"""
Anime Discovery Engine -- AniZone Scraper Service
Extracts HLS stream URLs and subtitles from AniZone.

IMPORTANT: On Windows, Playwright cannot spawn Chromium from inside Uvicorn's
event loop. All Playwright calls are dispatched to a separate Python process
via `subprocess`. This avoids the `NotImplementedError` on
`asyncio.create_subprocess_exec`.
"""
import asyncio
import json
import subprocess
import sys
import os
from backend.database import get_db
from backend.models.schemas import SubtitleTrack


# Path to the scraper runner script
SCRAPER_RUNNER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scraper_runner.py")


async def _build_anizone_title_candidates(mal_id: int | None, fallback_title: str) -> list[str]:
    candidates: list[str] = []
    if fallback_title:
        candidates.append(fallback_title)

    if mal_id:
        try:
            from backend.services.jikan_service import get_anime_detail

            detail = await get_anime_detail(mal_id)
            for candidate in [detail.title, detail.title_english, detail.title_japanese]:
                if candidate and candidate not in candidates:
                    candidates.append(candidate)
        except Exception as e:
            print(f"[AniZone] Failed to load title variants for {mal_id}: {e}")

    return candidates


async def search_anizone_by_title(title: str, mal_id: int = None):
    """
    Searches AniZone for an anime by its title and returns the URL.
    Checks DB cache first if mal_id is provided.
    """
    db = get_db()
    
    # Check cache first
    if mal_id:
        cached = await db["provider_mappings"].find_one({"mal_id": mal_id, "provider": "anizone"})
        if cached:
            return cached["url"]

    candidates = await _build_anizone_title_candidates(mal_id, title)
    if not candidates:
        return None

    for idx, candidate in enumerate(candidates, start=1):
        label = f"{candidate} ({idx}/{len(candidates)})" if len(candidates) > 1 else candidate
        print(f"[AniZone] Searching for: {label}")
        try:
            result = await _run_scraper_subprocess("anizone_search", {"title": candidate})
            if result and result.get("url"):
                url = result["url"]
                print(f"[AniZone] Found: {url}")

                # Cache the mapping
                if mal_id:
                    await db["provider_mappings"].update_one(
                        {"mal_id": mal_id, "provider": "anizone"},
                        {"$set": {"url": url, "title": candidate}},
                        upsert=True
                    )
                return url
        except Exception as e:
            print(f"[AniZone] Search error for {candidate}: {e}")
    return None


async def discover_anizone(mal_id: int, title: str):
    """Unified discovery task: Search then Scrape."""
    url = await search_anizone_by_title(title, mal_id)
    if url:
        await scrape_anizone_anime(url, mal_id)
    else:
        print(f"[AniZone] Discovery failed for {title}: Could not find URL")


async def discover_anizone_episode(mal_id: int, title: str, ep_number: int):
    """Fast path for first play: search AniZone, then scrape only one episode."""
    url = await search_anizone_by_title(title, mal_id)
    if url:
        await scrape_anizone_episode(url, mal_id, ep_number)
    else:
        print(f"[AniZone] Single-episode discovery failed for {title}: Could not find URL")


async def scrape_anizone_anime(url: str, mal_id: int):
    """
    Scrapes HLS streaming links from AniZone.
    Runs as a subprocess, then stores results in MongoDB.
    """
    print(f"[AniZone] Scraping: {url}")

    try:
        result = await _run_scraper_subprocess("anizone_scrape", {"url": url})
        if not result or not result.get("episodes"):
            print(f"[AniZone] No episodes scraped from {url}")
            return []

        episodes_data = result["episodes"]

        # Store in DB
        db = get_db()
        for ep in episodes_data:
            await db["streams"].update_one(
                {"anilist_id": mal_id, "episode": ep["ep_number"], "source": "anizone"},
                {"$set": {
                    "anilist_id": mal_id,
                    "mal_id": mal_id,  # Ensure mal_id is also set for indexing
                    "episode": ep["ep_number"],
                    "source": "anizone",
                    "stream_url": ep.get("stream_url"),
                    "subtitles": ep.get("subtitles", []),
                    "updated_at": "resolved",
                    "referer_url": ep.get("referer_url"),
                }},
                upsert=True
            )

        print(f"[AniZone] Saved {len(episodes_data)} episodes for MAL ID {mal_id}")
        return episodes_data
    except Exception as e:
        print(f"[AniZone] Scrape error: {e}")
        return []


async def scrape_anizone_episode(url: str, mal_id: int, ep_number: int):
    """Scrape and store only one AniZone episode."""
    print(f"[AniZone] Scraping single episode {ep_number} from {url}")

    try:
        result = await _run_scraper_subprocess("anizone_episode", {
            "url": url,
            "episode_number": ep_number
        })
        if not result or not result.get("episodes"):
            print(f"[AniZone] No single-episode result for {url} Ep {ep_number}")
            return []

        db = get_db()
        for ep in result["episodes"]:
            await db["streams"].update_one(
                {"anilist_id": mal_id, "episode": ep["ep_number"], "source": "anizone"},
                {"$set": {
                    "anilist_id": mal_id,
                    "mal_id": mal_id,
                    "episode": ep["ep_number"],
                    "source": "anizone",
                    "stream_url": ep.get("stream_url"),
                    "subtitles": ep.get("subtitles", []),
                    "updated_at": "resolved",
                    "referer_url": ep.get("referer_url"),
                }},
                upsert=True
            )

        print(f"[AniZone] Saved single episode {ep_number} for MAL ID {mal_id}")
        return result["episodes"]
    except Exception as e:
        print(f"[AniZone] Single-episode scrape error: {e}")
        return []


async def get_stream_for_episode(mal_id: int, ep_number: int):
    """Check DB for a cached AniZone stream."""
    db = get_db()
    return await db["streams"].find_one({
        "anilist_id": mal_id,
        "episode": ep_number,
        "source": "anizone"
    })


async def _run_scraper_subprocess(action: str, params: dict) -> dict | None:
    """
    Run a scraper action in a separate Python process.
    This is REQUIRED on Windows because Playwright needs ProactorEventLoop
    for subprocess creation, but Uvicorn uses SelectorEventLoop.
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
            timeout=120,  # 2 minutes max
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )

        if proc.returncode != 0:
            print(f"[Subprocess] Error (exit {proc.returncode}): {proc.stderr[:500]}")
            return None

        # The runner prints JSON to stdout as the last line
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
