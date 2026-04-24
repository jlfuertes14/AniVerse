"""
Anime Discovery Engine — trace.moe Service
Reverse image search to find anime from screenshots.
"""
import httpx
from backend.models.schemas import ScreenshotResult

TRACE_MOE_URL = "https://api.trace.moe/search"


async def search_by_image(image_bytes: bytes) -> list[ScreenshotResult]:
    """Search for anime by uploading a screenshot image."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            TRACE_MOE_URL,
            content=image_bytes,
            headers={"Content-Type": "image/jpeg"},
        )
        response.raise_for_status()
        data = response.json()

    results = []
    for item in data.get("result", [])[:5]:
        anilist_id = item.get("anilist")

        # Build preview URLs
        filename = item.get("filename", "")
        episode = item.get("episode")
        timestamp = item.get("from", 0)

        image_url = f"https://trace.moe/thumbnail.php?anilist_id={anilist_id}&file={filename}&t={timestamp}&token="
        video_url = f"https://trace.moe/preview.php?anilist_id={anilist_id}&file={filename}&t={timestamp}&token="

        results.append(ScreenshotResult(
            anilist_id=anilist_id,
            title=item.get("filename", "").split("/")[0] if "/" in item.get("filename", "") else None,
            episode=episode if isinstance(episode, int) else None,
            timestamp_from=item.get("from"),
            timestamp_to=item.get("to"),
            similarity=round(item.get("similarity", 0) * 100, 2),
            image_url=image_url,
            video_url=video_url,
        ))

    return results


async def search_by_url(image_url: str) -> list[ScreenshotResult]:
    """Search for anime by providing an image URL."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            TRACE_MOE_URL,
            params={"url": image_url},
        )
        response.raise_for_status()
        data = response.json()

    results = []
    for item in data.get("result", [])[:5]:
        anilist_id = item.get("anilist")
        filename = item.get("filename", "")
        timestamp = item.get("from", 0)

        results.append(ScreenshotResult(
            anilist_id=anilist_id,
            title=filename.split("/")[0] if "/" in filename else None,
            episode=item.get("episode") if isinstance(item.get("episode"), int) else None,
            timestamp_from=item.get("from"),
            timestamp_to=item.get("to"),
            similarity=round(item.get("similarity", 0) * 100, 2),
            image_url=f"https://trace.moe/thumbnail.php?anilist_id={anilist_id}&file={filename}&t={timestamp}&token=",
            video_url=f"https://trace.moe/preview.php?anilist_id={anilist_id}&file={filename}&t={timestamp}&token=",
        ))

    return results
