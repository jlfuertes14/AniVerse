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
MANUAL_PROVIDER_MAPPINGS = [
    {
        "mal_id": 61316,
        "provider": "animepahe",
        "session": "331f5a10-a98f-656b-d863-a9baf430e133",
        "title": "Re:ZERO kara Hajimeru Isekai Seikatsu 3rd Season",
        "source": "seed"
    }
]

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

    # streams collection indexes
    await db["streams"].create_index(
        [("mal_id", 1), ("episode", 1), ("source", 1)],
        unique=True,
        name="stream_ep_unique"
    )
    await db["streams"].create_index("anilist_id")
    
    # provider_mappings collection indexes
    await db["provider_mappings"].create_index([("mal_id", 1), ("provider", 1)], unique=True)
    await db["provider_mappings"].create_index([("provider", 1), ("is_airing", 1), ("last_catalog_check_at", 1)])
    await db["provider_mappings"].create_index([("provider", 1), ("title_normalized", 1)])
    await db["provider_mappings"].create_index([("provider", 1), ("mapping_retry_after", 1)])

    # persistent cache collection indexes
    await db["cache"].create_index("key", unique=True)
    await db["cache"].create_index("expires_at", expireAfterSeconds=0)

    # refresh_locks collection indexes (TTL-based distributed locks)
    await db["refresh_locks"].create_index("key", unique=True)
    await db["refresh_locks"].create_index("expires_at", expireAfterSeconds=0)

    for mapping in MANUAL_PROVIDER_MAPPINGS:
        await db["provider_mappings"].update_one(
            {"mal_id": mapping["mal_id"], "provider": mapping["provider"]},
            {"$set": mapping},
            upsert=True
        )
    
    print("[DB] MongoDB connected and indexes verified.")
