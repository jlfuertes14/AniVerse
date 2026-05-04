"""
Anime Discovery Engine — Filters Router
Genre and studio lists for frontend dropdowns.
"""
from fastapi import APIRouter
from backend.services import jikan_service

router = APIRouter(prefix="/filters", tags=["filters"])


@router.get("/genres")
async def get_genres():
    """Get all anime genres for filter dropdowns."""
    try:
        return await jikan_service.get_genres()
    except Exception as e:
        print(f"[Filters] Genres fetch failed: {e}")
        return []


@router.get("/studios")
async def get_studios():
    """Get top anime studios for filter dropdowns."""
    try:
        return await jikan_service.get_studios()
    except Exception as e:
        print(f"[Filters] Studios fetch failed: {e}")
        return []
