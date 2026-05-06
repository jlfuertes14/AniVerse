"""
Anime Discovery Engine — NLP Vibe Search (Powered by Groq)
Converts natural language queries into structured anime search filters
using Groq's LLM with a fallback to algorithmic keyword matching.
"""
import re
import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

# Initialize Groq client
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Known anime metadata vocabularies (Legacy Fallback)
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
    """Parse a natural language request using Groq (Primary) or Keywords (Fallback)."""
    
    # --- Try Groq API First ---
    if client:
        try:
            prompt = f"""
            You are an anime metadata expert. Your task is to parse a user's natural language request for anime recommendations into structured JSON filters.
            
            User Query: "{user_query}"
            
            Output exactly this JSON format:
            {{
                "filters": {{
                    "genres": ["Genre1", "Genre2"],
                    "tags": ["Tag1", "Tag2"],
                    "year_from": int or null,
                    "year_to": int or null,
                    "description": "Short summary of the vibe for vector search",
                    "title": "Specific anime title mentioned (if any, e.g. Black Clover)"
                }}
            }}
            
            Rules:
            - Use standard genres: Action, Adventure, Comedy, Drama, Fantasy, Horror, Mystery, Romance, Sci-Fi, Slice of Life, Sports, Supernatural, Thriller.
            - Tags can be themes like: Cyberpunk, Isekai, Samurai, School, Magic, Post-Apocalyptic, Gore, Dark, Urban, Reincarnation.
            - If a specific year is mentioned, set year_from and year_to to that year.
            - If a decade is mentioned (e.g., 90s), set year_from=1990, year_to=1999.
            - If no filters apply, leave them as null or empty lists.
            - Description should be a condensed version of the user's intent suitable for text search.
            - **Title Field**: If the user is looking for something "similar to [Anime Title]", OR if the user is describing an anime by character names or plot points (e.g. "basketball anime with kuroko"), identify the most likely official title and put it here.
            - ONLY output the JSON block. Nothing else.
            """

            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                response_format={"type": "json_object"}
            )
            
            result = json.loads(completion.choices[0].message.content)
            if "filters" in result:
                return {"filters": result["filters"], "raw_query": user_query, "engine": "groq"}
        except Exception as e:
            print(f"[AI] Groq Error: {e}")
            # Fall through to legacy fallback

    # --- Legacy Keyword Fallback ---
    print("[AI] Using legacy keyword fallback")
    query_lower = user_query.lower()
    filters = {
        "genres": [],
        "tags": [],
        "mood": None,
        "year_from": None,
        "year_to": None,
        "description": user_query
    }

    decade_match = re.search(r'\b(1980|1990|2000|2010|2020|80|90)s\b', query_lower)
    if decade_match:
        val = decade_match.group(1)
        year = 1980 if val == "80" else 1990 if val == "90" else int(val)
        filters["year_from"], filters["year_to"] = year, year + 9
    else:
        year_match = re.search(r'\b(19\d{2}|20\d{2})\b', query_lower)
        if year_match:
            year = int(year_match.group(1))
            filters["year_from"], filters["year_to"] = year, year

    for genre in GENRES:
        if re.search(rf'\b{genre}\b', query_lower):
            filters["genres"].append(genre.title() if genre != "sci-fi" else "Sci-Fi")

    for keyword, tag_name in TAGS.items():
        if re.search(rf'\b{keyword}\b', query_lower):
            if tag_name not in filters["tags"]:
                filters["tags"].append(tag_name)

    for mood in MOODS:
        if re.search(rf'\b{mood}\b', query_lower):
            filters["mood"] = mood.title()
            if mood == "dark" and "Dark" not in filters["tags"]:
                filters["tags"].append("Dark")
            break
    
    return {"filters": filters, "raw_query": user_query, "engine": "fallback"}
