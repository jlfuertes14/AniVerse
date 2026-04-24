"""
Anime Discovery Engine — NLP Vibe Search (Algorithmic)
Converts natural language queries into structured anime search filters
using keyword matching and regex, without needing an external LLM.
"""
import re

# Known anime metadata vocabularies mapping to AniList/Jikan tags and genres
GENRES = {
    "action", "adventure", "comedy", "drama", "fantasy", "horror", 
    "mystery", "romance", "sci-fi", "slice of life", "sports", 
    "suspense", "ecchi", "supernatural", "thriller", "psychological", "mecha"
}

TAGS = {
    "cyberpunk": "Cyberpunk",
    "isekai": "Isekai",
    "reincarnation": "Reincarnation",
    "post apocalyptic": "Post-Apocalyptic",
    "apocalyptic": "Post-Apocalyptic",
    "post-apocalyptic": "Post-Apocalyptic",
    "zombie": "Zombies",
    "vampire": "Vampire",
    "samurai": "Samurai",
    "ninja": "Ninja",
    "magic": "Magic",
    "school": "School",
    "space": "Space",
    "time travel": "Time Travel",
    "military": "Military",
    "music": "Music",
    "martial arts": "Martial Arts",
    "super power": "Super Power",
    "dark": "Dark",
    "gore": "Gore",
    "urban": "Urban",
    "iyashikei": "Iyashikei",
    "shounen": "Shounen",
    "shoujo": "Shoujo",
    "seinen": "Seinen",
    "josei": "Josei"
}

MOODS = {"dark", "lighthearted", "action-packed", "emotional", "chill", "mysterious", "hype", "sad", "funny"}


async def parse_natural_language(user_query: str) -> dict:
    """Algorithmically parse a natural language request into structured filters."""
    query_lower = user_query.lower()
    
    filters = {
        "genres": [],
        "tags": [],
        "mood": None,
        "year_from": None,
        "year_to": None,
        "description": user_query
    }

    # 1. Extract Years/Decades using Regex
    # Match "90s", "80s", "2010s"
    decade_match = re.search(r'\b(1980|1990|2000|2010|2020|80|90)s\b', query_lower)
    if decade_match:
        val = decade_match.group(1)
        if val == "80": year = 1980
        elif val == "90": year = 1990
        else: year = int(val)
        
        filters["year_from"] = year
        filters["year_to"] = year + 9

    # Match specific year "from 2015" or simply "2015"
    else:
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', query_lower)
        if year_match:
            year = int(year_match.group(1))
            filters["year_from"] = year
            filters["year_to"] = year

    # 2. Extract Genres
    for genre in GENRES:
        # Match standalone words
        if re.search(rf'\b{genre}\b', query_lower):
            # Title case the genre for the API
            filters["genres"].append(genre.title() if genre != "sci-fi" else "Sci-Fi")

    # 3. Extract Tags
    for keyword, tag_name in TAGS.items():
        if re.search(rf'\b{keyword}\b', query_lower):
            if tag_name not in filters["tags"]:
                filters["tags"].append(tag_name)

    # 4. Extract Mood
    for mood in MOODS:
        if re.search(rf'\b{mood}\b', query_lower):
            filters["mood"] = mood.title()
            # Also map dark/psychological to tags if not already there
            if mood == "dark" and "Dark" not in filters["tags"]:
                filters["tags"].append("Dark")
            break

    # If it found zero filters, it might just be a regular title search
    # But since it hit this endpoint, we'll return what we found (even if empty)
    # The frontend will fall back if no results.
    
    return {"filters": filters, "raw_query": user_query, "error": None}
