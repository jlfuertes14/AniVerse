"""
Anime Discovery Engine — User Router
Watchlist, favorites, and watch progress endpoints.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone

from backend.database import get_db
from backend.auth_middleware import get_current_user

router = APIRouter(prefix="/user", tags=["user"])


class WatchlistRequest(BaseModel):
    anime_id: int
    anime_title: str
    anime_image: str = ""
    status: str = "plan_to_watch"


class WatchlistUpdateRequest(BaseModel):
    status: str


class ProgressRequest(BaseModel):
    episodes_watched: int
    total_episodes: int = 0


# ─── Watchlist ───────────────────────────────────

@router.get("/watchlist")
async def get_watchlist(
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """Get user's watchlist, optionally filtered by status."""
    user_id = current_user["sub"]
    db = get_db()
    
    query = {"user_id": user_id}
    if status:
        query["status"] = status
        
    cursor = db["watchlist"].find(query).sort("added_at", -1)
    rows = await cursor.to_list(length=1000)
    
    result = []
    for row in rows:
        row["id"] = str(row.pop("_id"))
        result.append(row)
        
    return result


@router.post("/watchlist")
async def add_to_watchlist(
    req: WatchlistRequest,
    current_user: dict = Depends(get_current_user),
):
    """Add anime to watchlist."""
    user_id = current_user["sub"]
    db = get_db()
    
    await db["watchlist"].update_one(
        {"user_id": user_id, "anime_id": req.anime_id},
        {
            "$set": {
                "anime_title": req.anime_title,
                "anime_image": req.anime_image,
                "status": req.status,
            },
            "$setOnInsert": {
                "added_at": datetime.now()
            }
        },
        upsert=True
    )
    
    return {"message": "Added to watchlist", "status": req.status}


@router.put("/watchlist/{anime_id}")
async def update_watchlist_status(
    anime_id: int,
    req: WatchlistUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update watchlist item status."""
    user_id = current_user["sub"]
    valid = ["watching", "completed", "plan_to_watch", "dropped", "on_hold"]
    if req.status not in valid:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(valid)}")

    db = get_db()
    
    result = await db["watchlist"].update_one(
        {"user_id": user_id, "anime_id": anime_id},
        {"$set": {"status": req.status}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Anime not in watchlist")
        
    return {"message": "Status updated", "status": req.status}


@router.delete("/watchlist/{anime_id}")
async def remove_from_watchlist(
    anime_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Remove anime from watchlist."""
    user_id = current_user["sub"]
    db = get_db()
    
    await db["watchlist"].delete_one({"user_id": user_id, "anime_id": anime_id})
    return {"message": "Removed from watchlist"}


# ─── Favorites ───────────────────────────────────

@router.get("/favorites")
async def get_favorites(current_user: dict = Depends(get_current_user)):
    """Get user's favorites."""
    user_id = current_user["sub"]
    db = get_db()
    
    cursor = db["favorites"].find({"user_id": user_id}).sort("added_at", -1)
    rows = await cursor.to_list(length=1000)
    
    result = []
    for row in rows:
        row["id"] = str(row.pop("_id"))
        result.append(row)
        
    return result


@router.post("/favorites/{anime_id}")
async def toggle_favorite(
    anime_id: int,
    anime_title: str = "",
    anime_image: str = "",
    current_user: dict = Depends(get_current_user),
):
    """Toggle favorite status for an anime."""
    user_id = current_user["sub"]
    db = get_db()
    
    existing = await db["favorites"].find_one({"user_id": user_id, "anime_id": anime_id})

    if existing:
        await db["favorites"].delete_one({"user_id": user_id, "anime_id": anime_id})
        return {"favorited": False}
    else:
        await db["favorites"].insert_one({
            "user_id": user_id,
            "anime_id": anime_id,
            "anime_title": anime_title,
            "anime_image": anime_image,
            "added_at": datetime.now()
        })
        return {"favorited": True}


@router.get("/is-favorited/{anime_id}")
async def is_favorited(anime_id: int, current_user: dict = Depends(get_current_user)):
    """Check if an anime is favorited."""
    user_id = current_user["sub"]
    db = get_db()
    
    existing = await db["favorites"].find_one({"user_id": user_id, "anime_id": anime_id})
    return {"favorited": existing is not None}


# ─── Watch Progress ──────────────────────────────

@router.put("/progress/{anime_id}")
async def update_progress(
    anime_id: int,
    req: ProgressRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update watch progress for an anime."""
    user_id = current_user["sub"]
    db = get_db()
    
    await db["watch_progress"].update_one(
        {"user_id": user_id, "anime_id": anime_id},
        {
            "$set": {
                "episodes_watched": req.episodes_watched,
                "total_episodes": req.total_episodes,
                "updated_at": datetime.now()
            }
        },
        upsert=True
    )
    return {"message": "Progress updated"}


@router.get("/progress/{anime_id}")
async def get_progress(anime_id: int, current_user: dict = Depends(get_current_user)):
    """Get watch progress for a specific anime."""
    user_id = current_user["sub"]
    db = get_db()
    
    row = await db["watch_progress"].find_one({"user_id": user_id, "anime_id": anime_id})
    if row:
        row["id"] = str(row.pop("_id"))
        return row
    return {"episodes_watched": 0, "total_episodes": 0}


# ─── Watchlist Status Check ─────────────────────

@router.get("/watchlist-status/{anime_id}")
async def get_watchlist_status(anime_id: int, current_user: dict = Depends(get_current_user)):
    """Check if anime is in watchlist and its status."""
    user_id = current_user["sub"]
    db = get_db()
    
    row = await db["watchlist"].find_one({"user_id": user_id, "anime_id": anime_id})
    if row:
        return {"in_watchlist": True, "status": row.get("status")}
    return {"in_watchlist": False, "status": None}
