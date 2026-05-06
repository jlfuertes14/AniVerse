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
async def get_latest():
    """Get latest releases from AnimePahe."""
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
        # 1. Vibe-based search
        if vibe:
            return await search_by_vibe(vibe, page=page)

        # 2. Smart NLP Detection (Optional: can be triggered by length or keywords)
        ai_results = []
        if q and (len(q.split()) > 3 or any(word in q.lower() for word in ["like", "similar", "about", "protagonist", "recommend"])):
            try:
                from backend.routers.ai import ai_search
                # We reuse the ai_search logic but as an internal call
                # Note: ai_search expects a body dict, but we can call it or its services
                from backend.services import nlp_search
                parsed = await nlp_search.parse_natural_language(q)
                
                if not parsed.get("error") and parsed.get("filters"):
                    # If the AI identified something, let's use the ai_search logic
                    # To avoid circular imports or messy code, we'll just hit the search_by_tags
                    filters = parsed["filters"]
                    
                    # 2a. Search by AI-extracted tags/genres
                    al_results = await anilist_service.search_by_tags(
                        tags=filters.get("tags"),
                        genres=filters.get("genres"),
                        year_from=filters.get("year_from"),
                        year_to=filters.get("year_to"),
                        page=page,
                        per_page=20
                    )
                    ai_results = al_results.get("data", [])
            except Exception as e:
                print(f"[SmartSearch] AI Fallback failed: {e}")

        # 3. Standard Text search via Jikan
        start_date = f"{year_from}-01-01" if year_from else None
        end_date = f"{year_to}-12-31" if year_to else None

        jikan_results = await jikan_service.search_anime(
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
        
        # Merge results (AI results first for relevance)
        results_data = ai_results
        existing_ids = {getattr(a, 'id', None) or a.get('id') for a in results_data if a}
        
        for a in jikan_results.get("data", []):
            aid = getattr(a, 'id', None) or a.get('id')
            if aid not in existing_ids:
                results_data.append(a)

        # 4. Rank and Filter
        if results_data:
            if type:
                target_type = type.lower()
                results_data = [a for a in results_data if (getattr(a, 'type', None) or "").lower() == target_type]
            
            if q and not ai_results: # Only rank if AI didn't already handle the relevance
                scored = []
                for anime in results_data:
                    # Handle both AnimeResult objects and dicts
                    if not isinstance(anime, AnimeResult):
                        # Convert dict to temp AnimeResult for relevance check
                        temp = AnimeResult(
                            id=anime.get("id", 0),
                            title=anime.get("title", ""),
                            title_english=anime.get("title_english"),
                            title_japanese=anime.get("title_japanese"),
                        )
                        score = _title_relevance(temp, q)
                    else:
                        score = _title_relevance(anime, q)
                    scored.append((anime, score))
                
                scored = [(a, s) for a, s in scored if s > 0]
                scored.sort(key=lambda x: (x[1], getattr(x[0], 'score', 0) or x[0].get('score', 0) or 0), reverse=True)
                results_data = [a for a, s in scored]

        return {
            "data": results_data[:24],
            "total": len(results_data),
            "has_next": jikan_results.get("has_next", False),
            "page": page,
            "smart_search": len(ai_results) > 0
        }
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
