"""
Anime Discovery Engine — AniList Service
GraphQL API integration with AniList for rich anime queries.
"""
import httpx
import asyncio
import os
from typing import Optional
from backend.models.schemas import AnimeResult
from backend.cache import search_cache, trending_cache, get_cache_key

GRAPHQL_URL = "https://graphql.anilist.co"

MAX_RETRIES = 3

ANILIST_TOKEN = os.getenv("ANILIST_TOKEN")
ANILIST_USER_AGENT = os.getenv("ANILIST_USER_AGENT", "AnimeDiscoveryEngine/1.0")
ANILIST_REFERER = os.getenv("ANILIST_REFERER")


async def _query(query: str, variables: dict = None) -> dict:
    """Execute a GraphQL query against AniList with retry logic."""
    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": ANILIST_USER_AGENT,
            }
            if ANILIST_TOKEN:
                headers["Authorization"] = f"Bearer {ANILIST_TOKEN}"
            if ANILIST_REFERER:
                headers["Referer"] = ANILIST_REFERER

            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                response = await client.post(
                    GRAPHQL_URL,
                    json={"query": query, "variables": variables or {}},
                )
                response.raise_for_status()
                return response.json()
        except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout) as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                wait = 1.5 * (attempt + 1)
                print(f"[AniList] Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}. Retrying in {wait}s...")
                await asyncio.sleep(wait)
            else:
                print(f"[AniList] All {MAX_RETRIES} attempts failed: {e}")
    raise last_error


def _parse_media(media: dict) -> AnimeResult:
    """Parse AniList media into unified AnimeResult."""
    title = media.get("title", {})
    cover = media.get("coverImage", {})
    studios_data = media.get("studios", {}).get("nodes", [])
    genres = media.get("genres", [])

    return AnimeResult(
        id=media.get("id", 0),
        anilist_id=media.get("id"),
        mal_id=media.get("idMal"),
        title=title.get("romaji") or title.get("english") or "Unknown",
        title_english=title.get("english"),
        title_japanese=title.get("native"),
        image_url=cover.get("large") or cover.get("medium") or "",
        large_image_url=cover.get("extraLarge") or cover.get("large") or "",
        synopsis=media.get("description", ""),
        score=round(media.get("averageScore", 0) / 10, 1) if media.get("averageScore") else None,
        episodes=media.get("episodes"),
        status=media.get("status"),
        year=media.get("seasonYear"),
        season=media.get("season"),
        type=media.get("format"),
        genres=genres,
        studios=[s.get("name", "") for s in studios_data if s.get("isAnimationStudio", True)],
        source="anilist",
    )


MEDIA_FIELDS = """
    id
    idMal
    title { romaji english native }
    coverImage { extraLarge large medium }
    bannerImage
    description(asHtml: false)
    averageScore
    episodes
    status
    format
    season
    seasonYear
    genres
    studios(isMain: true) { nodes { name isAnimationStudio } }
"""


async def get_anilist_id_by_mal_id(mal_id: int) -> int | None:
    """Resolve AniList ID from MAL ID."""
    query_str = """
    query ($malId: Int) {
        Media(idMal: $malId, type: ANIME) {
            id
        }
    }
    """
    try:
        data = await _query(query_str, {"malId": mal_id})
        return data.get("data", {}).get("Media", {}).get("id")
    except:
        return None


async def get_airing_schedule_by_mal_id(mal_id: int) -> dict:
    """Get AniList airing metadata for a MAL ID."""
    query_str = """
    query ($malId: Int) {
        Media(idMal: $malId, type: ANIME) {
            status
            nextAiringEpisode {
                episode
                airingAt
            }
        }
    }
    """
    data = await _query(query_str, {"malId": mal_id})
    media = data.get("data", {}).get("Media") or {}
    next_airing = media.get("nextAiringEpisode") or {}

    return {
        "provider_status": media.get("status"),
        "is_airing": media.get("status") == "RELEASING",
        "next_airing_episode": next_airing.get("episode"),
        "next_airing_at": next_airing.get("airingAt"),
    }


async def get_trending(page: int = 1, per_page: int = 24) -> dict:
    """Get currently trending anime."""
    cache_key = get_cache_key("anilist_trending", page)
    if cache_key in trending_cache:
        return trending_cache[cache_key]

    query_str = f"""
    query ($page: Int, $perPage: Int) {{
        Page(page: $page, perPage: $perPage) {{
            pageInfo {{ total currentPage hasNextPage }}
            media(sort: TRENDING_DESC, type: ANIME) {{
                {MEDIA_FIELDS}
            }}
        }}
    }}
    """
    data = await _query(query_str, {"page": page, "perPage": per_page})
    page_data = data.get("data", {}).get("Page", {})
    page_info = page_data.get("pageInfo", {})

    results = {
        "data": [_parse_media(m) for m in page_data.get("media", [])],
        "total": page_info.get("total", 0),
        "has_next": page_info.get("hasNextPage", False),
        "page": page,
    }
    trending_cache[cache_key] = results
    return results


async def search_by_tags(
    tags: list[str] = None,
    genres: list[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    sort: str = "SCORE_DESC",
    page: int = 1,
    per_page: int = 24,
) -> dict:
    """Search anime by AniList tags and genres."""
    cache_key = get_cache_key("anilist_tags", str(tags), str(genres), year_from, year_to, page)
    if cache_key in search_cache:
        return search_cache[cache_key]

    variables = {"page": page, "perPage": per_page, "sort": sort}

    # Build dynamic query with optional filters
    filter_args = ["$page: Int", "$perPage: Int", "$sort: [MediaSort]"]
    media_args = ["sort: $sort", "type: ANIME"]

    if tags:
        filter_args.append("$tags: [String]")
        media_args.append("tag_in: $tags")
        variables["tags"] = tags

    if genres:
        filter_args.append("$genres: [String]")
        media_args.append("genre_in: $genres")
        variables["genres"] = genres

    if year_from:
        filter_args.append("$yearGreater: FuzzyDateInt")
        media_args.append("startDate_greater: $yearGreater")
        variables["yearGreater"] = year_from * 10000  # AniList uses YYYYMMDD format

    if year_to:
        filter_args.append("$yearLess: FuzzyDateInt")
        media_args.append("startDate_lesser: $yearLess")
        variables["yearLess"] = year_to * 10000 + 1231

    query_str = f"""
    query ({", ".join(filter_args)}) {{
        Page(page: $page, perPage: $perPage) {{
            pageInfo {{ total currentPage hasNextPage }}
            media({", ".join(media_args)}) {{
                {MEDIA_FIELDS}
            }}
        }}
    }}
    """

    data = await _query(query_str, variables)
    page_data = data.get("data", {}).get("Page", {})
    page_info = page_data.get("pageInfo", {})

    results = {
        "data": [_parse_media(m) for m in page_data.get("media", [])],
        "total": page_info.get("total", 0),
        "has_next": page_info.get("hasNextPage", False),
        "page": page,
    }
    search_cache[cache_key] = results
    return results


async def get_anime_detail(anilist_id: int) -> dict:
    """Get detailed anime info from AniList."""
    cache_key = get_cache_key("anilist_detail", anilist_id)
    if cache_key in search_cache:
        return search_cache[cache_key]

    query_str = f"""
    query ($id: Int) {{
        Media(id: $id, type: ANIME) {{
            {MEDIA_FIELDS}
            bannerImage
            trailer {{ id site thumbnail }}
            duration
            startDate {{ year month day }}
            endDate {{ year month day }}
            popularity
            trending
            favourites
            characters(sort: ROLE, perPage: 12) {{
                nodes {{
                    name {{ full }}
                    image {{ medium }}
                }}
            }}
            recommendations(perPage: 8, sort: RATING_DESC) {{
                nodes {{
                    mediaRecommendation {{
                        {MEDIA_FIELDS}
                    }}
                }}
            }}
        }}
    }}
    """
    data = await _query(query_str, {"id": anilist_id})
    media = data.get("data", {}).get("Media", {})

    result = _parse_media(media)

    # Add extra detail fields
    trailer = media.get("trailer", {}) or {}
    trailer_url = None
    if trailer.get("site") == "youtube":
        trailer_url = f"https://www.youtube.com/watch?v={trailer.get('id')}"

    start_date = media.get("startDate", {}) or {}
    end_date = media.get("endDate", {}) or {}
    aired_str = ""
    if start_date.get("year"):
        aired_str = f"{start_date.get('year')}"
        if start_date.get("month"):
            aired_str = f"{start_date.get('month')}/{aired_str}"

    characters = []
    for char_node in (media.get("characters", {}).get("nodes", []) or []):
        characters.append({
            "name": char_node.get("name", {}).get("full", ""),
            "image_url": char_node.get("image", {}).get("medium", ""),
        })

    recommendations = []
    for rec_node in (media.get("recommendations", {}).get("nodes", []) or []):
        rec_media = rec_node.get("mediaRecommendation")
        if rec_media:
            recommendations.append(_parse_media(rec_media))

    detail = {
        **result.model_dump(),
        "banner_image": media.get("bannerImage"),
        "trailer_url": trailer_url,
        "duration": f"{media.get('duration', 'N/A')} min" if media.get("duration") else None,
        "aired": aired_str,
        "popularity": media.get("popularity"),
        "characters": characters,
        "recommendations": [r.model_dump() for r in recommendations],
    }

    search_cache[cache_key] = detail
    return detail


async def get_spotlight(count: int = 5) -> list[dict]:
    """Get top spotlight anime for the hero section."""
    cache_key = get_cache_key("anilist_spotlight", count)
    if cache_key in trending_cache:
        return trending_cache[cache_key]

    query_str = f"""
    query ($perPage: Int) {{
        Page(page: 1, perPage: $perPage) {{
            media(sort: TRENDING_DESC, type: ANIME, isAdult: false) {{
                {MEDIA_FIELDS}
                bannerImage
                trailer {{ id site thumbnail }}
            }}
        }}
    }}
    """
    data = await _query(query_str, {"perPage": count})
    media_list = data.get("data", {}).get("Page", {}).get("media", [])

    results = []
    for media in media_list:
        parsed = _parse_media(media)
        trailer = media.get("trailer", {}) or {}
        trailer_url = None
        if trailer.get("site") == "youtube":
            trailer_url = f"https://www.youtube.com/watch?v={trailer.get('id')}"
        results.append({
            **parsed.model_dump(),
            "banner_image": media.get("bannerImage"),
            "trailer_url": trailer_url,
        })

    trending_cache[cache_key] = results
    return results
