"""Verify stored streaming links are still reachable."""
import asyncio
import os
import httpx
from backend.database import get_db

VIDPLAY_BASE_URL = os.getenv("VIDPLAY_BASE_URL", "https://vidplay-org.lol/e/")


def _build_embed_url(source_id: str) -> str:
    base = VIDPLAY_BASE_URL.rstrip("/") + "/"
    return f"{base}{source_id}"


async def check_links():
    print("Initiating stream health check...")
    db = get_db()
    cursor = db["streams"].find({})

    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
        async for document in cursor:
            mal_id = document.get("mal_id")
            for ep in document.get("episodes", []):
                source_id = ep.get("source_id")
                ep_number = ep.get("ep_number")
                if not source_id:
                    continue
                url = _build_embed_url(source_id)
                try:
                    response = await client.head(url)
                    if response.status_code != 200:
                        print(f"[WARNING] Broken link: MAL {mal_id} Ep {ep_number} ({response.status_code})")
                except Exception as exc:
                    print(f"[WARNING] Connection error: MAL {mal_id} Ep {ep_number} ({exc})")


if __name__ == "__main__":
    asyncio.run(check_links())
