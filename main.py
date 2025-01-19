from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import Database
from router import docRouter
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    """Startup event: Initialize database connection."""
    await Database.connect()

@app.on_event("shutdown")
async def shutdown():
    """Shutdown event: Close database connection."""
    await Database.close()

# Include routers for different endpoints
app.include_router(docRouter, prefix="", tags=["Document Upload"])
# app.include_router(auth.authRouter, prefix="/api/v1/user", tags=["Authentification"])

app.mount("/uploads", StaticFiles(directory="uploaded_files"), name="uploads")

# Include the upload router
app.include_router(docRouter)

@app.get("/")
async def root():
    return {"message": "Welcome to Adhyayan Backend"}

