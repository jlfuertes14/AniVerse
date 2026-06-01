"""
Anime Discovery Engine -- Miruro Scraper Service
Extracts HLS streams from Miruro dynamically using Playwright.
"""
import asyncio
import json
import os
import sys
import subprocess
from datetime import datetime, timezone
from backend.database import get_db

# Path to the scraper runner script
SCRAPER_RUNNER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scraper_runner.py")

_active_refreshes: set[int] = set()
_refresh_locks: dict[int, asyncio.Lock] = {}

def is_miruro_refresh_in_progress(mal_id: int) -> bool:
    return mal_id in _active_refreshes

def _get_refresh_lock(mal_id: int) -> asyncio.Lock:
    lock = _refresh_locks.get(mal_id)
    if lock is None:
        lock = asyncio.Lock()
        _refresh_locks[mal_id] = lock
    return lock

async def refresh_miruro_catalog(mal_id: int, ep_number: int):
    """
    Background discovery for Miruro.
    Since Miruro uses AniList IDs, we can map MAL to AniList, then scrape immediately.
    """
    lock = _get_refresh_lock(mal_id)
    if lock.locked():
        print(f"[Miruro] Discovery already running for {mal_id}")
        return

    async with lock:
        _active_refreshes.add(mal_id)
        db = get_db()
        try:
            await db["provider_mappings"].update_one(
                {"mal_id": mal_id, "provider": "miruro"},
                {"$set": {"refreshing": True, "refresh_started_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True
            )
            
            # Resolve AniList ID
            anilist_id = None
            try:
                from backend.services.anilist_service import get_anilist_id_by_mal_id
                anilist_id = await get_anilist_id_by_mal_id(mal_id)
            except Exception as e:
                print(f"[Miruro] Failed to resolve AniList ID for MAL {mal_id}: {e}")
            
            if anilist_id:
                results = await scrape_miruro_episode(anilist_id, mal_id, ep_number)
                if not results:
                    print(f"[Miruro] Scraper returned no results for MAL {mal_id} Ep {ep_number}")
                    await db["provider_mappings"].update_one(
                        {"mal_id": mal_id, "provider": "miruro"},
                        {"$set": {"last_scrape_error": "No stream found"}}
                    )
                else:
                    await db["provider_mappings"].update_one(
                        {"mal_id": mal_id, "provider": "miruro"},
                        {"$set": {"last_success_at": datetime.utcnow().isoformat() + "Z"}, "$unset": {"last_scrape_error": ""}}
                    )
            else:
                print(f"[Miruro] Cannot scrape without anilist_id for MAL {mal_id}")
                await db["provider_mappings"].update_one(
                    {"mal_id": mal_id, "provider": "miruro"},
                    {"$set": {"last_scrape_error": "No anilist_id"}}
                )
                
        except Exception as e:
            print(f"[Miruro] Background discovery failed for {mal_id}: {e}")
            await db["provider_mappings"].update_one(
                {"mal_id": mal_id, "provider": "miruro"},
                {"$set": {"last_scrape_error": str(e)}},
                upsert=True
            )
        finally:
            _active_refreshes.discard(mal_id)
            await db["provider_mappings"].update_one(
                {"mal_id": mal_id, "provider": "miruro"},
                {"$set": {
                    "refreshing": False, 
                    "last_catalog_check_at": datetime.utcnow().isoformat() + "Z"
                }, "$unset": {"refresh_started_at": ""}},
                upsert=True
            )


async def scrape_miruro_episode(anilist_id: int, mal_id: int, ep_number: int):
    """Scrape and store a single Miruro episode."""
    print(f"[Miruro] Scraping episode {ep_number} for anilist_id {anilist_id}")

    try:
        result = await _run_scraper_subprocess("miruro_episode", {
            "anilist_id": anilist_id,
            "episode_number": ep_number
        })
        
        if result and (result.get("stream_url") or result.get("embed_url")):
            db = get_db()
            
            # Update stream record
            await db["streams"].update_one(
                {"anilist_id": mal_id, "episode": ep_number, "source": "miruro"},
                {"$set": {
                    "anilist_id": mal_id,
                    "mal_id": mal_id, 
                    "episode": ep_number,
                    "source": "miruro",
                    "stream_url": result.get("stream_url"),
                    "embed_url": result.get("embed_url"),
                    "updated_at": "resolved",
                    "referer_url": result.get("referer_url"),
                    "subtitles": result.get("subtitles", [])
                }},
                upsert=True
            )

            # Update provider mapping with the detected episode count
            if result.get("available_episodes"):
                await db["provider_mappings"].update_one(
                    {"mal_id": mal_id, "provider": "miruro"},
                    {"$set": {
                        "mal_id": mal_id,
                        "anilist_id": anilist_id,
                        "provider": "miruro",
                        "latest_episode": result["available_episodes"],
                        "last_scraped_at": datetime.now(timezone.utc).isoformat(),
                    }},
                    upsert=True,
                )

            return [result]
    except Exception as e:
        print(f"[Miruro] Scrape error: {e}")
    
    return []


async def _run_scraper_subprocess(action: str, params: dict) -> dict | None:
    """
    Run a scraper action in a separate Python process.
    Required for Windows/Playwright compatibility.
    """
    cmd = [
        sys.executable,
        SCRAPER_RUNNER,
        action,
        json.dumps(params)
    ]

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _sync_run_subprocess, cmd)
    return result

def _sync_run_subprocess(cmd: list) -> dict | None:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )

        if proc.stderr:
            for line in proc.stderr.splitlines():
                if line.strip():
                    print(f"[Scraper] {line}")

        if proc.returncode != 0:
            print(f"[Subprocess] Error (exit {proc.returncode})")
            return None

        stdout = proc.stdout.strip()
        if not stdout:
            return None

        for line in reversed(stdout.split('\\n')):
            line = line.strip()
            if line.startswith('{') or line.startswith('['):
                return json.loads(line)

    except subprocess.TimeoutExpired:
        print("[Subprocess] Timed out after 120s")
    except json.JSONDecodeError as e:
        print(f"[Subprocess] JSON parse error: {e}")
    except Exception as e:
        print(f"[Subprocess] Error: {e}")
    return None
