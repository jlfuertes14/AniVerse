import asyncio
import json
import os
import subprocess
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from backend.database import get_db

async def refresh_uniquestream_catalog(mal_id: int, title: str, episode_number: int):
    db = get_db()
    
    await db["provider_mappings"].update_one(
        {"mal_id": mal_id, "provider": "uniquestream"},
        {"$set": {"status": "refreshing", "last_catalog_check_at": datetime.utcnow().isoformat() + "Z"}},
        upsert=True
    )
    
    try:
        loop = asyncio.get_running_loop()
        stream_data = await loop.run_in_executor(
            None, 
            _run_uniquestream_scraper, 
            title, 
            episode_number
        )
        
        if stream_data:
            stream_data["anilist_id"] = mal_id  # Store under mal_id for consistency
            stream_data["episode"] = episode_number
            stream_data["source"] = "uniquestream"
            stream_data["created_at"] = datetime.now(timezone.utc)
            
            await db["streams"].update_one(
                {"anilist_id": mal_id, "episode": episode_number, "source": "uniquestream"},
                {"$set": stream_data},
                upsert=True
            )
            
            await db["provider_mappings"].update_one(
                {"mal_id": mal_id, "provider": "uniquestream"},
                {"$set": {
                    "status": "idle",
                    "last_success_at": datetime.utcnow().isoformat() + "Z",
                    "latest_episode": episode_number
                }, "$unset": {"last_scrape_error": ""}}
            )
            print(f"[Uniquestream] Successfully fetched stream for MAL {mal_id} Ep {episode_number}")
        else:
            print(f"[Uniquestream] Failed to fetch stream for MAL {mal_id} Ep {episode_number}")
            await db["provider_mappings"].update_one(
                {"mal_id": mal_id, "provider": "uniquestream"},
                {"$set": {
                    "status": "idle",
                    "last_scrape_error": "No stream found"
                }}
            )
    except Exception as e:
        print(f"[Uniquestream] Error running scraper: {e}")
        await _clear_refreshing(db, mal_id)

async def _clear_refreshing(db, mal_id: int):
    await db["provider_mappings"].update_one(
        {"mal_id": mal_id, "provider": "uniquestream"},
        {"$set": {"status": "idle"}}
    )

def _run_uniquestream_scraper(title: str, episode_number: int) -> Optional[Dict[str, Any]]:
    cmd = [
        "python", "scraper_runner.py", "uniquestream_episode",
        json.dumps({
            "title": title,
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
        print(f"[Uniquestream] Subprocess error: {e}")
        return None

async def check_uniquestream_refresh_in_progress(mal_id: int) -> bool:
    db = get_db()
    mapping = await db["provider_mappings"].find_one({"mal_id": mal_id, "provider": "uniquestream"})
    return mapping.get("status") == "refreshing" if mapping else False
