"""
Anime Discovery Engine -- Cache Layer
In-memory hot cache plus Mongo-backed persistent cache helpers.
"""
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

from cachetools import TTLCache

# Cache for genre/studio lists (1 hour TTL)
metadata_cache = TTLCache(maxsize=50, ttl=3600)

# Cache for search results and trending (5 min TTL)
search_cache = TTLCache(maxsize=200, ttl=300)

# Cache for trending data (10 min TTL)
trending_cache = TTLCache(maxsize=50, ttl=600)

_singleflight_locks: dict[str, asyncio.Lock] = {}


def get_cache_key(*args) -> str:
    """Generate a cache key from arguments."""
    return ":".join(str(a) if a is not None else "" for a in args)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def ttl_to_expiry(ttl_seconds: int) -> datetime:
    return utc_now() + timedelta(seconds=ttl_seconds)


def is_fresh(doc: dict | None) -> bool:
    if not doc:
        return False
    expires_at = parse_datetime(doc.get("expires_at"))
    if not expires_at:
        return False
    return expires_at > utc_now()


def get_singleflight_lock(key: str) -> asyncio.Lock:
    lock = _singleflight_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _singleflight_locks[key] = lock
    return lock


async def get_persistent_cache(key: str, *, allow_stale: bool = False) -> dict | None:
    from backend.database import get_db

    doc = await get_db()["cache"].find_one({"key": key})
    if not doc:
        return None
    if allow_stale or is_fresh(doc):
        return doc
    return None


async def set_persistent_cache(
    key: str,
    data: Any,
    *,
    ttl_seconds: int,
    meta: dict | None = None,
) -> None:
    from backend.database import get_db

    payload = {
        "key": key,
        "status": "ok",
        "data": data,
        "updated_at": utc_now_iso(),
        "expires_at": ttl_to_expiry(ttl_seconds),
    }
    if meta:
        payload.update(meta)
    await get_db()["cache"].update_one({"key": key}, {"$set": payload}, upsert=True)


async def set_persistent_failure(
    key: str,
    *,
    status: str,
    ttl_seconds: int,
    detail: str | None = None,
    meta: dict | None = None,
) -> None:
    from backend.database import get_db

    payload = {
        "key": key,
        "status": status,
        "updated_at": utc_now_iso(),
        "expires_at": ttl_to_expiry(ttl_seconds),
    }
    if detail:
        payload["detail"] = detail[:400]
    if meta:
        payload.update(meta)
    await get_db()["cache"].update_one({"key": key}, {"$set": payload}, upsert=True)


async def get_persistent_failure(key: str) -> dict | None:
    doc = await get_persistent_cache(key)
    if doc and doc.get("status") != "ok":
        return doc
    return None
