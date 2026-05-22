"""
Anime Discovery Engine -- Re:ANIME Scraper Service
Extracts FlixCloud embed URLs from Re:ANIME.
"""
import asyncio
import json
import os
import sys
import subprocess
import re
from datetime import datetime, timezone, timedelta
from backend.database import get_db

# Configuration
LATEST_RELEASES_REFRESH_INTERVAL = timedelta(minutes=15)
_latest_releases_lock = asyncio.Lock()
MAPPING_LOOKUP_CONCURRENCY = 2

# Path to the scraper runner script
SCRAPER_RUNNER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scraper_runner.py")

_active_refreshes: set[int] = set()
_refresh_locks: dict[int, asyncio.Lock] = {}

def is_reanime_refresh_in_progress(mal_id: int) -> bool:
    return mal_id in _active_refreshes

def _get_refresh_lock(mal_id: int) -> asyncio.Lock:
    lock = _refresh_locks.get(mal_id)
    if lock is None:
        lock = asyncio.Lock()
        _refresh_locks[mal_id] = lock
    return lock

def _expand_title_candidates(title: str | None) -> list[str]:
    if not title:
        return []

    candidates: list[str] = []

    def add(value: str | None):
        if value and value not in candidates:
            candidates.append(value)

    add(title)
    trimmed = re.sub(r"\s+(Part|Cour|Season)\s+\d+\s*$", "", title, flags=re.IGNORECASE).strip()
    add(trimmed)
    collapsed = re.sub(r"\b\d+(st|nd|rd|th)\s+Season\b", "", title, flags=re.IGNORECASE).strip(" :-")
    add(collapsed)
    return candidates


def _normalize_title(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\b(season|part|cour|tv)\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _mapping_retry_active(mapping: dict | None) -> bool:
    if not mapping:
        return False
    retry_after = mapping.get("mapping_retry_after")
    if not retry_after:
        return False
    try:
        retry_at = datetime.fromisoformat(str(retry_after).replace("Z", "+00:00"))
    except ValueError:
        return False
    return retry_at > datetime.now(timezone.utc)


async def _build_reanime_title_candidates(mal_id: int | None, fallback_title: str) -> list[str]:
    candidates: list[str] = []
    for title in _expand_title_candidates(fallback_title):
        if title not in candidates:
            candidates.append(title)

    if not mal_id:
        return candidates

    try:
        from backend.services.jikan_service import get_anime_detail as get_jikan_anime_detail

        detail = await get_jikan_anime_detail(mal_id)
        for title_variant in [detail.title, detail.title_english, detail.title_japanese]:
            for expanded in _expand_title_candidates(title_variant):
                if expanded not in candidates:
                    candidates.append(expanded)
    except Exception as e:
        print(f"[Re:ANIME] Failed to build title candidates for {mal_id}: {e}")

    return candidates

async def refresh_reanime_catalog(mal_id: int, title: str, ep_number: int):
    """
    Background discovery for Re:ANIME.
    Updates DB mapping state while discovery is running.
    """
    lock = _get_refresh_lock(mal_id)
    if lock.locked():
        print(f"[Re:ANIME] Discovery already running for {mal_id}")
        return

    async with lock:
        _active_refreshes.add(mal_id)
        db = get_db()
        try:
            await db["provider_mappings"].update_one(
                {"mal_id": mal_id, "provider": "reanime"},
                {"$set": {"refreshing": True, "refresh_started_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True
            )
            reanime_slug = await search_reanime_by_title(title, mal_id)
            if reanime_slug:
                await scrape_reanime_episode(reanime_slug, mal_id, ep_number)
        except Exception as e:
            print(f"[Re:ANIME] Background discovery failed for {mal_id}: {e}")
        finally:
            _active_refreshes.discard(mal_id)
            await db["provider_mappings"].update_one(
                {"mal_id": mal_id, "provider": "reanime"},
                {"$set": {
                    "refreshing": False, 
                    "last_catalog_check_at": datetime.now(timezone.utc).isoformat()
                }, "$unset": {"refresh_started_at": ""}},
                upsert=True
            )

async def search_reanime_by_title(title: str, mal_id: int = None):
    """
    Searches Re:ANIME for an anime by its title and returns the slug.
    Checks DB cache first if mal_id is provided.
    """
    db = get_db()
    
    # Check cache first
    if mal_id:
        cached = await db["provider_mappings"].find_one({"mal_id": mal_id, "provider": "reanime"})
        if cached and "slug" in cached:
            return cached["slug"]

    target_anilist_id = None
    if mal_id:
        try:
            from backend.services.anilist_service import get_anilist_id_by_mal_id
            target_anilist_id = await get_anilist_id_by_mal_id(mal_id)
        except Exception as e:
            print(f"[Re:ANIME] Failed to resolve AniList ID for MAL {mal_id}: {e}")

    title_candidates = await _build_reanime_title_candidates(mal_id, title)
    for candidate in title_candidates:
        result = await _run_scraper_subprocess(
            "reanime_search",
            {"title": candidate, "anilist_id": target_anilist_id}
        )
        
        if result and result.get("slug"):
            slug = result["slug"]
            if mal_id:
                await db["provider_mappings"].update_one(
                    {"mal_id": mal_id, "provider": "reanime"},
                    {"$set": {
                        "mal_id": mal_id,
                        "anilist_id": mal_id,
                        "slug": slug, 
                        "title": title,
                        "title_normalized": _normalize_title(title),
                        "provider": "reanime",
                        "last_mapped_at": datetime.now(timezone.utc).isoformat(),
                    }},
                    upsert=True
                )
            return slug
    
    return None

async def scrape_reanime_episode(slug: str, mal_id: int, ep_number: int):
    """Scrape and store a single Re:ANIME episode."""
    print(f"[Re:ANIME] Scraping episode {ep_number} for slug {slug}")

    try:
        result = await _run_scraper_subprocess("reanime_scrape_episode", {
            "slug": slug,
            "episode_number": ep_number
        })
        
        if result and (result.get("stream_url") or result.get("embed_url")):
            db = get_db()
            
            # Update stream record
            await db["streams"].update_one(
                {"anilist_id": mal_id, "episode": ep_number, "source": "reanime"},
                {"$set": {
                    "anilist_id": mal_id,
                    "mal_id": mal_id, 
                    "episode": ep_number,
                    "source": "reanime",
                    "stream_url": result.get("stream_url"),
                    "embed_url": result.get("embed_url"),
                    "updated_at": "resolved",
                    "referer_url": result.get("referer_url"),
                }},
                upsert=True
            )

            # Update provider mapping with the detected episode count
            if result.get("available_episodes"):
                await db["provider_mappings"].update_one(
                    {"mal_id": mal_id, "provider": "reanime"},
                    {"$set": {
                        "mal_id": mal_id,
                        "anilist_id": mal_id,
                        "slug": slug,
                        "provider": "reanime",
                        "latest_episode": result["available_episodes"],
                        "last_scraped_at": datetime.now(timezone.utc).isoformat(),
                    }},
                    upsert=True,
                )

            return [result]
    except Exception as e:
        print(f"[Re:ANIME] Scrape error: {e}")
    
    return []

async def get_stream_for_episode(mal_id: int, ep_number: int):
    """Check DB for a cached Re:ANIME stream."""
    db = get_db()
    return await db["streams"].find_one({
        "anilist_id": mal_id,
        "episode": ep_number,
        "source": "reanime"
    })

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

    # Run in a thread to not block the event loop
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, _sync_run_subprocess, cmd)
    return result

def _sync_run_subprocess(cmd: list) -> dict | None:
    """Synchronously run the subprocess and parse JSON output."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )

        # Print scraper logs for visibility
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

        # Find the last JSON line in the output
        for line in reversed(stdout.split('\n')):
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

def _normalize_title(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\b(season|part|cour|tv)\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized

def _title_similarity_score(source_title: str, candidate_title: str) -> float:
    source = _normalize_title(source_title)
    candidate = _normalize_title(candidate_title)
    if not source or not candidate:
        return 0.0
    if source == candidate:
        return 1.0
    if source in candidate or candidate in source:
        shorter = min(len(source), len(candidate))
        longer = max(len(source), len(candidate))
        return shorter / longer

    source_tokens = set(source.split())
    candidate_tokens = set(candidate.split())
    if not source_tokens or not candidate_tokens:
        return 0.0
    overlap = len(source_tokens & candidate_tokens)
    union = len(source_tokens | candidate_tokens)
    return overlap / union if union else 0.0

async def _map_single_release(item: dict, semaphore: asyncio.Semaphore | None = None) -> dict:
    """Helper to map a single release item to a MAL ID with persistent caching."""
    db = get_db()
    from backend.services import jikan_service
    
    title = item["title"]
    title_normalized = _normalize_title(title)
    # 1. Try finding in existing Re:ANIME mappings first (exact title match)
    existing = await db["provider_mappings"].find_one({
        "provider": "reanime",
        "$or": [
            {"title_normalized": title_normalized},
            {"title": title},
        ],
    })
    existing_mal_id = existing.get("mal_id") if existing else None
    if isinstance(existing_mal_id, int) and existing_mal_id > 0:
        item["mal_id"] = existing_mal_id
        return item
    if _mapping_retry_active(existing):
        return item

    # 2. Not in cache, try Jikan search
    try:
        async def _lookup():
            return await jikan_service.search_anime(query=title, limit=5)

        if semaphore is None:
            search_res = await _lookup()
        else:
            async with semaphore:
                search_res = await _lookup()

        if search_res["data"]:
            best_match = None
            best_score = 0.0
            for candidate in search_res["data"]:
                score = max(
                    _title_similarity_score(title, candidate.title or ""),
                    _title_similarity_score(title, candidate.title_english or ""),
                    _title_similarity_score(title, candidate.title_japanese or ""),
                )
                if score > best_score:
                    best_match = candidate
                    best_score = score

            if best_match and best_score >= 0.72:
                mal_id = best_match.id
                item["mal_id"] = mal_id
                
                # 3. CRITICAL: Cache this mapping for future instant lookups
                await db["provider_mappings"].update_one(
                    {"provider": "reanime", "title_normalized": title_normalized},
                    {"$set": {
                        "title": title,
                        "title_normalized": title_normalized,
                        "mal_id": mal_id,
                        "anilist_id": mal_id,
                        "slug": item.get("slug"),
                        "provider": "reanime",
                        "last_mapped_at": datetime.now(timezone.utc).isoformat(),
                        "mapping_retry_after": None,
                        "mapping_status": "ok",
                    }},
                    upsert=True
                )
            else:
                await db["provider_mappings"].update_one(
                    {"provider": "reanime", "title_normalized": title_normalized},
                    {"$set": {
                        "title": title,
                        "title_normalized": title_normalized,
                        "provider": "reanime",
                        "mapping_status": "not_found",
                        "mapping_retry_after": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
                    }},
                    upsert=True,
                )
    except Exception as e:
        status = "rate_limited" if "429" in str(e) else "lookup_failed"
        retry_ttl = timedelta(minutes=5) if status == "rate_limited" else timedelta(hours=1)
        await db["provider_mappings"].update_one(
            {"provider": "reanime", "title_normalized": title_normalized},
            {"$set": {
                "title": title,
                "title_normalized": title_normalized,
                "provider": "reanime",
                "mapping_status": status,
                "mapping_retry_after": (datetime.now(timezone.utc) + retry_ttl).isoformat(),
            }},
            upsert=True,
        )
        print(f"[Re:ANIME Service] Mapping failed for {title}: {e}")
    
    return item

async def _map_latest_release_results(result: list[dict]) -> list[dict]:
    """Attach MAL IDs with small bounded concurrency to avoid slow serial mapping."""
    semaphore = asyncio.Semaphore(MAPPING_LOOKUP_CONCURRENCY)
    return await asyncio.gather(*(_map_single_release(item, semaphore) for item in result))

async def refresh_latest_releases(force: bool = False) -> list[dict]:
    """Refresh the cached Re:ANIME latest releases list when stale."""
    async with _latest_releases_lock:
        db = get_db()
        cache_key = "latest_releases_reanime"
        cached_doc = await db["cache"].find_one({"key": cache_key})
        
        if not force and cached_doc:
            updated_at = cached_doc.get("updated_at")
            if updated_at:
                if isinstance(updated_at, str):
                    updated_at_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                else:
                    updated_at_dt = updated_at
                
                if datetime.now(timezone.utc) - updated_at_dt < LATEST_RELEASES_REFRESH_INTERVAL:
                    return cached_doc.get("data", [])

        print(f"[Re:ANIME Service] Refreshing latest releases...")
        new_items = await _run_scraper_subprocess("reanime_latest", {})
        
        if new_items and isinstance(new_items, list):
            # Map the new items (find MAL IDs)
            mapped_new = await _map_latest_release_results(new_items)
            
            # Cache the results
            await db["cache"].update_one(
                {"key": cache_key},
                {"$set": {
                    "data": mapped_new,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }},
                upsert=True
            )
            return mapped_new
            
        await db["cache"].update_one(
            {"key": cache_key},
            {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
        return cached_doc.get("data", []) if cached_doc else []

async def get_latest_releases() -> list[dict]:
    """Read latest Re:ANIME releases from cache without scraping on request."""
    db = get_db()
    cached_doc = await db["cache"].find_one({"key": "latest_releases_reanime"})
    return cached_doc.get("data", []) if cached_doc else []

async def latest_releases_scheduler():
    """Keep the Re:ANIME latest releases cache warm in the background."""
    print("[Re:ANIME Service] Latest releases scheduler starting...")
    await refresh_latest_releases(force=False)

    while True:
        try:
            await asyncio.sleep(int(LATEST_RELEASES_REFRESH_INTERVAL.total_seconds()))
            await refresh_latest_releases(force=True)
        except Exception as e:
            print(f"[Re:ANIME Service] Latest releases scheduler error: {e}")
            await asyncio.sleep(60)
