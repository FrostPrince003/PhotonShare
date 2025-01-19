from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from motor.motor_asyncio import AsyncIOMotorDatabase
from dependencies import get_database
from typing import List
import shutil
from pathlib import Path
import os
import uuid
from pydantic import BaseModel
import asyncio
from datetime import datetime, timedelta
from starlette.responses import JSONResponse
from fastapi import Request

# Define a router for handling the requests
docRouter = APIRouter()

# Directory to store uploaded files
UPLOAD_DIR = Path("uploaded_files")
UPLOAD_DIR.mkdir(exist_ok=True)

# Background cleanup task reference
cleanup_task = None
class AuthDetails(BaseModel):
    name: str
    password: str
    
    
@docRouter.post("/checkauth")
async def check_auth(
    authdetails:AuthDetails,
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Validates the provided name and password to ensure no duplicate credentials.
    """
    try:
        if not authdetails.name or not authdetails.password:
            raise HTTPException(status_code=400, detail="Name and password are required.")
        
        # Collection to store data
        collection = db["uploads"]

        # Check for duplicate username and password
        existing_user = await collection.find_one({"auth.name": authdetails.name, "auth.password": authdetails.password})
        if existing_user:
            print("User already Exists try with another id or password")
            return JSONResponse(
                status_code=400,
                content={"message": "Auth name or password already assigned."}
            )
        else:
            print("Authentication Success")
            return JSONResponse(
                status_code=200,
                content={"message": "Authentication successful. You may proceed."}
            )

    except Exception as e:
        print(f"❌ Error checking credentials: {e}")
        raise HTTPException(status_code=500, detail=f"Error checking credentials: {e}")


@docRouter.post("/upload")
async def upload_files(
    name: str = Form(...),
    password: str = Form(...),
    files: List[UploadFile] = File(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Accepts files and auth details, stores files locally, and metadata in MongoDB.
    """
    try:
        # Validate inputs
        if not name or not password:
            raise HTTPException(status_code=400, detail="Name and password are required.")

        if not files or len(files) == 0:
            raise HTTPException(status_code=400, detail="At least one file must be uploaded.")

        # Collection to store data
        collection = db["uploads"]

        # List to store file metadata
        file_metadata = []
        
        for file in files:
            # Create a unique filename to avoid conflicts
            unique_filename = f"{uuid.uuid4().hex}_{file.filename}"
            file_path = UPLOAD_DIR / unique_filename

            # Save file to the local filesystem
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Append metadata for the saved file
            file_metadata.append({
                "original_filename": file.filename,
                "stored_filename": unique_filename,
                "file_path": str(file_path),
                "file_size": os.path.getsize(file_path),
                "content_type": file.content_type,
            })

        # Get the current time and time + 24 hours
        upload_time = datetime.now()
        expiry_time = upload_time + timedelta(hours=24)

        # Insert metadata into MongoDB
        upload_data = {
            "auth": {"name": name, "password": password},
            "files": file_metadata,
            "upload_time": upload_time.isoformat(),
            "expiry_time": expiry_time.isoformat(),
        }

        result = await collection.insert_one(upload_data)

        return {
            "message": "Files uploaded successfully",
            "upload_id": str(result.inserted_id),
            "files": file_metadata,
            "upload_time": upload_time.isoformat(),
            "expiry_time": expiry_time.isoformat(),
        }

    except Exception as e:
        print(f"❌ Error uploading files: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading files: {e}")

@docRouter.post("/delete")
async def delete_user(
    name: str = Form(...),
    password: str = Form(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Deletes a user document and their associated files based on the provided name and password.
    """
    try:
        # Ensure the required parameters are provided
        if not name or not password:
            raise HTTPException(status_code=400, detail="Name and password are required.")

        # Access the MongoDB collection
        collection = db["uploads"]

        # Find the user by name and password
        user_upload = await collection.find_one({"auth.name": name, "auth.password": password})

        if not user_upload:
            raise HTTPException(status_code=404, detail="No user found with the provided name and password.")

        # Delete all associated files from the filesystem
        for file in user_upload.get("files", []):
            file_path = Path(file["file_path"])
            if file_path.exists():
                file_path.unlink()  # Remove the file

        # Remove the user document from the database
        await collection.delete_one({"_id": user_upload["_id"]})

        return JSONResponse(
                status_code=200,
                content={"message": "User Deleted."}
            )

    except Exception as e:
        print(f"❌ Error deleting user: {e}")
        raise HTTPException(status_code=500, detail=f"Error deleting user: {e}")


@docRouter.post("/get-uploads")
async def get_uploaded_files(
    request: Request,  # This should come first
    name: str = Form(...),
    password: str = Form(...),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    """
    Retrieve uploaded files based on the provided auth name and password.
    """
    try:
        if not name or not password:
            raise HTTPException(status_code=400, detail="Name and password are required.")

        collection = db["uploads"]
        user_uploads = await collection.find_one({"auth.name": name, "auth.password": password})

        if not user_uploads:
            raise HTTPException(status_code=404, detail="No files found for the provided credentials.")

        # Modify file paths to be accessible URLs dynamically
        base_url = str(request.base_url).rstrip("/")
        for file in user_uploads["files"]:
            file["file_path"] = f"{base_url}/uploads/{file['stored_filename']}"

        return {
            "message": "Files retrieved successfully",
            "files": user_uploads["files"]
        }

    except Exception as e:
        print(f"❌ Error retrieving files: {e}")
        raise HTTPException(status_code=500, detail=f"Error retrieving files: {e}")


async def delete_expired_entries(db: AsyncIOMotorDatabase):
    """
    Periodically deletes expired entries and their associated files.
    """
    collection = db["uploads"]
    while True:
        try:
            # Get the current time
            current_time = datetime.now()

            # Query for expired entries
            expired_entries = await collection.find({"expiry_time": {"$lte": current_time.isoformat()}}).to_list(length=None)

            # Delete expired files and their metadata
            for entry in expired_entries:
                for file in entry["files"]:
                    # Delete file from filesystem
                    file_path = Path(file["file_path"])
                    if file_path.exists():
                        file_path.unlink()  # Remove the file

                # Remove the document from the database
                await collection.delete_one({"_id": entry["_id"]})

            print(f"✅ Cleanup executed at {current_time}, deleted {len(expired_entries)} expired entries.")

        except Exception as e:
            print(f"❌ Error during cleanup: {e}")

        # Wait for 1 hour before the next cleanup (adjust if needed)
        await asyncio.sleep(3600)


# Use a lifespan context in your main FastAPI application instead of router events.
# Move the startup/shutdown logic to that lifespan context (see FastAPI docs).
