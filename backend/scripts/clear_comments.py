
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def clear_comments():
    uri = os.getenv("MONGODB_URI")
    if not uri:
        print("MONGODB_URI not found")
        return
    
    client = AsyncIOMotorClient(uri)
    db = client["aniverse"]
    
    result = await db["comments"].delete_many({})
    print(f"Deleted {result.deleted_count} comments.")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(clear_comments())
