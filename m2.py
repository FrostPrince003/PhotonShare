from fastapi import FastAPI
import httpx  # A fast HTTP client for sending requests
import asyncio

app = FastAPI()

# Background task for self-pinging
async def ping_self():
    url = "https://yourappname.onrender.com"  # Replace with your backend's URL
    async with httpx.AsyncClient() as client:
        while True:
            try:
                response = await client.get(url)
                print(f"Self-ping successful: {response.status_code}")
            except Exception as e:
                print(f"Self-ping failed: {e}")
            # Wait for 14 minutes before the next ping
            await asyncio.sleep(14 * 60)

@app.on_event("startup")
async def startup_event():
    # Launch the self-ping task during app startup
    asyncio.create_task(ping_self())

@app.get("/")
async def root():
    return {"message": "Hello, FastAPI is running!"}

