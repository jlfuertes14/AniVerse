import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from backend.database import get_db

async def refresh_shiroko_catalog(mal_id: int, episode_number: int):
    """
    Triggers Shiroko scraper for a specific episode.
    """
    db = get_db()
    
    # Mark as refreshing
    await db["provider_mappings"].update_one(
        {"mal_id": mal_id, "provider": "shiroko"},
        {"$set": {"status": "refreshing", "last_catalog_check_at": datetime.utcnow().isoformat() + "Z"}},
        upsert=True
    )
    
    # Find mapping for Anilist ID
    anilist_mapping = await db["anime_mappings"].find_one({"mal_id": mal_id})
    anilist_id = None
    if anilist_mapping and anilist_mapping.get("anilist_id"):
        anilist_id = anilist_mapping["anilist_id"]
    else:
        # Fallback to dynamic lookup using AniList GraphQL API
        print(f"[Shiroko] No Anilist ID found for MAL {mal_id} in DB. Fetching from AniList API...")
        try:
            from backend.services.anilist_service import get_anilist_id_by_mal_id
            anilist_id = await get_anilist_id_by_mal_id(mal_id)
        except Exception as e:
            print(f"[Shiroko] Dynamic AniList lookup failed: {e}")
            
    if not anilist_id:
        print(f"[Shiroko] Failed to resolve Anilist ID for MAL ID {mal_id}")
        await _clear_refreshing(db, mal_id)
        return
    
    try:
        # We can run this in an executor thread so it doesn't block asyncio
        loop = asyncio.get_running_loop()
        stream_data = await loop.run_in_executor(
            None, 
            _run_shiroko_scraper, 
            anilist_id, 
            episode_number
        )
        
        if stream_data:
            # Store stream
            stream_data["anilist_id"] = mal_id  # We store with MAL ID as key
            stream_data["episode"] = episode_number
            stream_data["source"] = "shiroko"
            stream_data["created_at"] = datetime.now(timezone.utc)
            
            await db["streams"].update_one(
                {"anilist_id": mal_id, "episode": episode_number, "source": "shiroko"},
                {"$set": stream_data},
                upsert=True
            )
            
            # Update mapping
            await db["provider_mappings"].update_one(
                {"mal_id": mal_id, "provider": "shiroko"},
                {"$set": {
                    "status": "idle",
                    "last_success_at": datetime.utcnow().isoformat() + "Z",
                    "latest_episode": episode_number
                }, "$unset": {"last_scrape_error": ""}}
            )
            print(f"[Shiroko] Successfully fetched stream for MAL {mal_id} Ep {episode_number}")
        else:
            print(f"[Shiroko] Failed to fetch stream for MAL {mal_id} Ep {episode_number}")
            await db["provider_mappings"].update_one(
                {"mal_id": mal_id, "provider": "shiroko"},
                {"$set": {
                    "status": "idle",
                    "last_scrape_error": "No stream found"
                }}
            )
    except Exception as e:
        print(f"[Shiroko] Error running scraper: {e}")
        await _clear_refreshing(db, mal_id)

async def _clear_refreshing(db, mal_id: int):
    await db["provider_mappings"].update_one(
        {"mal_id": mal_id, "provider": "shiroko"},
        {"$set": {"status": "idle"}}
    )

def _run_shiroko_scraper(anilist_id: int, episode_number: int) -> Optional[Dict[str, Any]]:
    cmd = [
        "python", "scraper_runner.py", "shiroko_episode",
        json.dumps({
            "anilist_id": anilist_id,
            "episode_number": episode_number
        })
    ]
    try:
        import os
        env = os.environ.copy()
        env["SCRAPER_SUBPROCESS"] = "1"
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)
        
        if result.stderr:
            for line in result.stderr.strip().split("\n"):
                if line.strip():
                    print(line.strip())
                    
        lines = result.stdout.strip().split("\n")
        if not lines or not lines[-1].strip(): return None
        data = json.loads(lines[-1])
        return data if data else None
    except Exception as e:
        print(f"[Shiroko] Subprocess error: {e}")
        return None

def is_shiroko_refresh_in_progress(mal_id: int) -> bool:
    # Need synchronous check or async check. Since it's used in router synchronously without await in animepahe, wait, router methods are async.
    # Actually we should make it async or just do a quick DB check.
    # To keep it sync-like, I will implement it as sync if we just do a quick pymongo query, but it's motor! So it must be async.
    pass

async def check_shiroko_refresh_in_progress(mal_id: int) -> bool:
    db = get_db()
    mapping = await db["provider_mappings"].find_one({"mal_id": mal_id, "provider": "shiroko"})
    return mapping.get("status") == "refreshing" if mapping else False
