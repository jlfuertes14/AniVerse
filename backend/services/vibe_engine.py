"""
Anime Discovery Engine — Vibe Engine
Maps aesthetic "vibe" presets to API query parameters.
"""
from typing import Optional
from backend.models.schemas import VibePreset, AnimeResult
from backend.services import anilist_service, jikan_service
from backend.cache import search_cache, get_cache_key

# Vibe preset definitions
VIBE_PRESETS: dict[str, VibePreset] = {
    "90s-aesthetic": VibePreset(
        id="90s-aesthetic",
        name="90s Aesthetic",
        emoji="📼",
        description="Retro charm, cel animation, and that unmistakable 90s anime atmosphere",
        genres=["Action", "Sci-Fi", "Adventure"],
        tags=["Super Power", "Martial Arts"],
        year_from=1990,
        year_to=1999,
    ),
    "cyberpunk": VibePreset(
        id="cyberpunk",
        name="Cyberpunk Nights",
        emoji="🌃",
        description="Neon-lit dystopias, hackers, and high-tech meets low-life",
        genres=["Sci-Fi", "Action"],
        tags=["Cyberpunk", "Robots", "Urban"],
        year_from=None,
        year_to=None,
    ),
    "studio-mappa": VibePreset(
        id="studio-mappa",
        name="Studio MAPPA",
        emoji="🎬",
        description="The studio behind AOT Final Season, JJK, and Chainsaw Man",
        studios=["MAPPA"],
        genres=[],
        tags=[],
    ),
    "dark-psychological": VibePreset(
        id="dark-psychological",
        name="Dark & Psychological",
        emoji="🌑",
        description="Mind-bending thrillers that keep you up at night",
        genres=["Suspense"],
        tags=["Psychological", "Thriller", "Gore", "Dark"],
    ),
    "shonen-hype": VibePreset(
        id="shonen-hype",
        name="Shonen Hype Train",
        emoji="🔥",
        description="Power-ups, epic battles, and the bonds of friendship",
        genres=["Action"],
        tags=["Shounen", "Super Power", "Martial Arts"],
        demographic="Shounen",
    ),
    "cozy-sol": VibePreset(
        id="cozy-sol",
        name="Cozy Slice of Life",
        emoji="☕",
        description="Warm, healing, and wholesome — the anime comfort zone",
        genres=["Slice of Life", "Comedy"],
        tags=["Iyashikei", "Slice of Life", "CGDCT"],
    ),
    "isekai-adventure": VibePreset(
        id="isekai-adventure",
        name="Isekai Adventure",
        emoji="🌀",
        description="Transported to another world with overpowered abilities",
        genres=["Fantasy", "Adventure"],
        tags=["Isekai", "Reincarnation"],
    ),
    "romance-drama": VibePreset(
        id="romance-drama",
        name="Romance & Drama",
        emoji="💕",
        description="Heart-wrenching love stories and emotional rollercoasters",
        genres=["Romance", "Drama"],
        tags=["Romance", "Love Triangle"],
    ),
}


def get_all_vibes() -> list[VibePreset]:
    """Get all available vibe presets."""
    return list(VIBE_PRESETS.values())


def get_vibe(vibe_id: str) -> Optional[VibePreset]:
    """Get a specific vibe preset."""
    return VIBE_PRESETS.get(vibe_id)


async def search_by_vibe(vibe_id: str, page: int = 1) -> dict:
    """Search anime based on a vibe preset using AniList and Jikan."""
    vibe = VIBE_PRESETS.get(vibe_id)
    if not vibe:
        return {"data": [], "total": 0, "has_next": False, "page": page}

    cache_key = get_cache_key("vibe_search", vibe_id, page)
    if cache_key in search_cache:
        return search_cache[cache_key]

    all_results: list[AnimeResult] = []

    # If studio-specific vibe, use Jikan producer search
    if vibe.studios:
        try:
            # Search Jikan for studio-specific anime
            studios_data = await jikan_service.get_studios()
            studio_ids = [
                str(s["mal_id"]) for s in studios_data
                if any(studio.lower() in s["name"].lower() for studio in vibe.studios)
            ]
            if studio_ids:
                jikan_results = await jikan_service.search_anime(
                    producers=",".join(studio_ids[:3]),
                    page=page,
                    limit=24,
                )
                all_results.extend(jikan_results.get("data", []))
        except Exception:
            pass

    # Use AniList for tag-based search
    if vibe.tags or vibe.genres:
        try:
            anilist_results = await anilist_service.search_by_tags(
                tags=vibe.tags if vibe.tags else None,
                genres=vibe.genres if vibe.genres else None,
                year_from=vibe.year_from,
                year_to=vibe.year_to,
                page=page,
                per_page=24,
            )
            all_results.extend(anilist_results.get("data", []))
        except Exception:
            pass

    # Deduplicate by title
    seen_titles = set()
    unique_results = []
    for r in all_results:
        title_key = (r.title or "").lower().strip()
        if title_key and title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_results.append(r)

    # Sort by score (descending)
    unique_results.sort(key=lambda x: x.score or 0, reverse=True)

    results = {
        "data": unique_results[:24],
        "total": len(unique_results),
        "has_next": len(unique_results) > 24,
        "page": page,
    }
    search_cache[cache_key] = results
    return results
