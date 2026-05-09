"""
Anime Discovery Engine — Jikan (MAL) Service
REST API integration with MyAnimeList via Jikan v4.
"""
import httpx
import asyncio
from typing import Optional
from backend.models.schemas import AnimeResult, AnimeDetail
from backend.cache import (
    metadata_cache,
    search_cache,
    get_cache_key,
    get_persistent_cache,
    set_persistent_cache,
    set_persistent_failure,
    get_singleflight_lock,
)

BASE_URL = "https://api.jikan.moe/v4"
MAX_RETRIES = 3
SEARCH_CACHE_TTL_SECONDS = 60 * 60 * 6
DETAIL_CACHE_TTL_SECONDS = 60 * 60 * 12
RATE_LIMIT_CACHE_TTL_SECONDS = 60 * 3

# Rate limit: ~3 requests/sec
_rate_semaphore = asyncio.Semaphore(3)


def _serialize_anime_result(result: AnimeResult) -> dict:
    return result.model_dump()


def _deserialize_anime_result(data: dict) -> AnimeResult:
    return AnimeResult(**data)


def _serialize_anime_detail(detail: AnimeDetail) -> dict:
    return detail.model_dump()


def _deserialize_anime_detail(data: dict) -> AnimeDetail:
    return AnimeDetail(**data)


def _serialize_paginated_results(results: dict) -> dict:
    return {
        **results,
        "data": [_serialize_anime_result(item) for item in results.get("data", [])],
    }


def _deserialize_paginated_results(data: dict) -> dict:
    return {
        **data,
        "data": [_deserialize_anime_result(item) for item in data.get("data", [])],
    }


def _retry_delay_seconds(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(float(retry_after), 1.0)
            except ValueError:
                pass
    return max(1.0, 1.5 * (attempt + 1))


def _is_rate_limited(error: Exception) -> bool:
    return isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 429


async def _get(endpoint: str, params: dict = None) -> dict:
    """Make a rate-limited GET request to Jikan API."""
    async with _rate_semaphore:
        last_error = None
        async with httpx.AsyncClient(timeout=15.0) as client:
            for attempt in range(MAX_RETRIES):
                try:
                    response = await client.get(f"{BASE_URL}{endpoint}", params=params)
                    response.raise_for_status()
                    await asyncio.sleep(0.35)  # Respect rate limit
                    return response.json()
                except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout) as e:
                    last_error = e
                    if attempt < MAX_RETRIES - 1:
                        wait = _retry_delay_seconds(getattr(e, "response", None), attempt)
                        print(f"[Jikan] Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}. Retrying in {wait}s...")
                        await asyncio.sleep(wait)
                    else:
                        print(f"[Jikan] All {MAX_RETRIES} attempts failed: {e}")
        raise last_error


def _parse_anime(data: dict) -> AnimeResult:
    """Parse Jikan anime data into unified AnimeResult."""
    images = data.get("images", {}).get("jpg", {})
    return AnimeResult(
        id=data.get("mal_id", 0),
        mal_id=data.get("mal_id"),
        title=data.get("title", "Unknown"),
        title_english=data.get("title_english"),
        title_japanese=data.get("title_japanese"),
        image_url=images.get("image_url", ""),
        large_image_url=images.get("large_image_url", ""),
        synopsis=data.get("synopsis"),
        score=data.get("score"),
        episodes=data.get("episodes"),
        status=data.get("status"),
        rating=data.get("rating"),
        year=data.get("year"),
        season=data.get("season"),
        type=data.get("type"),
        genres=[g["name"] for g in data.get("genres", [])],
        studios=[s["name"] for s in data.get("studios", [])],
        source="jikan",
    )


def _parse_anime_detail(data: dict) -> AnimeDetail:
    """Parse Jikan anime data into detailed AnimeDetail."""
    base = _parse_anime(data)
    trailer = data.get("trailer", {})
    aired = data.get("aired", {})

    characters = []
    for char in data.get("characters", [])[:12]:
        character = char.get("character", {})
        char_images = character.get("images", {}).get("jpg", {})
        characters.append({
            "name": character.get("name", ""),
            "role": char.get("role", ""),
            "image_url": char_images.get("image_url", ""),
        })

    related = []
    for relation in data.get("relations", []) or []:
        for entry in relation.get("entry", []) or []:
            images = entry.get("images", {}).get("jpg", {})
            related.append(AnimeResult(
                id=entry.get("mal_id", 0),
                mal_id=entry.get("mal_id"),
                title=entry.get("name", "Unknown"),
                image_url=images.get("image_url", ""),
                large_image_url=images.get("large_image_url", ""),
                relation=relation.get("relation", ""),
                source="jikan",
            ))

    recommendations = []
    for recommendation in data.get("recommendations", []) or []:
        entry = recommendation.get("entry", {})
        images = entry.get("images", {}).get("jpg", {})
        recommendations.append(AnimeResult(
            id=entry.get("mal_id", 0),
            mal_id=entry.get("mal_id"),
            title=entry.get("title", "Unknown"),
            image_url=images.get("image_url", ""),
            large_image_url=images.get("large_image_url", ""),
            source="jikan",
        ))

    return AnimeDetail(
        **base.model_dump(),
        trailer_url=trailer.get("url"),
        duration=data.get("duration"),
        aired=aired.get("string"),
        rank=data.get("rank"),
        popularity=data.get("popularity"),
        members=data.get("members"),
        background=data.get("background"),
        characters=characters,
        related=related[:12],
        recommendations=recommendations[:12],
    )


async def _hydrate_related_images(detail: AnimeDetail) -> AnimeDetail:
    """Fill missing cover images for related/recommended entries using lightweight Jikan lookups."""
    buckets = [detail.related or [], detail.recommendations or []]
    ids_to_fetch: list[int] = []
    seen_ids: set[int] = set()

    for bucket in buckets:
        for item in bucket:
            mal_id = item.mal_id or item.id
            if not mal_id or item.image_url:
                continue
            if mal_id in seen_ids:
                continue
            seen_ids.add(mal_id)
            ids_to_fetch.append(mal_id)

    async def fetch_cover(mal_id: int) -> tuple[int, str, str]:
        try:
            data = await _get(f"/anime/{mal_id}")
            parsed = _parse_anime(data.get("data", {}))
            return mal_id, parsed.image_url or "", parsed.large_image_url or ""
        except Exception:
            return mal_id, "", ""

    if not ids_to_fetch:
        return detail

    fetched = await asyncio.gather(*(fetch_cover(mal_id) for mal_id in ids_to_fetch[:12]))
    image_map = {
        mal_id: {"image_url": image_url, "large_image_url": large_image_url}
        for mal_id, image_url, large_image_url in fetched
        if image_url or large_image_url
    }

    for bucket in buckets:
        for item in bucket:
            mal_id = item.mal_id or item.id
            if not mal_id or mal_id not in image_map:
                continue
            if not item.image_url:
                item.image_url = image_map[mal_id]["image_url"]
            if not item.large_image_url:
                item.large_image_url = image_map[mal_id]["large_image_url"]

    return detail


async def search_anime(
    query: Optional[str] = None,
    genres: Optional[str] = None,
    producers: Optional[str] = None,
    type_filter: Optional[str] = None,
    min_score: Optional[int] = None,
    max_score: Optional[int] = None,
    status: Optional[str] = None,
    rating: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    order_by: str = "score",
    sort: str = "desc",
    page: int = 1,
    limit: int = 24,
) -> dict:
    """Search anime with filters."""
    cache_key = get_cache_key("jikan_search", query, genres, producers, type_filter, status, rating, start_date, end_date, page)
    if cache_key in search_cache:
        return search_cache[cache_key]
    cached_doc = await get_persistent_cache(cache_key)
    if cached_doc and cached_doc.get("data"):
        hydrated = _deserialize_paginated_results(cached_doc["data"])
        search_cache[cache_key] = hydrated
        return hydrated

    lock = get_singleflight_lock(cache_key)
    async with lock:
        if cache_key in search_cache:
            return search_cache[cache_key]
        cached_doc = await get_persistent_cache(cache_key)
        if cached_doc and cached_doc.get("data"):
            hydrated = _deserialize_paginated_results(cached_doc["data"])
            search_cache[cache_key] = hydrated
            return hydrated

        params = {"page": page, "limit": limit, "order_by": order_by, "sort": sort, "sfw": True}
        if query:
            params["q"] = query
        if genres:
            params["genres"] = genres
        if producers:
            params["producers"] = producers
        if type_filter:
            params["type"] = type_filter
        if min_score:
            params["min_score"] = min_score
        if max_score:
            params["max_score"] = max_score
        if status:
            params["status"] = status
        if rating:
            params["rating"] = rating
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date

        try:
            data = await _get("/anime", params)
        except Exception as e:
            if _is_rate_limited(e):
                await set_persistent_failure(cache_key, status="rate_limited", ttl_seconds=RATE_LIMIT_CACHE_TTL_SECONDS, detail=str(e))
                stale_doc = await get_persistent_cache(cache_key, allow_stale=True)
                if stale_doc and stale_doc.get("data"):
                    hydrated = _deserialize_paginated_results(stale_doc["data"])
                    search_cache[cache_key] = hydrated
                    return hydrated
            raise
        pagination = data.get("pagination", {})
        results = {
            "data": [_parse_anime(a) for a in data.get("data", [])],
            "total": pagination.get("items", {}).get("total", 0),
            "has_next": pagination.get("has_next_page", False),
            "page": page,
        }
        search_cache[cache_key] = results
        await set_persistent_cache(cache_key, _serialize_paginated_results(results), ttl_seconds=SEARCH_CACHE_TTL_SECONDS)
        return results


async def get_top_anime(page: int = 1, limit: int = 24, filter_type: str = None) -> dict:
    """Get top rated anime."""
    cache_key = get_cache_key("jikan_top", filter_type, page)
    if cache_key in search_cache:
        return search_cache[cache_key]

    params = {"page": page, "limit": limit}
    if filter_type:
        params["filter"] = filter_type

    data = await _get("/top/anime", params)
    pagination = data.get("pagination", {})
    results = {
        "data": [_parse_anime(a) for a in data.get("data", [])],
        "total": pagination.get("items", {}).get("total", 0),
        "has_next": pagination.get("has_next_page", False),
        "page": page,
    }
    search_cache[cache_key] = results
    return results


async def get_anime_detail(mal_id: int) -> AnimeDetail:
    """Get full anime details by MAL ID."""
    cache_key = get_cache_key("jikan_detail", mal_id)
    if cache_key in search_cache:
        cached_detail = search_cache[cache_key]
        try:
            hydrated_cached_detail = await _hydrate_related_images(cached_detail)
            search_cache[cache_key] = hydrated_cached_detail
            return hydrated_cached_detail
        except Exception:
            return cached_detail
    cached_doc = await get_persistent_cache(cache_key)
    if cached_doc and cached_doc.get("data"):
        cached_detail = _deserialize_anime_detail(cached_doc["data"])
        try:
            hydrated_cached_detail = await _hydrate_related_images(cached_detail)
            search_cache[cache_key] = hydrated_cached_detail
            return hydrated_cached_detail
        except Exception:
            search_cache[cache_key] = cached_detail
            return cached_detail

    lock = get_singleflight_lock(cache_key)
    async with lock:
        if cache_key in search_cache:
            cached_detail = search_cache[cache_key]
            try:
                hydrated_cached_detail = await _hydrate_related_images(cached_detail)
                search_cache[cache_key] = hydrated_cached_detail
                return hydrated_cached_detail
            except Exception:
                return cached_detail
        cached_doc = await get_persistent_cache(cache_key)
        if cached_doc and cached_doc.get("data"):
            cached_detail = _deserialize_anime_detail(cached_doc["data"])
            try:
                hydrated_cached_detail = await _hydrate_related_images(cached_detail)
                search_cache[cache_key] = hydrated_cached_detail
                return hydrated_cached_detail
            except Exception:
                search_cache[cache_key] = cached_detail
                return cached_detail

        try:
            data = await _get(f"/anime/{mal_id}/full")
        except Exception as e:
            if _is_rate_limited(e):
                await set_persistent_failure(cache_key, status="rate_limited", ttl_seconds=RATE_LIMIT_CACHE_TTL_SECONDS, detail=str(e))
                stale_doc = await get_persistent_cache(cache_key, allow_stale=True)
                if stale_doc and stale_doc.get("data"):
                    cached_detail = _deserialize_anime_detail(stale_doc["data"])
                    search_cache[cache_key] = cached_detail
                    return cached_detail
            raise
        detail = _parse_anime_detail(data.get("data", {}))

        try:
            char_data = await _get(f"/anime/{mal_id}/characters")
            characters = []
            for char in char_data.get("data", [])[:12]:
                character = char.get("character", {})
                char_images = character.get("images", {}).get("jpg", {})
                characters.append({
                    "name": character.get("name", ""),
                    "role": char.get("role", ""),
                    "image_url": char_images.get("image_url", ""),
                })
            detail.characters = characters
        except Exception:
            pass

        try:
            detail = await _hydrate_related_images(detail)
        except Exception:
            pass

        search_cache[cache_key] = detail
        await set_persistent_cache(cache_key, _serialize_anime_detail(detail), ttl_seconds=DETAIL_CACHE_TTL_SECONDS)
        return detail


async def get_seasonal_anime(year: int, season: str, page: int = 1) -> dict:
    """Get anime for a specific season."""
    cache_key = get_cache_key("jikan_season", year, season, page)
    if cache_key in search_cache:
        return search_cache[cache_key]

    data = await _get(f"/seasons/{year}/{season}", {"page": page, "limit": 24})
    pagination = data.get("pagination", {})
    results = {
        "data": [_parse_anime(a) for a in data.get("data", [])],
        "total": pagination.get("items", {}).get("total", 0),
        "has_next": pagination.get("has_next_page", False),
        "page": page,
    }
    search_cache[cache_key] = results
    return results


async def get_genres() -> list[dict]:
    """Get genre list for filters."""
    cache_key = "jikan_genres"
    if cache_key in metadata_cache:
        return metadata_cache[cache_key]

    data = await _get("/genres/anime")
    genres = [{"mal_id": g["mal_id"], "name": g["name"], "count": g.get("count", 0)}
              for g in data.get("data", [])]
    metadata_cache[cache_key] = genres
    return genres


async def get_studios() -> list[dict]:
    """Get studio/producer list for filters."""
    cache_key = "jikan_studios"
    if cache_key in metadata_cache:
        return metadata_cache[cache_key]

    data = await _get("/producers", {"limit": 100, "order_by": "count", "sort": "desc"})
    studios = [{"mal_id": s["mal_id"], "name": s.get("titles", [{}])[0].get("title", "Unknown") if s.get("titles") else "Unknown", "count": s.get("count", 0)}
               for s in data.get("data", [])]
    metadata_cache[cache_key] = studios
    return studios


async def get_random_anime() -> AnimeResult:
    """Get a random anime."""
    data = await _get("/random/anime")
    return _parse_anime(data.get("data", {}))

async def get_prequel_episode_offset(mal_id: int) -> int:
    """
    Recursively calculate the total episodes of all prequels.
    Used for providers that continue episode numbering (e.g. AnimePahe).
    """
    cache_key = f"offset_{mal_id}"
    if cache_key in metadata_cache:
        return metadata_cache[cache_key]

    try:
        detail = await get_anime_detail(mal_id)
        if not detail or not detail.related:
            metadata_cache[cache_key] = 0
            return 0
            
        prequel_id = None
        for rel in detail.related:
            if rel.relation == "Prequel":
                prequel_id = rel.mal_id
                break
                
        if not prequel_id:
            metadata_cache[cache_key] = 0
            return 0
            
        prequel_detail = await get_anime_detail(prequel_id)
        if not prequel_detail:
            metadata_cache[cache_key] = 0
            return 0
            
        # Current prequel's episodes + recursive prequels
        count = prequel_detail.episodes or 0
        total_offset = count + await get_prequel_episode_offset(prequel_id)
        metadata_cache[cache_key] = total_offset
        return total_offset
    except Exception as e:
        print(f"[Jikan Service] Error calculating offset for {mal_id}: {e}")
        return 0
