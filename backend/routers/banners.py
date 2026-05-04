from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from backend.database import get_db
import random

router = APIRouter(tags=["Banners"])

@router.get("/banners", response_model=List[str])
async def get_banners():
    """Get a list of banner URLs for the AuthModal."""
    db = get_db()
    cursor = db["banners"].find({}, {"_id": 0, "url": 1})
    banners = await cursor.to_list(length=100)
    return [b["url"] for b in banners]

@router.post("/banners/sync")
async def sync_banners(urls: List[str]):
    """Sync/Add new banner URLs to the database."""
    db = get_db()
    if not urls:
        return {"message": "No URLs provided"}
    
    operations = []
    for url in urls:
        await db["banners"].update_one(
            {"url": url},
            {"$set": {"url": url}},
            upsert=True
        )
    
    return {"message": f"Synced {len(urls)} banners"}

@router.get("/banners/random")
async def get_random_banner():
    """Get a single random banner URL."""
    db = get_db()
    count = await db["banners"].count_documents({})
    if count == 0:
        return {"url": "https://pic.re/image"} # Fallback
    
    skip = random.randint(0, count - 1)
    banner = await db["banners"].find().skip(skip).limit(1).to_list(length=1)
    return {"url": banner[0]["url"]}
