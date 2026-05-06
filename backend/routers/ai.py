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
    Natural language anime search powered by Groq.
    Send: { "query": "anime similar to Black Clover" }
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

    # Step 2: If a specific title is mentioned, try finding it for a direct similarity search
    target_anime = None
    if filters.get("title") and recommendation_engine.is_ready():
        title_to_find = filters["title"].lower()
        for anime in recommendation_engine._corpus:
            if title_to_find in (anime.get("title", "") or "").lower() or \
               title_to_find in (anime.get("title_english", "") or "").lower():
                target_anime = anime
                break

    # Step 3: Run the search
    results = []
    
    # 3a. If we found a target anime, get its similar items first
    if target_anime and recommendation_engine.is_ready():
        sim_id = target_anime.get("id")
        if sim_id:
            results = recommendation_engine.get_similar(sim_id, top_n=15)
            # Mark these as high-relevance
            for r in results:
                r["is_similarity_match"] = True

    # 3b. Search AniList by extracted filters (Tags/Genres) OR by identified Title
    try:
        al_data = []
        if filters.get("tags") or filters.get("genres"):
            anilist_results = await anilist_service.search_by_tags(
                tags=filters.get("tags"),
                genres=filters.get("genres"),
                year_from=filters.get("year_from"),
                year_to=filters.get("year_to"),
                page=1,
                per_page=24,
            )
            al_data = anilist_results.get("data", [])
        
        # If we have a title but no results from tags/similarity yet, search by title
        if not results and filters.get("title"):
            title_results = await anilist_service.search_anime(filters["title"])
            al_data.extend(title_results.get("data", []))

        # Merge with results, avoiding duplicates
        existing_titles = {(a.get('title', '') or '').lower() for a in results if isinstance(a, dict)}
        for a in al_data:
            if isinstance(a, AnimeResult):
                title = (a.title or "").lower()
                if title not in existing_titles:
                    results.append(a)
                    existing_titles.add(title)
            elif isinstance(a, dict):
                title = (a.get('title', '') or '').lower()
                if title not in existing_titles:
                    results.append(a)
                    existing_titles.add(title)
    except Exception:
        pass

    # 3c. Finally, search by text description (Vector Search)
    if recommendation_engine.is_ready():
        desc = filters.get("description", user_query)
        rec_results = recommendation_engine.search_by_text(desc, top_n=10)
        
        existing_titles = {(a.get('title', '') or '').lower() for a in results if isinstance(a, dict)}
        existing_titles.update({(getattr(a, 'title', '') or '').lower() for a in results if isinstance(a, AnimeResult)})
        
        for r in rec_results:
            if (r.get("title", "") or "").lower() not in existing_titles:
                results.append(r)

    return {
        "filters": filters,
        "raw_query": user_query,
        "results": results[:24],
        "total": len(results),
        "target_anime": target_anime.get("title") if target_anime else None,
        "engine": parsed.get("engine", "unknown")
    }


@router.get("/similar/{anime_id}")
async def get_similar(anime_id: int, count: int = Query(10, ge=1, le=20)):
    """Get content-based recommendations for a given anime."""
    if not recommendation_engine.is_ready():
        return {"results": [], "model_ready": False, "message": "Recommendation model is loading..."}

    similar = recommendation_engine.get_similar(anime_id, top_n=count)
    if not similar:
        similar = recommendation_engine.get_similar_by_mal(anime_id, top_n=count)
    return {"results": similar, "model_ready": True}


@router.get("/status")
async def ai_status():
    """Check AI engine status."""
    return {
        "nlp_search": True,
        "recommendation_engine": recommendation_engine.is_ready(),
        "corpus_size": recommendation_engine.corpus_size(),
    }
