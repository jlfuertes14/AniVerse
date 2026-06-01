from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
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
from backend.services.reanime_service import (
    search_reanime_by_title,
    scrape_reanime_episode,
    get_stream_for_episode as get_reanime_stream
)
from backend.services.jikan_service import get_anime_detail

router = APIRouter(prefix="/stream", tags=["streaming"])


SOURCE_PRIORITY = {
    "shiroko": 0,
    "miruro": 1,
    "animeverse": 2,
    "uniquestream": 3,
    "reanime": 4,
    "animepahe": 5,
}


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


async def _get_latest_episode_number(db, mal_id: int, source: str | None = None) -> int:
    query = {"anilist_id": mal_id}
    if source:
        query["source"] = source

    latest_db = await db["streams"].find_one(query, sort=[("episode", -1)])
    db_count = int(latest_db.get("episode", 0)) if latest_db else 0
    
    # Check provider mapping for Re:ANIME specifically to get the total available on site
    if source == "reanime":
        mapping = await db["provider_mappings"].find_one({"mal_id": mal_id, "provider": "reanime"})
        if mapping and mapping.get("latest_episode"):
            return max(db_count, int(mapping["latest_episode"]))

    return db_count


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
async def get_episode_stream(
    mal_id: int,
    ep_number: int,
    background_tasks: BackgroundTasks,
    prefer: str | None = None,
    from_context: str | None = Query(None, alias="from"),
):
    """Resolve a streaming URL (iframe or HLS) for a given MAL ID and episode."""
    db = get_db()
    
    # Check for seasonal offset to handle sequels correctly (e.g. mapping Ep 15 to Ep 3)
    from backend.services.jikan_service import get_prequel_episode_offset
    offset = await get_prequel_episode_offset(mal_id)
    
    search_numbers = [ep_number]
    if offset > 0 and ep_number > offset:
        search_numbers.append(ep_number - offset)
    elif offset > 0:
        search_numbers.append(ep_number + offset)

    animepahe_requested_episode = ep_number
    if prefer == "animepahe" and from_context == "latest" and offset > 0 and ep_number > offset:
        animepahe_requested_episode = ep_number - offset
        print(
            f"[Streaming] Normalized AnimePahe latest-release episode "
            f"{ep_number} -> {animepahe_requested_episode} using offset {offset} for MAL {mal_id}"
        )

    animepahe_mapping = await get_animepahe_mapping(mal_id)
    reanime_mapping = await db["provider_mappings"].find_one({"mal_id": mal_id, "provider": "reanime"})
    miruro_mapping = await db["provider_mappings"].find_one({"mal_id": mal_id, "provider": "miruro"})
    shiroko_mapping = await db["provider_mappings"].find_one({"mal_id": mal_id, "provider": "shiroko"})
    animeverse_mapping = await db["provider_mappings"].find_one({"mal_id": mal_id, "provider": "animeverse"})
    uniquestream_mapping = await db["provider_mappings"].find_one({"mal_id": mal_id, "provider": "uniquestream"})

    # 1. Check DB for available sources
    stream_candidates = await db["streams"].find(
        {"anilist_id": mal_id, "episode": {"$in": search_numbers}}
    ).to_list(length=20)

    preferred_record = None
    if prefer in {"shiroko", "miruro", "animeverse", "uniquestream", "reanime", "animepahe"}:
        matches = [record for record in stream_candidates if record.get("source") == prefer]
        if matches:
            preferred_record = _sort_stream_candidates(matches)[0]
        else:
            # If preferred source is NOT in DB, we must trigger discovery
            # instead of falling back to other DB records immediately
            print(f"[Streaming] Preferred source '{prefer}' missing from DB. Triggering discovery...")
            stream_data = None
    
    if not preferred_record and not (prefer and not any(r.get("source") == prefer for r in stream_candidates)):
        if stream_candidates:
            stream_data = _sort_stream_candidates(stream_candidates)[0]
        else:
            stream_data = None
    else:
        stream_data = preferred_record
    
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
                    await db["streams"].update_one(
                        {"_id": stream_data["_id"]},
                        {"$set": {"stream_url": stream_url, "updated_at": "resolved"}}
                    )
                    stream_data["stream_url"] = stream_url
            except Exception as e:
                print(f"[Streaming] AnimePahe resolution failed: {e}")

        if stream_data.get("stream_url") or stream_data.get("embed_url"):
            s_url = stream_data.get("stream_url")
            e_url = stream_data.get("embed_url")
            referer_url = stream_data.get("referer_url")
            
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

            mapping_for_status = None
            src = stream_data.get("source")
            if src == "shiroko": mapping_for_status = shiroko_mapping
            elif src == "miruro": mapping_for_status = miruro_mapping
            elif src == "animeverse": mapping_for_status = animeverse_mapping
            elif src == "uniquestream": mapping_for_status = uniquestream_mapping
            elif src == "animepahe": mapping_for_status = animepahe_mapping
            else: mapping_for_status = reanime_mapping

            print(f"[Streaming] Returning {stream_data.get('source')} stream for {mal_id} Ep {resolved_ep}")
            return StreamResponse(
                mal_id=mal_id,
                ep_number=resolved_ep,
                stream_url=s_url,
                embed_url=e_url,
                subtitles=stream_data.get("subtitles", []),
                provider=stream_data.get("source", "unknown"),
                available_episodes=await _get_latest_episode_number(
                    db,
                    mal_id,
                    stream_data.get("source")
                ),
                referer_url=referer_url,
                catalog_status=_build_catalog_status(
                    mapping_for_status,
                    stream_data.get("source", "unknown")
                ),
            )

    # 2. If missing, trigger on-demand discovery
    try:
        anime = await get_anime_detail(mal_id)
        if not anime:
            raise HTTPException(status_code=404, detail="Anime not found on MAL")
        
        search_title = anime.title_english or anime.title

        # --- Shiroko Discovery (Primary 0) ---
        if prefer not in {"miruro", "animeverse", "uniquestream", "reanime", "animepahe"}:
            from backend.services.shiroko_service import check_shiroko_refresh_in_progress, refresh_shiroko_catalog
            
            if await check_shiroko_refresh_in_progress(mal_id):
                pending_catalog_status = _build_catalog_status(shiroko_mapping, "shiroko")
                return JSONResponse(
                    status_code=202,
                    content={
                        "detail": "Shiroko stream is being fetched. Please refresh in a few seconds.",
                        "mal_id": mal_id,
                        "ep_number": ep_number,
                        "status": "pending",
                        "provider": "shiroko",
                        "available_episodes": int(shiroko_mapping.get("latest_episode", 0)) if shiroko_mapping else 0,
                        "catalog_status": pending_catalog_status.model_dump() if pending_catalog_status else None,
                    }
                )

            shiroko_stale = True
            if shiroko_mapping and shiroko_mapping.get("last_catalog_check_at"):
                last_check = datetime.fromisoformat(shiroko_mapping["last_catalog_check_at"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - last_check < timedelta(minutes=15):
                    shiroko_stale = False

            if shiroko_stale:
                print(f"[Streaming] Queueing Shiroko discovery for MAL {mal_id} Ep {ep_number}...")
                background_tasks.add_task(refresh_shiroko_catalog, mal_id, ep_number)
                
                pending_catalog_status = _build_catalog_status(shiroko_mapping, "shiroko")
                return JSONResponse(
                    status_code=202,
                    content={
                        "detail": "Shiroko stream is being fetched. Please refresh in a few seconds.",
                        "mal_id": mal_id,
                        "ep_number": ep_number,
                        "status": "pending",
                        "provider": "shiroko",
                        "available_episodes": int(shiroko_mapping.get("latest_episode", 0)) if shiroko_mapping else 0,
                        "catalog_status": pending_catalog_status.model_dump() if pending_catalog_status else None,
                    }
                )
            else:
                print(f"[Streaming] Shiroko discovery recently checked and skipped. Falling back to Miruro...")

        # --- Miruro Discovery (Priority 1) ---
        if prefer not in {"animeverse", "uniquestream", "reanime", "animepahe"}:
            from backend.services.miruro_service import is_miruro_refresh_in_progress, refresh_miruro_catalog
            
            if is_miruro_refresh_in_progress(mal_id):
                pending_catalog_status = _build_catalog_status(miruro_mapping, "miruro")
                return JSONResponse(
                    status_code=202,
                    content={
                        "detail": "Miruro stream is being fetched. Please refresh in a few seconds.",
                        "mal_id": mal_id,
                        "ep_number": ep_number,
                        "status": "pending",
                        "provider": "miruro",
                        "available_episodes": int(miruro_mapping.get("latest_episode", 0)) if miruro_mapping else 0,
                        "catalog_status": pending_catalog_status.model_dump() if pending_catalog_status else None,
                    }
                )

            miruro_stale = True
            if miruro_mapping and miruro_mapping.get("last_catalog_check_at"):
                last_check = datetime.fromisoformat(miruro_mapping["last_catalog_check_at"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - last_check < timedelta(minutes=15):
                    miruro_stale = False

            if miruro_stale:
                print(f"[Streaming] Queueing Miruro discovery for MAL {mal_id} Ep {ep_number}...")
                background_tasks.add_task(
                    refresh_miruro_catalog,
                    mal_id,
                    ep_number,
                )
                
                pending_catalog_status = _build_catalog_status(miruro_mapping, "miruro")
                return JSONResponse(
                    status_code=202,
                    content={
                        "detail": "Miruro stream is being fetched. Please refresh in a few seconds.",
                        "mal_id": mal_id,
                        "ep_number": ep_number,
                        "status": "pending",
                        "provider": "miruro",
                        "available_episodes": int(miruro_mapping.get("latest_episode", 0)) if miruro_mapping else 0,
                        "catalog_status": pending_catalog_status.model_dump() if pending_catalog_status else None,
                    }
                )
            else:
                print(f"[Streaming] Miruro discovery recently checked and skipped. Falling back to Animeverse...")

        # --- Animeverse Discovery (Priority 2) ---
        if prefer not in {"uniquestream", "reanime", "animepahe"}:
            from backend.services.animeverse_service import check_animeverse_refresh_in_progress, refresh_animeverse_catalog
            
            if await check_animeverse_refresh_in_progress(mal_id):
                pending_catalog_status = _build_catalog_status(animeverse_mapping, "animeverse")
                return JSONResponse(
                    status_code=202,
                    content={
                        "detail": "Animeverse stream is being fetched. Please refresh in a few seconds.",
                        "mal_id": mal_id,
                        "ep_number": ep_number,
                        "status": "pending",
                        "provider": "animeverse",
                        "available_episodes": int(animeverse_mapping.get("latest_episode", 0)) if animeverse_mapping else 0,
                        "catalog_status": pending_catalog_status.model_dump() if pending_catalog_status else None,
                    }
                )

            animeverse_stale = True
            if animeverse_mapping and animeverse_mapping.get("last_catalog_check_at"):
                last_check = datetime.fromisoformat(animeverse_mapping["last_catalog_check_at"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - last_check < timedelta(minutes=15):
                    animeverse_stale = False

            if animeverse_stale:
                print(f"[Streaming] Queueing Animeverse discovery for MAL {mal_id} Ep {ep_number}...")
                background_tasks.add_task(refresh_animeverse_catalog, mal_id, search_title, ep_number)
                
                pending_catalog_status = _build_catalog_status(animeverse_mapping, "animeverse")
                return JSONResponse(
                    status_code=202,
                    content={
                        "detail": "Animeverse stream is being fetched. Please refresh in a few seconds.",
                        "mal_id": mal_id,
                        "ep_number": ep_number,
                        "status": "pending",
                        "provider": "animeverse",
                        "available_episodes": int(animeverse_mapping.get("latest_episode", 0)) if animeverse_mapping else 0,
                        "catalog_status": pending_catalog_status.model_dump() if pending_catalog_status else None,
                    }
                )
            else:
                print(f"[Streaming] Animeverse discovery recently checked and skipped. Falling back to Uniquestream...")

        # --- Uniquestream Discovery (Priority 3) ---
        if prefer not in {"reanime", "animepahe"}:
            from backend.services.uniquestream_service import check_uniquestream_refresh_in_progress, refresh_uniquestream_catalog
            
            if await check_uniquestream_refresh_in_progress(mal_id):
                pending_catalog_status = _build_catalog_status(uniquestream_mapping, "uniquestream")
                return JSONResponse(
                    status_code=202,
                    content={
                        "detail": "Uniquestream stream is being fetched. Please refresh in a few seconds.",
                        "mal_id": mal_id,
                        "ep_number": ep_number,
                        "status": "pending",
                        "provider": "uniquestream",
                        "available_episodes": int(uniquestream_mapping.get("latest_episode", 0)) if uniquestream_mapping else 0,
                        "catalog_status": pending_catalog_status.model_dump() if pending_catalog_status else None,
                    }
                )

            uniquestream_stale = True
            if uniquestream_mapping and uniquestream_mapping.get("last_catalog_check_at"):
                last_check = datetime.fromisoformat(uniquestream_mapping["last_catalog_check_at"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - last_check < timedelta(minutes=15):
                    uniquestream_stale = False

            if uniquestream_stale:
                print(f"[Streaming] Queueing Uniquestream discovery for MAL {mal_id} Ep {ep_number}...")
                background_tasks.add_task(refresh_uniquestream_catalog, mal_id, search_title, ep_number)
                
                pending_catalog_status = _build_catalog_status(uniquestream_mapping, "uniquestream")
                return JSONResponse(
                    status_code=202,
                    content={
                        "detail": "Uniquestream stream is being fetched. Please refresh in a few seconds.",
                        "mal_id": mal_id,
                        "ep_number": ep_number,
                        "status": "pending",
                        "provider": "uniquestream",
                        "available_episodes": int(uniquestream_mapping.get("latest_episode", 0)) if uniquestream_mapping else 0,
                        "catalog_status": pending_catalog_status.model_dump() if pending_catalog_status else None,
                    }
                )
            else:
                print(f"[Streaming] Uniquestream discovery recently checked and skipped. Falling back to Re:ANIME...")

        # --- Re:ANIME Discovery (Secondary) ---
        if prefer != "animepahe":
            from backend.services.reanime_service import is_reanime_refresh_in_progress, refresh_reanime_catalog
            
            if is_reanime_refresh_in_progress(mal_id):
                pending_catalog_status = _build_catalog_status(reanime_mapping, "reanime")
                return JSONResponse(
                    status_code=202,
                    content={
                        "detail": "Re:ANIME stream is being fetched. Please refresh in a few seconds.",
                        "mal_id": mal_id,
                        "ep_number": ep_number,
                        "status": "pending",
                        "provider": "reanime",
                        "available_episodes": int(reanime_mapping.get("latest_episode", 0)) if reanime_mapping else 0,
                        "catalog_status": pending_catalog_status.model_dump() if pending_catalog_status else None,
                    }
                )

            # Check if we recently tried and failed, to avoid infinite 202 loops
            reanime_stale = True
            if reanime_mapping and reanime_mapping.get("last_catalog_check_at"):
                last_check = datetime.fromisoformat(reanime_mapping["last_catalog_check_at"].replace("Z", "+00:00"))
                if datetime.now(timezone.utc) - last_check < timedelta(minutes=15):
                    reanime_stale = False

            if reanime_stale:
                print(f"[Streaming] Queueing Re:ANIME discovery for {search_title}...")
                background_tasks.add_task(
                    refresh_reanime_catalog,
                    mal_id,
                    search_title,
                    ep_number,
                )
                
                pending_catalog_status = _build_catalog_status(reanime_mapping, "reanime")
                return JSONResponse(
                    status_code=202,
                    content={
                        "detail": "Re:ANIME stream is being fetched. Please refresh in a few seconds.",
                        "mal_id": mal_id,
                        "ep_number": ep_number,
                        "status": "pending",
                        "provider": "reanime",
                        "available_episodes": int(reanime_mapping.get("latest_episode", 0)) if reanime_mapping else 0,
                        "catalog_status": pending_catalog_status.model_dump() if pending_catalog_status else None,
                    }
                )
            else:
                print(f"[Streaming] Re:ANIME discovery recently checked and skipped. Falling back to AnimePahe...")

        # --- AnimePahe Discovery (Fallback) ---
        from backend.services.animepahe_service import should_refresh_animepahe_catalog
        should_refresh, mapping = await should_refresh_animepahe_catalog(
            mal_id, 
            animepahe_requested_episode, 
            expected_total=(anime.episodes or 0)
        )
        available_episodes = int(mapping.get("latest_episode", 0)) if mapping else 0

        if is_animepahe_refresh_in_progress(mal_id):
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

        if should_refresh:
            print(
                f"[Streaming] Queueing AnimePahe discovery for {mal_id} Ep "
                f"{animepahe_requested_episode} using title: {search_title}"
            )
            background_tasks.add_task(
                refresh_animepahe_catalog,
                mal_id,
                search_title,
                animepahe_requested_episode,
            )
            
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

        raise HTTPException(
            status_code=404,
            detail=f"Episode {ep_number} is not available yet. Latest found on backup source: {available_episodes}"
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
