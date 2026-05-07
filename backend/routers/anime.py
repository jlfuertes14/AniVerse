"""
Anime Discovery Engine — Anime Router
Main anime endpoints: search, trending, top, details, seasonal, vibes.
"""
from fastapi import APIRouter, Query
import httpx
from typing import Optional
from backend.services import jikan_service, anilist_service, animepahe_service, schedule_service
from backend.services.vibe_engine import get_all_vibes, search_by_vibe
from backend.models.schemas import AnimeResult

router = APIRouter(prefix="/anime", tags=["anime"])


@router.get("/latest")
async def get_latest(prefer: Optional[str] = Query("animepahe", description="animepahe or reanime")):
    """Get latest releases from the preferred provider."""
    if prefer == "reanime":
        from backend.services import reanime_service
        return await reanime_service.get_latest_releases()
    return await animepahe_service.get_latest_releases()


@router.get("/schedule")
async def get_schedule(refresh: bool = False):
    """Get the weekly airing schedule."""
    if refresh:
        await schedule_service.refresh_airing_schedule(force=True)
    
    schedule = await schedule_service.get_airing_schedule()
    return schedule or {}


def _title_relevance(anime: AnimeResult, query: str) -> int:
    """Score how relevant an anime title is to the query. Higher = better match."""
    q = query.lower().strip()
    titles = [
        (anime.title or "").lower(),
        (anime.title_english or "").lower(),
        (anime.title_japanese or "").lower(),
    ]

    # Exact match
    for t in titles:
        if t and t == q:
            return 100

    # Title starts with query
    for t in titles:
        if t and t.startswith(q):
            return 90

    # Query is fully contained in title
    for t in titles:
        if t and q in t:
            return 80

    # All query words appear in at least one title
    query_words = q.split()
    for t in titles:
        if t and all(w in t for w in query_words):
            return 70

    # Most query words appear (>= 50%)
    for t in titles:
        if t:
            matches = sum(1 for w in query_words if w in t)
            if matches >= len(query_words) * 0.5:
                return 50 + matches

    # At least one query word in title
    for t in titles:
        if t and any(w in t for w in query_words):
            return 30

    # No title match at all
    return 0


@router.get("/search")
async def search_anime(
    q: Optional[str] = Query(None, description="Search query"),
    vibe: Optional[str] = Query(None, description="Vibe preset ID"),
    genres: Optional[str] = Query(None, description="Comma-separated genre IDs (Jikan)"),
    studios: Optional[str] = Query(None, description="Comma-separated studio IDs (Jikan)"),
    year_from: Optional[int] = Query(None, description="Start year"),
    year_to: Optional[int] = Query(None, description="End year"),
    status: Optional[str] = Query(None, description="airing, complete, upcoming"),
    rating: Optional[str] = Query(None, description="g, pg, pg13, r17, r, rx"),
    type: Optional[str] = Query(None, description="tv, movie, ova, special, ona, music"),
    page: int = Query(1, ge=1),
):
    """Search anime with text query, vibe preset, or advanced filters."""
    try:
        # Vibe-based search
        if vibe:
            return await search_by_vibe(vibe, page=page)

        # Text search or filtered search via Jikan
        start_date = f"{year_from}-01-01" if year_from else None
        end_date = f"{year_to}-12-31" if year_to else None

        results = await jikan_service.search_anime(
            query=q,
            genres=genres,
            producers=studios,
            type_filter=type,
            status=status,
            rating=rating,
            start_date=start_date,
            end_date=end_date,
            page=page,
        )

        # If text query, rank by title relevance and filter weak matches
        if results.get("data"):
            # Strict type filtering (Jikan sometimes leaks types, especially in mixed searches)
            if type:
                target_type = type.lower()
                results["data"] = [a for a in results["data"] if a.type and a.type.lower() == target_type]
            
            if q:
                scored = [(anime, _title_relevance(anime, q)) for anime in results["data"]]
                # Filter out results with no title word match (score 0)
                scored = [(a, s) for a, s in scored if s > 0]
                # Sort by relevance score (desc), then by anime score (desc)
                scored.sort(key=lambda x: (x[1], x[0].score or 0), reverse=True)
                results["data"] = [a for a in results["data"] if a]
            
            results["total"] = len(results["data"])

        return results
    except Exception as e:
        print(f"[Search] Failed: {e}")
        return {"data": [], "total": 0, "has_next": False, "page": page}


@router.get("/trending")
async def get_trending(page: int = Query(1, ge=1)):
    """Get currently trending anime from AniList."""
    try:
        return await anilist_service.get_trending(page=page)
    except Exception as e:
        print(f"[AniList] Trending failed: {e}")
        return {"data": [], "total": 0, "has_next": False, "page": page}


@router.get("/top")
async def get_top(
    page: int = Query(1, ge=1),
    filter: Optional[str] = Query(None, description="airing, upcoming, bypopularity, favorite"),
):
    """Get top rated anime from Jikan."""
    try:
        return await jikan_service.get_top_anime(page=page, filter_type=filter)
    except Exception as e:
        print(f"[Jikan] Top failed: {e}")
        return {"data": [], "total": 0, "has_next": False, "page": page}


@router.get("/spotlight")
async def get_spotlight():
    """Get spotlight anime for hero section."""
    try:
        return await anilist_service.get_spotlight(count=5)
    except Exception as e:
        print(f"[AniList] Spotlight failed: {e}")
        return []


@router.get("/vibes")
async def get_vibes():
    """Get all available vibe presets."""
    return get_all_vibes()


@router.get("/random")
async def get_random():
    """Get a random anime."""
    return await jikan_service.get_random_anime()


@router.get("/seasonal/{year}/{season}")
async def get_seasonal(year: int, season: str, page: int = Query(1, ge=1)):
    """Get anime for a specific season."""
    return await jikan_service.get_seasonal_anime(year, season, page)


@router.get("/{anime_id}")
async def get_anime_detail(anime_id: int, source: str = Query("anilist", description="jikan or anilist")):
    """Get detailed anime info."""
    try:
        if source == "anilist":
            return await anilist_service.get_anime_detail(anime_id)
        else:
            return await jikan_service.get_anime_detail(anime_id)
    except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout) as e:
        print(f"[API] Detail fetch failed for {anime_id}: {e}")
        # Try fallback source
        try:
            if source == "anilist":
                return await jikan_service.get_anime_detail(anime_id)
            else:
                return await anilist_service.get_anime_detail(anime_id)
        except Exception:
            return {"error": "Anime data temporarily unavailable. Please try again."}
