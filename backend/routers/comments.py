"""
Anime Discovery Engine — Comments Router
Per-anime discussion/comments.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timezone
from bson.objectid import ObjectId

from backend.database import get_db
from backend.auth_middleware import get_current_user

router = APIRouter(prefix="/comments", tags=["comments"])


class CommentRequest(BaseModel):
    content: str


@router.get("/{anime_id}")
async def get_comments(anime_id: int):
    """Get all comments for an anime (public)."""
    db = get_db()
    
    cursor = db["comments"].find({"anime_id": anime_id}).sort("created_at", -1)
    comments = await cursor.to_list(length=1000)
    
    # Collect unique user IDs
    user_ids = list(set(c["user_id"] for c in comments))
    object_ids = []
    for uid in user_ids:
        try:
            object_ids.append(ObjectId(uid))
        except:
            pass
            
    # Fetch users
    users_cursor = db["users"].find({"_id": {"$in": object_ids}})
    users = await users_cursor.to_list(length=1000)
    
    user_map = {
        str(u["_id"]): {"id": str(u["_id"]), "username": u["username"], "avatar_url": u.get("avatar_url")}
        for u in users
    }
    
    result = []
    for c in comments:
        user_info = user_map.get(c["user_id"], {
            "id": c["user_id"], 
            "username": "Unknown User", 
            "avatar_url": None
        })
        
        result.append({
            "id": str(c["_id"]),
            "anime_id": c["anime_id"],
            "content": c["content"],
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
            "user": user_info
        })
        
    return result


@router.post("/{anime_id}")
async def add_comment(
    anime_id: int,
    req: CommentRequest,
    current_user: dict = Depends(get_current_user),
):
    """Add a comment to an anime (auth required)."""
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="Comment cannot be empty")
    if len(req.content) > 2000:
        raise HTTPException(status_code=400, detail="Comment too long (max 2000 characters)")

    user_id = current_user["sub"]
    db = get_db()
    
    now = datetime.now(timezone.utc)
    new_comment = {
        "user_id": user_id,
        "anime_id": anime_id,
        "content": req.content.strip(),
        "created_at": now,
        "updated_at": now
    }
    
    result = await db["comments"].insert_one(new_comment)
    comment_id = str(result.inserted_id)

    # Return the created comment with user info
    try:
        user = await db["users"].find_one({"_id": ObjectId(user_id)})
    except:
        user = None
        
    if not user:
        user = {"username": "Unknown User", "avatar_url": None}

    return {
        "id": comment_id,
        "anime_id": anime_id,
        "content": req.content.strip(),
        "created_at": now,
        "user": {
            "id": user_id,
            "username": user["username"],
            "avatar_url": user.get("avatar_url"),
        },
    }


@router.delete("/{comment_id}")
async def delete_comment(
    comment_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete own comment."""
    user_id = current_user["sub"]
    db = get_db()
    
    try:
        obj_id = ObjectId(comment_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid comment ID")
        
    comment = await db["comments"].find_one({"_id": obj_id})
    
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    if str(comment["user_id"]) != str(user_id):
        raise HTTPException(status_code=403, detail="Not your comment")

    await db["comments"].delete_one({"_id": obj_id})
    return {"message": "Comment deleted"}
