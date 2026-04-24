"""
Anime Discovery Engine — AI Router
NLP search and content-based recommendations.
"""
from fastapi import APIRouter, Query, Body
from typing import Optional
from backend.services import nlp_search, recommendation_engine, anilist_service
from backend.models.schemas import AnimeResult

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/search")
async def ai_search(body: dict = Body(...)):
    """
    Natural language anime search powered by Gemini.
    Send: { "query": "something like death note but more action" }
    Returns: AI-extracted filters + matching anime results.
    """
    user_query = body.get("query", "")
    if not user_query:
        return {"error": "Please provide a query", "results": []}

    # Step 1: Parse natural language → structured filters via Gemini
    parsed = await nlp_search.parse_natural_language(user_query)

    if parsed.get("error"):
        return {"error": parsed["error"], "results": [], "filters": None}

    filters = parsed.get("filters", {})
    if not filters:
        return {"error": "Could not understand your request", "results": [], "filters": None}

    # Step 2: Use extracted filters to search AniList
    results = []
    try:
        anilist_results = await anilist_service.search_by_tags(
            tags=filters.get("tags"),
            genres=filters.get("genres"),
            year_from=filters.get("year_from"),
            year_to=filters.get("year_to"),
            page=1,
            per_page=24,
        )
        results = anilist_results.get("data", [])
    except Exception:
        pass

    # Step 3: Additionally search the recommendation engine by description
    if recommendation_engine.is_ready():
        desc = filters.get("description", user_query)
        rec_results = recommendation_engine.search_by_text(desc, top_n=10)
        # Convert to AnimeResult-like dicts and merge
        for r in rec_results:
            # Avoid duplicates
            existing_titles = {(getattr(a, 'title', '') or '').lower() for a in results if isinstance(a, AnimeResult)}
            existing_titles.update({(a.get('title', '') or '').lower() for a in results if isinstance(a, dict)})
            if (r.get("title", "") or "").lower() not in existing_titles:
                results.append(r)

    return {
        "filters": filters,
        "raw_query": user_query,
        "results": results[:24],
        "total": len(results),
    }


@router.get("/similar/{anime_id}")
async def get_similar(anime_id: int, count: int = Query(10, ge=1, le=20)):
    """Get content-based recommendations for a given anime."""
    if not recommendation_engine.is_ready():
        return {"results": [], "model_ready": False, "message": "Recommendation model is loading..."}

    similar = recommendation_engine.get_similar(anime_id, top_n=count)
    return {"results": similar, "model_ready": True}


@router.get("/status")
async def ai_status():
    """Check AI engine status."""
    return {
        "nlp_search": True,
        "recommendation_engine": recommendation_engine.is_ready(),
        "corpus_size": recommendation_engine.corpus_size(),
    }
