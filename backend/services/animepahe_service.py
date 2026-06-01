"""
AnimePahe Service -- Backend integration layer.

Uses subprocess-based scraping to bypass DDoS-Guard and avoid
Windows asyncio event loop conflicts with Playwright.
"""
import asyncio
import json
import subprocess
import sys
import os
import time
import re
from datetime import datetime, timedelta, timezone
from typing import Optional
from backend.database import get_db


SCRAPER_RUNNER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "scraper_runner.py")
AIRING_CATALOG_REFRESH_INTERVAL = timedelta(hours=4)
COMPLETED_CATALOG_REFRESH_INTERVAL = timedelta(days=3)
UPCOMING_CATALOG_REFRESH_INTERVAL = timedelta(hours=12)
SCHEDULER_REFRESH_INTERVAL_SECONDS = 30 * 60
LATEST_RELEASES_REFRESH_INTERVAL = timedelta(minutes=10)
_refresh_locks: dict[int, asyncio.Lock] = {}
_active_refreshes: set[int] = set()
_latest_releases_lock = asyncio.Lock()
MAPPING_LOOKUP_DELAY_SECONDS = 0.45
_stream_locks: dict[str, asyncio.Lock] = {}
_embed_locks: dict[str, asyncio.Lock] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _from_unix_timestamp(value: int | float | None) -> str | None:
    if not value:
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
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


async def _get_search_title_candidates(anilist_id: int, fallback_title: str) -> list[str]:
    titles: list[str] = []
    for candidate in [fallback_title]:
        if candidate and candidate not in titles:
            titles.append(candidate)

    try:
        from backend.services.jikan_service import get_anime_detail as get_jikan_anime_detail

        detail = await get_jikan_anime_detail(anilist_id)
        for candidate in [
            detail.title,
            detail.title_english,
            detail.title_japanese,
        ]:
            if candidate and candidate not in titles:
                titles.append(candidate)
    except Exception as e:
        print(f"[AnimePahe Service] Failed to build title candidates for {anilist_id}: {e}")

    return titles


def _result_episode_count(result: dict | None) -> int:
    if not result:
        return 0
    return _get_latest_episode(result.get("episodes", []))


def _catalog_looks_poisoned(result: dict | None, expected_total: int) -> bool:
    if not result:
        return True
    latest_episode = _result_episode_count(result)
    if latest_episode <= 1 and expected_total >= 6:
        return True
    if latest_episode > 0 and expected_total >= 12 and latest_episode <= max(2, expected_total // 4):
        return True
    return False


async def _run_animepahe_episode_with_recovery(
    anilist_id: int,
    title: str,
    ep_number: int,
    session_id: str | None,
    offset: int,
) -> dict | None:
    candidates = await _get_search_title_candidates(anilist_id, title)
    expected_total = 0
    try:
        from backend.services.jikan_service import get_anime_detail as get_jikan_anime_detail

        detail = await get_jikan_anime_detail(anilist_id)
        expected_total = int(detail.episodes or 0)
    except Exception as e:
        print(f"[AnimePahe Service] Failed to fetch expected episode count for {anilist_id}: {e}")

    primary_title = candidates[0] if candidates else title
    result = await _run_scraper_subprocess("animepahe_episode", {
        "title": primary_title,
        "episode_number": ep_number,
        "session_id": session_id,
        "offset": offset
    })

    should_retry_without_session = False
    if session_id:
        if not result or not result.get("episode"):
            should_retry_without_session = True
            print(
                f"[AnimePahe Service] Cached session failed to resolve episode {ep_number} "
                f"for {title}. Retrying without session."
            )
        elif _catalog_looks_poisoned(result, expected_total):
            should_retry_without_session = True

    if should_retry_without_session:
        print(
            f"[AnimePahe Service] Cached AnimePahe session looks wrong for {title} "
            f"(expected ~{expected_total} eps, got {_result_episode_count(result)}). Retrying without session."
        )
        for candidate in candidates:
            retry_result = await _run_scraper_subprocess("animepahe_episode", {
                "title": candidate,
                "episode_number": ep_number,
                "offset": offset
            })
            if retry_result and retry_result.get("episode"):
                return retry_result
            if not _catalog_looks_poisoned(retry_result, expected_total):
                return retry_result

    return result


async def _run_animepahe_catalog_with_recovery(
    anilist_id: int,
    title: str,
    session_id: str | None,
    offset: int,
) -> dict | None:
    candidates = await _get_search_title_candidates(anilist_id, title)
    expected_total = 0
    try:
        from backend.services.jikan_service import get_anime_detail as get_jikan_anime_detail

        detail = await get_jikan_anime_detail(anilist_id)
        expected_total = int(detail.episodes or 0)
    except Exception as e:
        print(f"[AnimePahe Service] Failed to fetch expected episode count for {anilist_id}: {e}")

    primary_title = candidates[0] if candidates else title
    result = await _run_scraper_subprocess("animepahe_catalog", {
        "title": primary_title,
        "session_id": session_id,
        "offset": offset,
    })

    if session_id and _catalog_looks_poisoned(result, expected_total):
        print(
            f"[AnimePahe Service] Cached AnimePahe catalog session looks wrong for {title} "
            f"(expected ~{expected_total} eps, got {_result_episode_count(result)}). Retrying without session."
        )
        for candidate in candidates:
            retry_result = await _run_scraper_subprocess("animepahe_catalog", {
                "title": candidate,
                "offset": offset,
            })
            if retry_result and not _catalog_looks_poisoned(retry_result, expected_total):
                return retry_result

    return result


def _interval_for_mapping(mapping: dict | None) -> timedelta:
    if not mapping:
        return AIRING_CATALOG_REFRESH_INTERVAL

    provider_status = (mapping.get("provider_status") or "").upper()
    if mapping.get("is_airing") or provider_status == "RELEASING":
        return AIRING_CATALOG_REFRESH_INTERVAL
    if provider_status in {"NOT_YET_RELEASED", "UPCOMING"}:
        return UPCOMING_CATALOG_REFRESH_INTERVAL
    return COMPLETED_CATALOG_REFRESH_INTERVAL


def _get_latest_episode(episodes: list[dict]) -> int:
    numbers = []
    for episode in episodes:
        try:
            numbers.append(int(episode["ep_number"]))
        except (KeyError, TypeError, ValueError):
            continue
    return max(numbers) if numbers else 0


def _is_catalog_stale(mapping: dict | None) -> bool:
    if not mapping:
        return True

    last_checked = mapping.get("last_catalog_check_at")
    if not last_checked:
        return True

    last_checked_at = _parse_iso_datetime(last_checked)
    if not last_checked_at:
        return True

    return datetime.now(timezone.utc) - last_checked_at >= _interval_for_mapping(mapping)


def _is_next_airing_refresh_due(mapping: dict | None) -> bool:
    if not mapping:
        return False

    next_airing_episode = int(mapping.get("next_airing_episode", 0) or 0)
    latest_episode = int(mapping.get("latest_episode", 0) or 0)
    if next_airing_episode <= 0 or latest_episode >= next_airing_episode:
        return False

    next_airing_at = _parse_iso_datetime(mapping.get("next_airing_at"))
    if not next_airing_at:
        return False

    return datetime.now(timezone.utc) >= next_airing_at


def _get_refresh_lock(anilist_id: int) -> asyncio.Lock:
    lock = _refresh_locks.get(anilist_id)
    if lock is None:
        lock = asyncio.Lock()
        _refresh_locks[anilist_id] = lock
    return lock


def is_animepahe_refresh_in_progress(anilist_id: int) -> bool:
    return anilist_id in _active_refreshes


def is_animepahe_catalog_stale(mapping: dict | None) -> bool:
    return _is_catalog_stale(mapping)


def is_animepahe_release_refresh_due(mapping: dict | None) -> bool:
    return _is_next_airing_refresh_due(mapping)


async def _fetch_airing_schedule_fields(anilist_id: int) -> dict:
    try:
        from backend.services.anilist_service import get_airing_schedule_by_mal_id

        data = await get_airing_schedule_by_mal_id(anilist_id)
        return {
            "provider_status": data.get("provider_status"),
            "is_airing": data.get("is_airing"),
            "next_airing_episode": data.get("next_airing_episode"),
            "next_airing_at": _from_unix_timestamp(data.get("next_airing_at")),
        }
    except Exception as e:
        print(f"[AnimePahe Service] Failed to fetch AniList schedule for {anilist_id}: {e}")
        return {}


async def _mark_refresh_started(anilist_id: int, title: str):
    db = get_db()
    await db["provider_mappings"].update_one(
        {"mal_id": anilist_id, "provider": "animepahe"},
        {"$set": {
            "title": title,
            "refreshing": True,
            "refresh_started_at": _utc_now_iso(),
            "provider": "animepahe",
        }},
        upsert=True,
    )


async def _mark_refresh_finished(
    anilist_id: int,
    success: bool,
    duration_ms: int,
    error_message: str | None = None,
):
    db = get_db()
    payload = {
        "refreshing": False,
        "last_scrape_duration_ms": duration_ms,
    }
    if success:
        payload["last_success_at"] = _utc_now_iso()
        payload["last_scrape_error"] = None
    elif error_message:
        payload["last_scrape_error"] = error_message[:400]

    await db["provider_mappings"].update_one(
        {"mal_id": anilist_id, "provider": "animepahe"},
        {"$set": payload, "$unset": {"refresh_started_at": ""}},
        upsert=True,
    )


async def _save_provider_mapping(
    anilist_id: int,
    title: str,
    session: str | None,
    latest_episode: int = 0,
    schedule_fields: dict | None = None,
):
    db = get_db()
    payload = {
        "title": title,
        "title_normalized": _normalize_title(title),
        "last_catalog_check_at": _utc_now_iso(),
        "provider": "animepahe",
    }
    if session:
        payload["session"] = session
    if latest_episode:
        payload["latest_episode"] = latest_episode
    if schedule_fields:
        payload.update({k: v for k, v in schedule_fields.items() if v is not None})

    await db["provider_mappings"].update_one(
        {"mal_id": anilist_id, "provider": "animepahe"},
        {"$set": payload},
        upsert=True
    )


async def _upsert_animepahe_stream_record(
    db,
    anilist_id: int,
    episode_number: int,
    session: str | None,
    episode_session: str | None,
    snapshot: str | None,
    stream_url: str | None,
    embed_url: str | None = None,
):
    """
    Preserve an existing resolved stream URL when a metadata refresh only knows
    the episode/session identifiers for that row.
    """
    existing = await db["streams"].find_one(
        {"anilist_id": anilist_id, "episode": episode_number, "source": "animepahe"},
        {"stream_url": 1, "embed_url": 1}
    )
    existing = existing or {}
    normalized_stream_url = stream_url
    normalized_embed_url = embed_url

    if normalized_stream_url and "kwik" in normalized_stream_url.lower():
        normalized_embed_url = normalized_stream_url
        normalized_stream_url = None

    preserved_stream_url = normalized_stream_url or existing.get("stream_url")
    preserved_embed_url = normalized_embed_url or existing.get("embed_url")

    await db["streams"].update_one(
        {"anilist_id": anilist_id, "episode": episode_number, "source": "animepahe"},
        {"$set": {
            "anilist_id": anilist_id,
            "mal_id": anilist_id,
            "episode": episode_number,
            "source": "animepahe",
            "provider_id": session,
            "episode_id": episode_session,
            "stream_url": preserved_stream_url,
            "embed_url": preserved_embed_url,
            "snapshot": snapshot,
            "updated_at": "resolved" if preserved_stream_url else "metadata"
        }},
        upsert=True
    )


async def scrape_animepahe_full(anilist_id: int, title: str):
    """
    Full discovery pipeline: search + episode catalogue.
    Runs as a separate process, stores results in MongoDB.
    """
    print(f"[AnimePahe Service] Starting discovery for: {title} (ID: {anilist_id})")

    db = get_db()
    mapping = await db["provider_mappings"].find_one({"mal_id": anilist_id, "provider": "animepahe"})
    session_id = mapping.get("session") if mapping else None

    started_at = time.perf_counter()
    await _mark_refresh_started(anilist_id, title)
    try:
        result = await _run_scraper_subprocess("animepahe_full", {
            "title": title,
            "max_episodes": 0,
            "session_id": session_id
        })

        if not result or not result.get("episodes"):
            print(f"[AnimePahe Service] No episodes found for {title}")
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            await _mark_refresh_finished(
                anilist_id,
                success=False,
                duration_ms=duration_ms,
                error_message="No episodes found during catalog refresh",
            )
            return

        from backend.services.jikan_service import get_prequel_episode_offset
        offset = await get_prequel_episode_offset(anilist_id)
        if offset > 0:
            print(f"[AnimePahe Service] Detected prequel offset of {offset} episodes for ID {anilist_id}")

        db = get_db()
        session = result.get("session")
        
        # Apply offset to episode numbers if needed
        mapped_episodes = []
        for ep in result["episodes"]:
            provider_ep = float(ep.get("provider_ep_number") or ep["ep_number"])
            if offset > 0:
                if provider_ep <= offset:
                    continue
                ep["ep_number"] = int(provider_ep - offset)
            mapped_episodes.append(ep)

        latest_episode = _get_latest_episode(mapped_episodes)
        schedule_fields = await _fetch_airing_schedule_fields(anilist_id)
        await _save_provider_mapping(anilist_id, title, session, latest_episode, schedule_fields)

        seen_episodes = set()
        for ep in mapped_episodes:
            ep_number = int(ep["ep_number"])
            seen_episodes.add(ep_number)
            await _upsert_animepahe_stream_record(
                db=db,
                anilist_id=anilist_id,
                episode_number=ep_number,
                session=session,
                episode_session=ep.get("episode_session"),
                snapshot=ep.get("snapshot"),
                stream_url=ep.get("stream_url"),
                embed_url=ep.get("embed_url"),
            )

        if seen_episodes:
            await db["streams"].delete_many({
                "anilist_id": anilist_id,
                "source": "animepahe",
                "episode": {"$nin": list(seen_episodes)}
            })
            print(f"[AnimePahe Service] Saved {len(seen_episodes)} episode records for {title}")
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        await _mark_refresh_finished(anilist_id, success=True, duration_ms=duration_ms)

    except Exception as e:
        print(f"[AnimePahe Service] Error: {e}")
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        await _mark_refresh_finished(anilist_id, success=False, duration_ms=duration_ms, error_message=str(e))


async def scrape_animepahe_episode(anilist_id: int, title: str, ep_number: int):
    """
    Fast path for first play: resolve just one requested episode instead of
    cataloguing the whole show.
    """
    print(f"[AnimePahe Service] Starting single-episode discovery for: {title} Ep {ep_number}")

    db = get_db()
    mapping = await db["provider_mappings"].find_one({"mal_id": anilist_id, "provider": "animepahe"})
    session_id = mapping.get("session") if mapping else None

    from backend.services.jikan_service import get_prequel_episode_offset
    offset = await get_prequel_episode_offset(anilist_id)
    
    started_at = time.perf_counter()
    await _mark_refresh_started(anilist_id, title)
    try:
        print(f"[AnimePahe Service] Using session_id={session_id!r} for MAL {anilist_id}")
        result = await _run_animepahe_episode_with_recovery(
            anilist_id=anilist_id,
            title=title,
            ep_number=ep_number,
            session_id=session_id,
            offset=offset,
        )

        if not result:
            print(f"[AnimePahe Service] Scraper returned no result for {title} Ep {ep_number}")
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            await _mark_refresh_finished(
                anilist_id,
                success=False,
                duration_ms=duration_ms,
                error_message=f"No result for episode {ep_number}",
            )
            return

        session = result.get("session")
        episode = result.get("episode")
        episodes = result.get("episodes", [])

        latest_episode = _get_latest_episode(episodes)
        schedule_fields = await _fetch_airing_schedule_fields(anilist_id)
        await _save_provider_mapping(anilist_id, title, session, latest_episode, schedule_fields)

        if not episode:
            print(f"[AnimePahe Service] Episode {ep_number} not found for {title}")
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            await _mark_refresh_finished(anilist_id, success=True, duration_ms=duration_ms)
            return

        stored_numbers = set()
        for episode_meta in episodes:
            ep_num = int(episode_meta["ep_number"])
            stored_numbers.add(ep_num)
            await _upsert_animepahe_stream_record(
                db=db,
                anilist_id=anilist_id,
                episode_number=ep_num,
                session=session,
                episode_session=episode_meta.get("episode_session"),
                snapshot=episode_meta.get("snapshot"),
                stream_url=episode_meta.get("stream_url"),
                embed_url=episode_meta.get("embed_url"),
            )

        requested_ep = int(episode["ep_number"])
        if requested_ep not in stored_numbers:
            await _upsert_animepahe_stream_record(
                db=db,
                anilist_id=anilist_id,
                episode_number=requested_ep,
                session=session,
                episode_session=episode.get("episode_session"),
                snapshot=episode.get("snapshot"),
                stream_url=episode.get("stream_url"),
                embed_url=episode.get("embed_url"),
            )

        print(f"[AnimePahe Service] Saved {max(len(episodes), 1)} episode records for {title}")
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        await _mark_refresh_finished(anilist_id, success=True, duration_ms=duration_ms)
    except Exception as e:
        print(f"[AnimePahe Service] Single-episode error: {e}")
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        await _mark_refresh_finished(anilist_id, success=False, duration_ms=duration_ms, error_message=str(e))


async def scrape_animepahe_catalog_metadata(anilist_id: int, title: str):
    """
    Refresh only AnimePahe episode metadata without resolving a playable stream.
    Used by manual refreshes and the background scheduler.
    """
    print(f"[AnimePahe Service] Refreshing metadata catalog for: {title} (ID: {anilist_id})")
    db = get_db()
    mapping = await db["provider_mappings"].find_one({"mal_id": anilist_id, "provider": "animepahe"})
    session_id = mapping.get("session") if mapping else None

    started_at = time.perf_counter()
    await _mark_refresh_started(anilist_id, title)
    try:
        from backend.services.jikan_service import get_prequel_episode_offset

        offset = await get_prequel_episode_offset(anilist_id)
        result = await _run_animepahe_catalog_with_recovery(
            anilist_id=anilist_id,
            title=title,
            session_id=session_id,
            offset=offset,
        )
        episodes = result.get("episodes", []) if result else []
        session = result.get("session") if result else session_id
        latest_episode = _get_latest_episode(episodes)
        schedule_fields = await _fetch_airing_schedule_fields(anilist_id)
        await _save_provider_mapping(anilist_id, title, session, latest_episode, schedule_fields)

        seen_episodes = set()
        for episode_meta in episodes:
            ep_num = int(episode_meta["ep_number"])
            seen_episodes.add(ep_num)
            await _upsert_animepahe_stream_record(
                db=db,
                anilist_id=anilist_id,
                episode_number=ep_num,
                session=session,
                episode_session=episode_meta.get("episode_session"),
                snapshot=episode_meta.get("snapshot"),
                stream_url=episode_meta.get("stream_url"),
                embed_url=episode_meta.get("embed_url"),
            )

        if seen_episodes:
            await db["streams"].delete_many({
                "anilist_id": anilist_id,
                "source": "animepahe",
                "episode": {"$nin": list(seen_episodes)}
            })

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        await _mark_refresh_finished(anilist_id, success=True, duration_ms=duration_ms)
    except Exception as e:
        print(f"[AnimePahe Service] Metadata refresh error: {e}")
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        await _mark_refresh_finished(anilist_id, success=False, duration_ms=duration_ms, error_message=str(e))


async def refresh_animepahe_catalog(
    anilist_id: int,
    title: str,
    preferred_episode: int = 1,
    resolve_stream: bool = True,
):
    """
    Refresh AnimePahe metadata when cached catalog is stale or a newer episode may exist.
    Reuses the single-episode path so we still resolve a playable stream for the preferred episode.
    """
    print(f"[AnimePahe Service] Refreshing catalog for: {title} (ID: {anilist_id}, preferred Ep {preferred_episode})")
    lock = _get_refresh_lock(anilist_id)
    if lock.locked():
        print(f"[AnimePahe Service] Refresh already in progress for {anilist_id}, skipping duplicate trigger")
        return

    async with lock:
        _active_refreshes.add(anilist_id)
        try:
            if resolve_stream:
                await scrape_animepahe_episode(anilist_id, title, preferred_episode)
            else:
                await scrape_animepahe_catalog_metadata(anilist_id, title)
        finally:
            _active_refreshes.discard(anilist_id)


async def get_animepahe_mapping(anilist_id: int) -> dict | None:
    db = get_db()
    return await db["provider_mappings"].find_one({"mal_id": anilist_id, "provider": "animepahe"})


async def should_refresh_animepahe_catalog(anilist_id: int, requested_episode: int, expected_total: int = 0, force_refresh: bool = False) -> tuple[bool, dict | None]:
    mapping = await get_animepahe_mapping(anilist_id)
    if force_refresh:
        # If forced (e.g. user explicitly requested AnimePahe but stream is missing),
        # only throttle for 1 minute to prevent spamming, but bypass the normal 4+ hour cache
        if mapping and mapping.get("last_catalog_check_at"):
            last_check = _parse_iso_datetime(mapping.get("last_catalog_check_at"))
            if last_check and datetime.now(timezone.utc) - last_check < timedelta(minutes=1):
                return False, mapping
        return True, mapping

    if _is_next_airing_refresh_due(mapping):
        next_airing_episode = int(mapping.get("next_airing_episode", 0) or 0) if mapping else 0
        if next_airing_episode <= 0 or requested_episode >= next_airing_episode:
            return True, mapping

    if _is_catalog_stale(mapping):
        return True, mapping

    latest_episode = int(mapping.get("latest_episode", 0) or 0) if mapping else 0
    
    # If the user is requesting an episode beyond what we've found
    if requested_episode > latest_episode:
        return True, mapping

    is_airing = bool(mapping.get("is_airing")) if mapping else False

    # If we have significantly fewer episodes than Jikan/AniList says exist
    # (e.g. we have 300 but there should be 1100), trigger a refresh to pick up the new 100-page limit.
    # Skip this for airing shows because Jikan's total is often the planned season count, not aired count.
    if (
        not is_airing
        and expected_total > 0
        and latest_episode < expected_total
        and latest_episode <= 300
    ):
        print(f"[AnimePahe Service] Found only {latest_episode} episodes, but expected ~{expected_total}. Forcing refresh.")
        return True, mapping

    return False, mapping


async def refresh_airing_animepahe_catalogs():
    """Background sweep to keep airing catalogs warm without resolving streams."""
    db = get_db()
    cursor = db["provider_mappings"].find({"provider": "animepahe", "is_airing": True})
    async for mapping in cursor:
        mal_id = mapping.get("mal_id")
        title = mapping.get("title")
        if not mal_id or not title or is_animepahe_refresh_in_progress(mal_id):
            continue
        release_due = _is_next_airing_refresh_due(mapping)
        is_stale = _is_catalog_stale(mapping)
        if not release_due and not is_stale:
            continue
        try:
            await refresh_animepahe_catalog(mal_id, title, preferred_episode=mapping.get("latest_episode", 1) or 1, resolve_stream=False)
        except Exception as e:
            print(f"[AnimePahe Service] Scheduled refresh failed for {mal_id}: {e}")


async def animepahe_catalog_scheduler():
    """Periodically refresh airing AnimePahe mappings."""
    while True:
        try:
            await refresh_airing_animepahe_catalogs()
        except Exception as e:
            print(f"[AnimePahe Service] Scheduler loop error: {e}")
        await asyncio.sleep(SCHEDULER_REFRESH_INTERVAL_SECONDS)


async def refresh_trending_animepahe_catalogs():
    """Background sweep to keep trending catalogs warm."""
    try:
        from backend.services.anilist_service import get_trending
        # Fetch top 2 pages of trending (~50 anime)
        for page in [1, 2]:
            result = await get_trending(page=page)
            data = result.get("data", [])
            for item in data:
                mal_id = item.get("mal_id") or item.get("id")
                title = item.get("title")
                if not mal_id or not title or is_animepahe_refresh_in_progress(mal_id):
                    continue
                try:
                    await refresh_animepahe_catalog(mal_id, title, preferred_episode=1, resolve_stream=False)
                    # Sleep slightly to avoid hammering Jikan and scrapers
                    await asyncio.sleep(2)
                except Exception as e:
                    print(f"[AnimePahe Service] Trending scheduled refresh failed for {mal_id}: {e}")
    except Exception as e:
        print(f"[AnimePahe Service] Trending sweep error: {e}")

async def trending_catalog_scheduler():
    """Periodically refresh trending AnimePahe mappings (every 1 hour)."""
    while True:
        try:
            await refresh_trending_animepahe_catalogs()
        except Exception as e:
            print(f"[AnimePahe Service] Trending scheduler loop error: {e}")
        # Run every 1 hour (3600 seconds)
        await asyncio.sleep(3600)

async def _map_single_release(item: dict) -> dict:
    """Helper to map a single release item to a MAL ID with persistent caching."""
    db = get_db()
    from backend.services import jikan_service
    
    title = item["title"]
    title_normalized = _normalize_title(title)
    # 1. Try finding in existing mappings first
    existing = await db["provider_mappings"].find_one({
        "provider": "animepahe",
        "$or": [
            {"title_normalized": title_normalized},
            {"title": title},
        ],
    })
    if existing and isinstance(existing.get("mal_id"), int):
        item["mal_id"] = existing["mal_id"]
    elif existing and existing.get("mapping_retry_after") and _parse_iso_datetime(existing.get("mapping_retry_after")) and _parse_iso_datetime(existing.get("mapping_retry_after")) > datetime.now(timezone.utc):
        pass
    else:
        try:
            # 2. Not in cache, try Jikan search
            search_res = await jikan_service.search_anime(query=title, limit=5)
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
                    
                    # 3. Cache this mapping for future instant lookups
                    await db["provider_mappings"].update_one(
                        {"provider": "animepahe", "title_normalized": title_normalized},
                        {"$set": {
                            "title": title,
                            "title_normalized": title_normalized,
                            "mal_id": mal_id,
                            "session": item.get("session"),
                            "provider": "animepahe",
                            "last_mapped_at": datetime.now(timezone.utc).isoformat(),
                            "mapping_retry_after": None,
                            "mapping_status": "ok",
                        }},
                        upsert=True
                    )
                else:
                    await db["provider_mappings"].update_one(
                        {"provider": "animepahe", "title_normalized": title_normalized},
                        {"$set": {
                            "title": title,
                            "title_normalized": title_normalized,
                            "provider": "animepahe",
                            "mapping_status": "not_found",
                            "mapping_retry_after": (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat(),
                        }},
                        upsert=True
                    )
        except Exception as e:
            status = "rate_limited" if "429" in str(e) else "lookup_failed"
            retry_ttl = timedelta(minutes=5) if status == "rate_limited" else timedelta(hours=1)
            await db["provider_mappings"].update_one(
                {"provider": "animepahe", "title_normalized": title_normalized},
                {"$set": {
                    "title": title,
                    "title_normalized": title_normalized,
                    "provider": "animepahe",
                    "mapping_status": status,
                    "mapping_retry_after": (datetime.now(timezone.utc) + retry_ttl).isoformat(),
                }},
                upsert=True
            )
            print(f"[AnimePahe Service] Mapping failed for {title}: {e}")

    # Use raw episode from provider for latest releases
    item["display_episode"] = str(item["episode"])
    return item

async def _map_latest_release_results(result: list[dict]) -> list[dict]:
    """Attach MAL IDs while pacing Jikan lookups to avoid provider rate limits."""
    mapped_results: list[dict] = []
    for index, item in enumerate(result):
        mapped_results.append(await _map_single_release(item))
        if index < len(result) - 1:
            await asyncio.sleep(MAPPING_LOOKUP_DELAY_SECONDS)
    return mapped_results


async def refresh_latest_releases(force: bool = False, pages: int = 1) -> list[dict]:
    """
    Refresh latest releases cache. 
    On schedule, we only fetch 1 page and merge. 
    On force (or startup), we fetch the full 3 pages to populate.
    """
    async with _latest_releases_lock:
        db = get_db()
        cache_key = "latest_releases"
        cached_doc = await db["cache"].find_one({"key": cache_key})
        existing_data = cached_doc.get("data", []) if cached_doc else []

        if not force and cached_doc:
            updated_at = _parse_iso_datetime(cached_doc.get("updated_at"))
            if updated_at and datetime.now(timezone.utc) - updated_at < LATEST_RELEASES_REFRESH_INTERVAL:
                return existing_data

        # If forced and no pages specified, default to 3 for a "deep" refresh
        num_pages = pages if not force else max(pages, 3)
        
        print(f"[AnimePahe Service] Refreshing latest releases ({num_pages} pages)...")
        new_items = await _run_scraper_subprocess("animepahe_latest", {"pages": num_pages})
        
        if new_items and isinstance(new_items, list):
            # Map the new items (find MAL IDs)
            mapped_new = await _map_latest_release_results(new_items)
            
            # Merge with existing data
            # Use a combination of session and episode_session as a unique key
            merged_map = {}
            
            # Add existing items first
            for item in existing_data:
                key = f"{item.get('session')}-{item.get('episode_session')}"
                merged_map[key] = item
                
            # Overwrite/Add new items
            for item in mapped_new:
                key = f"{item.get('session')}-{item.get('episode_session')}"
                merged_map[key] = item
            
            # Sort by whatever order they came in (newest first)
            # Actually, the scraper already returns them newest first.
            # We want to keep the most recent ones.
            # For simplicity, we can just sort by a proxy like index or timestamp if we had one,
            # but since we merge 'new' last, the order is preserved if we extract correctly.
            
            # A better way: just prepend new items and filter duplicates
            all_items = mapped_new + existing_data
            unique_items = []
            seen_keys = set()
            for item in all_items:
                key = f"{item.get('session')}-{item.get('episode_session')}"
                if key not in seen_keys:
                    unique_items.append(item)
                    seen_keys.add(key)
            
            # Limit to 36 items (3 pages of 12)
            final_data = unique_items[:36]
            
            await db["cache"].update_one(
                {"key": cache_key},
                {"$set": {
                    "data": final_data,
                    "updated_at": _utc_now_iso()
                }},
                upsert=True
            )
            print(f"[AnimePahe Service] Refresh complete. Cache size: {len(final_data)} (Merged {len(mapped_new)} new)")
            return final_data
        
        # Update timestamp even on empty/fail to avoid loop
        await db["cache"].update_one(
            {"key": cache_key},
            {"$set": { "updated_at": _utc_now_iso() }},
            upsert=True
        )
        return existing_data


async def get_latest_releases() -> list[dict]:
    """Read latest releases from cache without triggering a scrape on request."""
    db = get_db()
    cached = await db["cache"].find_one({"key": "latest_releases"})
    return cached.get("data", []) if cached else []


async def latest_releases_scheduler():
    """Refresh latest releases cache on a fixed timer."""
    print("[AnimePahe Service] Latest releases scheduler starting...")
    # Initial check on startup (only refresh if stale)
    await refresh_latest_releases(force=False)
    
    while True:
        try:
            # Wait for the next interval
            interval_secs = int(LATEST_RELEASES_REFRESH_INTERVAL.total_seconds())
            await asyncio.sleep(interval_secs)
            
            print(f"[AnimePahe Service] Scheduled refresh triggered (1-page delta).")
            # Scheduled refresh only fetches 1 page and merges it
            await refresh_latest_releases(force=True, pages=1)
        except Exception as e:
            print(f"[AnimePahe Service] Latest releases scheduler error: {e}")
            # Still sleep on error to avoid tight retry loops
            await asyncio.sleep(60)


async def get_animepahe_stream(session: str, episode_session: str) -> Optional[str]:
    """
    Resolve a kwik.cx embed URL for a specific episode.
    Called on-demand when a user clicks play.
    Deduplicates requests using an internal lock and DB check.
    """
    lock_key = f"{session}-{episode_session}"
    if lock_key not in _stream_locks:
        _stream_locks[lock_key] = asyncio.Lock()

    async with _stream_locks[lock_key]:
        # 1. Check DB first in case another process just resolved it
        db = get_db()
        cached = await db["streams"].find_one(
            {"provider_id": session, "episode_id": episode_session, "source": "animepahe"},
            {"stream_url": 1}
        )
        if cached and cached.get("stream_url"):
            print(f"[AnimePahe Service] Reusing cached stream for {session}/{episode_session}")
            return cached["stream_url"]

        print(f"[AnimePahe Service] Resolving stream for {session}/{episode_session}")
        try:
            result = await _run_scraper_subprocess("animepahe_stream", {
                "session": session,
                "episode_session": episode_session
            })

            if result and result.get("stream_url"):
                stream_url = result["stream_url"]
                # Save it to DB so future calls are instant
                await db["streams"].update_one(
                    {"provider_id": session, "episode_id": episode_session, "source": "animepahe"},
                    {"$set": {
                        "stream_url": stream_url,
                        "updated_at": "resolved"
                    }}
                )
                return stream_url
        except Exception as e:
            print(f"[AnimePahe Service] Stream resolve error: {e}")
        return None


async def resolve_animepahe_embed_stream(embed_url: str) -> Optional[str]:
    """
    Resolve a kwik embed URL to a direct stream URL.
    Deduplicates requests using an internal lock and DB check.
    """
    if embed_url not in _embed_locks:
        _embed_locks[embed_url] = asyncio.Lock()

    async with _embed_locks[embed_url]:
        # 1. Check DB first
        db = get_db()
        cached = await db["streams"].find_one({"embed_url": embed_url}, {"stream_url": 1})
        if cached and cached.get("stream_url"):
            # Check if it's a direct URL (not just the embed link mirrored)
            url = cached["stream_url"]
            if url and "kwik" not in url.lower() and (url.endswith(".m3u8") or url.endswith(".mp4")):
                print(f"[AnimePahe Service] Reusing cached direct stream for {embed_url}")
                return url

        print(f"[AnimePahe Service] Resolving direct stream for {embed_url}")
        try:
            result = await _run_scraper_subprocess("kwik_stream", {
                "url": embed_url,
            })
            if result and result.get("stream_url"):
                direct_url = result["stream_url"]
                # Save it to DB
                await db["streams"].update_many(
                    {"embed_url": embed_url},
                    {"$set": {
                        "stream_url": direct_url,
                        "updated_at": "resolved"
                    }}
                )
                return direct_url
        except Exception as e:
            print(f"[AnimePahe Service] Embed resolve error: {e}")
        return None


async def _run_scraper_subprocess(action: str, params: dict) -> dict | None:
    """
    Run a scraper action in a separate Python process.
    This avoids the Windows asyncio/Playwright conflict.
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
    """Synchronously run the subprocess and parse JSON output."""
    try:
        print(f"[Subprocess] Running: {cmd[1]} {cmd[2]}")
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,  # 3 minutes max (AnimePahe can be slow)
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )

        if proc.returncode != 0:
            print(f"[Subprocess] Error (exit {proc.returncode})")
            if proc.stdout.strip():
                print(f"[Subprocess] stdout:\n{proc.stdout}")
            if proc.stderr.strip():
                print(f"[Subprocess] stderr:\n{proc.stderr}")
            return None

        stdout = proc.stdout.strip()
        if not stdout:
            if proc.stderr.strip():
                print(f"[Subprocess] Empty stdout, stderr:\n{proc.stderr}")
            return None

        # Find the last JSON line in the output
        if proc.stderr.strip():
            # Print scraper logs (stderr) to console
            for line in proc.stderr.strip().split('\n'):
                print(f"[Scraper] {line}")

        for line in reversed(stdout.split('\n')):
            line = line.strip()
            if line.startswith('{') or line.startswith('['):
                return json.loads(line)

    except subprocess.TimeoutExpired:
        print("[Subprocess] Timed out after 180s")
    except json.JSONDecodeError as e:
        print(f"[Subprocess] JSON parse error: {e}")
    except Exception as e:
        print(f"[Subprocess] Error: {e}")
    return None
