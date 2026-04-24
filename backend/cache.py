"""
Anime Discovery Engine — Cache Layer
TTL-based in-memory cache for API responses.
"""
from cachetools import TTLCache

# Cache for genre/studio lists (1 hour TTL)
metadata_cache = TTLCache(maxsize=50, ttl=3600)

# Cache for search results and trending (5 min TTL)
search_cache = TTLCache(maxsize=200, ttl=300)

# Cache for trending data (10 min TTL)
trending_cache = TTLCache(maxsize=50, ttl=600)


def get_cache_key(*args) -> str:
    """Generate a cache key from arguments."""
    return ":".join(str(a) for a in args if a is not None)
