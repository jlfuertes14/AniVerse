"""
Anime Discovery Engine — Screenshot Router
Reverse image search via trace.moe.
"""
from fastapi import APIRouter, UploadFile, File, Query
from typing import Optional
from backend.services import tracemoe_service

router = APIRouter(prefix="/screenshot", tags=["screenshot"])


@router.post("/search")
async def search_by_screenshot(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Query(None, description="Image URL to search"),
):
    """Search for anime by uploading a screenshot or providing an image URL."""
    if file:
        image_bytes = await file.read()
        results = await tracemoe_service.search_by_image(image_bytes)
    elif url:
        results = await tracemoe_service.search_by_url(url)
    else:
        return {"error": "Please provide an image file or URL"}

    return {"results": [r.model_dump() for r in results]}
