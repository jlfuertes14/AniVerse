"""
Anime Discovery Engine — Auth Router
Register, login, and profile endpoints.
"""
from fastapi import APIRouter, HTTPException, status, Depends, File, UploadFile
from pydantic import BaseModel, EmailStr
import bcrypt
import base64
from datetime import datetime, timezone
from bson.objectid import ObjectId

from backend.database import get_db
from backend.auth_middleware import create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/register")
async def register(req: RegisterRequest):
    """Register a new user."""
    if len(req.username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    db = get_db()
    
    # Check if user exists
    existing = await db["users"].find_one({
        "$or": [
            {"email": req.email},
            {"username": req.username}
        ]
    })
    if existing:
        raise HTTPException(status_code=409, detail="Email or username already taken")

    # Hash password and insert
    password_hash = bcrypt.hashpw(req.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    
    new_user = {
        "username": req.username,
        "email": req.email,
        "password_hash": password_hash,
        "avatar_url": None,
        "created_at": datetime.now(timezone.utc)
    }
    
    result = await db["users"].insert_one(new_user)
    user_id = str(result.inserted_id)

    # Generate token
    token = create_access_token({"sub": user_id, "username": req.username})
    return {
        "token": token,
        "user": {
            "id": user_id,
            "username": req.username,
            "email": req.email,
            "avatar_url": None,
        },
    }


@router.post("/login")
async def login(req: LoginRequest):
    """Login with email and password."""
    db = get_db()
    
    user = await db["users"].find_one({"email": req.email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Verify password
    if not bcrypt.checkpw(req.password.encode("utf-8"), user["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_id = str(user["_id"])
    token = create_access_token({"sub": user_id, "username": user["username"]})
    
    return {
        "token": token,
        "user": {
            "id": user_id,
            "username": user["username"],
            "email": user["email"],
            "avatar_url": user.get("avatar_url"),
        },
    }


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user profile."""
    db = get_db()
    
    user_id = current_user["sub"]
    user = await db["users"].find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Get stats
    watchlist_count = await db["watchlist"].count_documents({"user_id": user_id})
    favorites_count = await db["favorites"].count_documents({"user_id": user_id})
    comments_count = await db["comments"].count_documents({"user_id": user_id})

    return {
        "id": str(user["_id"]),
        "username": user["username"],
        "email": user["email"],
        "avatar_url": user.get("avatar_url"),
        "created_at": user.get("created_at"),
        "stats": {
            "watchlist": watchlist_count,
            "favorites": favorites_count,
            "comments": comments_count,
        },
    }


MAX_AVATAR_SIZE = 500 * 1024  # 500KB
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


@router.put("/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload a profile picture."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, GIF, and WebP images are allowed")

    contents = await file.read()
    if len(contents) > MAX_AVATAR_SIZE:
        raise HTTPException(status_code=400, detail="Image must be under 500KB")

    # Convert to base64 data URL
    b64 = base64.b64encode(contents).decode("utf-8")
    data_url = f"data:{file.content_type};base64,{b64}"

    user_id = current_user["sub"]
    db = get_db()

    await db["users"].update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"avatar_url": data_url}}
    )

    return {"avatar_url": data_url}
