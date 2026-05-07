from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from backend.database import get_db
from backend.models.schemas import CatalogStatus, StreamResponse
from backend.services.animepahe_service import (
    get_animepahe_mapping,
    is_animepahe_catalog_stale,
    is_animepahe_release_refresh_due,
    is_animepahe_refresh_in_progress,
    refresh_animepahe_catalog,
    get_animepahe_stream,
    resolve_animepahe_embed_stream,
)
from backend.services.anizone_service import discover_anizone_episode
from backend.services.jikan_service import get_anime_detail

router = APIRouter(prefix="/stream", tags=["streaming"])


SOURCE_PRIORITY = {
    "animepahe": 0,
    "anizone": 1,
}

ANIZONE_LOCK_TTL = timedelta(minutes=6)


async def _resolve_and_cache_embed_stream(db, stream_id, embed_url: str):
    try:
        direct_stream_url = await resolve_animepahe_embed_stream(embed_url)
        if direct_stream_url:
            await db["streams"].update_one(
                {"_id": stream_id},
                {"$set": {"stream_url": direct_stream_url, "embed_url": embed_url, "updated_at": "resolved"}}
            )
    except Exception as e:
        print(f"[Streaming] Background kwik resolution failed: {e}")


def _sort_stream_candidates(records: list[dict]) -> list[dict]:
    """Prefer already-playable records, then source priority."""
    return sorted(
        records,
        key=lambda record: (
            0 if record.get("stream_url") or record.get("embed_url") else 1,
            SOURCE_PRIORITY.get(record.get("source", ""), 99),
        ),
    )


async def _acquire_anizone_episode_lock(db, mal_id: int, ep_number: int) -> str | None:
    now = datetime.now(timezone.utc)
    expires_at = now + ANIZONE_LOCK_TTL
    key = f"anizone:{mal_id}:{ep_number}"

    refreshed = await db["refresh_locks"].find_one_and_update(
        {
            "key": key,
            "$or": [
                {"expires_at": {"$lte": now}},
                {"expires_at": {"$exists": False}},
            ],
        },
        {"$set": {
            "provider": "anizone",
            "mal_id": mal_id,
            "episode": ep_number,
            "expires_at": expires_at,
            "updated_at": now,
        }},
        return_document=ReturnDocument.AFTER,
    )
    if refreshed:
        return key

    try:
        await db["refresh_locks"].insert_one({
            "key": key,
            "provider": "anizone",
            "mal_id": mal_id,
            "episode": ep_number,
            "expires_at": expires_at,
            "created_at": now,
        })
        return key
    except DuplicateKeyError:
        return None


async def _release_anizone_episode_lock(db, key: str | None):
    if not key:
        return
    await db["refresh_locks"].delete_one({"key": key})


async def _run_anizone_episode_discovery(db, mal_id: int, title: str, ep_number: int, key: str | None):
    try:
        await discover_anizone_episode(mal_id, title, ep_number)
    finally:
        await _release_anizone_episode_lock(db, key)


async def _queue_anizone_episode(db, background_tasks: BackgroundTasks, mal_id: int, title: str, ep_number: int) -> bool:
    key = await _acquire_anizone_episode_lock(db, mal_id, ep_number)
    if not key:
        return False

    background_tasks.add_task(_run_anizone_episode_discovery, db, mal_id, title, ep_number, key)
    return True


async def _get_available_episode_count(db, mal_id: int, source: str | None = None) -> int:
    query = {"anilist_id": mal_id}
    if source:
        query["source"] = source

    return await db["streams"].count_documents(query)


def _build_catalog_status(mapping: dict | None, provider: str = "animepahe") -> CatalogStatus | None:
    if not mapping and provider != "animepahe":
        return None

    return CatalogStatus(
        provider=provider,
        latest_episode=int(mapping.get("latest_episode", 0) or 0) if mapping else None,
        last_checked_at=mapping.get("last_catalog_check_at") if mapping else None,
        is_refreshing=is_animepahe_refresh_in_progress(int(mapping.get("mal_id"))) if mapping else False,
        is_stale=(is_animepahe_catalog_stale(mapping) or is_animepahe_release_refresh_due(mapping)) if provider == "animepahe" else False,
        provider_status=mapping.get("provider_status") if mapping else None,
        is_airing=mapping.get("is_airing") if mapping else None,
        last_success_at=mapping.get("last_success_at") if mapping else None,
        last_scrape_error=mapping.get("last_scrape_error") if mapping else None,
        last_scrape_duration_ms=mapping.get("last_scrape_duration_ms") if mapping else None,
        next_airing_episode=mapping.get("next_airing_episode") if mapping else None,
        next_airing_at=mapping.get("next_airing_at") if mapping else None,
    )


@router.get("/{mal_id}/{ep_number}", response_model=StreamResponse)
async def get_episode_stream(mal_id: int, ep_number: int, background_tasks: BackgroundTasks):
    """Resolve a streaming URL (iframe or HLS) for a given MAL ID and episode."""
    db = get_db()
    
    # Check for seasonal offset to handle sequels correctly (e.g. mapping Ep 15 to Ep 3)
    from backend.services.jikan_service import get_prequel_episode_offset
    offset = await get_prequel_episode_offset(mal_id)
    
    search_numbers = [ep_number]
    if offset > 0 and ep_number > offset:
        # If user requests Ep 15 and offset is 12, we also check for Ep 3
        search_numbers.append(ep_number - offset)
    elif offset > 0:
        # If user requests Ep 3 and offset is 12, we also check for Ep 15
        search_numbers.append(ep_number + offset)

    animepahe_mapping = await get_animepahe_mapping(mal_id)

    # 1. Check DB for available sources
    stream_candidates = await db["streams"].find(
        {"anilist_id": mal_id, "episode": {"$in": search_numbers}}
    ).to_list(length=20)
    
    stream_data = _sort_stream_candidates(stream_candidates)[0] if stream_candidates else None
    
    # If we found a record, use its episode number (might be the mapped one)
    resolved_ep = stream_data["episode"] if stream_data else ep_number
    
    if stream_data:
        # Special case: AnimePahe needs on-the-fly resolution if not cached
        if (
            stream_data.get("source") == "animepahe"
            and not stream_data.get("stream_url")
            and not stream_data.get("embed_url")
        ):
            try:
                print(f"[Streaming] Resolving AnimePahe link for {mal_id} Ep {resolved_ep}...")
                stream_url = await get_animepahe_stream(
                    stream_data["provider_id"], 
                    stream_data["episode_id"]
                )
                if stream_url:
                    # Update DB with the resolved URL
                    await db["streams"].update_one(
                        {"_id": stream_data["_id"]},
                        {"$set": {"stream_url": stream_url, "updated_at": "resolved"}}
                    )
                    stream_data["stream_url"] = stream_url
            except Exception as e:
                print(f"[Streaming] AnimePahe resolution failed: {e}")

        if stream_data.get("stream_url") or stream_data.get("embed_url"):
            # kwik.cx links are embeds, not direct HLS streams
            s_url = stream_data.get("stream_url")
            e_url = stream_data.get("embed_url")
            
            if s_url and "kwik" in s_url:
                e_url = s_url
                s_url = None

            if stream_data.get("source") == "animepahe" and e_url and "kwik" in e_url and not s_url:
                background_tasks.add_task(
                    _resolve_and_cache_embed_stream,
                    db,
                    stream_data["_id"],
                    e_url,
                )

            return StreamResponse(
                mal_id=mal_id,
                ep_number=resolved_ep, # Return the mapped episode number
                stream_url=s_url,
                embed_url=e_url,
                subtitles=stream_data.get("subtitles", []),
                provider=stream_data.get("source", "unknown"),
                available_episodes=await _get_available_episode_count(
                    db,
                    mal_id,
                    stream_data.get("source")
                ),
                catalog_status=_build_catalog_status(animepahe_mapping, "animepahe")
                if stream_data.get("source") == "animepahe"
                else None,
            )

    # 2. If missing, trigger on-demand discovery across multiple providers
    try:
        anime = await get_anime_detail(mal_id)
        if not anime:
            raise HTTPException(status_code=404, detail="Anime not found on MAL")
        
        from backend.services.animepahe_service import should_refresh_animepahe_catalog
        should_refresh, mapping = await should_refresh_animepahe_catalog(
            mal_id, 
            ep_number, 
            expected_total=(anime.episodes or 0)
        )
        available_episodes = int(mapping.get("latest_episode", 0)) if mapping else 0

        if is_animepahe_refresh_in_progress(mal_id):
            await _queue_anizone_episode(db, background_tasks, mal_id, search_title, ep_number)
            pending_catalog_status = _build_catalog_status(mapping or animepahe_mapping, "animepahe")
            return JSONResponse(
                status_code=202,
                content={
                    "detail": "AnimePahe stream is being fetched. Please refresh in a few seconds.",
                    "mal_id": mal_id,
                    "ep_number": ep_number,
                    "status": "pending",
                    "provider": "animepahe",
                    "available_episodes": available_episodes,
                    "catalog_status": pending_catalog_status.model_dump() if pending_catalog_status else None,
                }
            )

        if not should_refresh:
            anizone_queued = await _queue_anizone_episode(db, background_tasks, mal_id, search_title, ep_number)
            if anizone_queued:
                return JSONResponse(
                    status_code=202,
                    content={
                        "detail": "AniZone stream is being fetched. Please refresh in a few seconds.",
                        "mal_id": mal_id,
                        "ep_number": ep_number,
                        "status": "pending",
                        "provider": "anizone",
                        "available_episodes": available_episodes,
                        "catalog_status": None,
                    }
                )
            raise HTTPException(
                status_code=404,
                detail=f"Episode {ep_number} is not available yet. Latest found: {available_episodes}"
            )

        search_title = anime.title_english or anime.title
        print(f"[Streaming] Queueing AnimePahe discovery for {mal_id} Ep {ep_number} using title: {search_title}")
        background_tasks.add_task(refresh_animepahe_catalog, mal_id, search_title, ep_number)
        await _queue_anizone_episode(db, background_tasks, mal_id, search_title, ep_number)

        pending_catalog_status = _build_catalog_status(mapping or animepahe_mapping, "animepahe")
        return JSONResponse(
            status_code=202,
            content={
                "detail": "AnimePahe stream is being fetched. Please refresh in a few seconds.",
                "mal_id": mal_id,
                "ep_number": ep_number,
                "status": "pending",
                "provider": "animepahe",
                "available_episodes": available_episodes,
                "catalog_status": pending_catalog_status.model_dump() if pending_catalog_status else None,
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Streaming] Discovery failed for {mal_id}: {e}")

    raise HTTPException(status_code=404, detail="No streaming source available for this episode")


@router.post("/refresh/{mal_id}")
async def refresh_stream_catalog(mal_id: int, background_tasks: BackgroundTasks):
    """Manually trigger an AnimePahe metadata refresh for a title."""
    anime = await get_anime_detail(mal_id)
    if not anime:
        raise HTTPException(status_code=404, detail="Anime not found on MAL")

    title = anime.title_english or anime.title
    mapping = await get_animepahe_mapping(mal_id)
    preferred_episode = int(mapping.get("latest_episode", 1) or 1) if mapping else 1

    background_tasks.add_task(
        refresh_animepahe_catalog,
        mal_id,
        title,
        preferred_episode,
        False,
    )

    catalog_status = _build_catalog_status(mapping, "animepahe")
    return {
        "detail": "AnimePahe catalog refresh queued.",
        "mal_id": mal_id,
        "provider": "animepahe",
        "catalog_status": catalog_status.model_dump() if catalog_status else None,
    }
