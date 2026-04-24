"""
Anime Discovery Engine — Database (MongoDB via Motor)
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI")
if not MONGODB_URI:
    raise ValueError("MONGODB_URI environment variable is not set")
DB_NAME = "aniverse"

client = None

def get_db():
    """Get a database instance."""
    global client
    if client is None:
        client = AsyncIOMotorClient(MONGODB_URI)
    return client[DB_NAME]

async def init_db():
    """Create required indexes for MongoDB collections."""
    db = get_db()
    
    # users collection indexes
    await db["users"].create_index("username", unique=True)
    await db["users"].create_index("email", unique=True)
    
    # watchlist collection indexes
    await db["watchlist"].create_index([("user_id", 1), ("anime_id", 1)], unique=True)
    
    # favorites collection indexes
    await db["favorites"].create_index([("user_id", 1), ("anime_id", 1)], unique=True)
    
    # watch_progress collection indexes
    await db["watch_progress"].create_index([("user_id", 1), ("anime_id", 1)], unique=True)
    
    print("[DB] MongoDB connected and indexes verified.")
