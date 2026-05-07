"""Safely migrate stale Re:ANIME cache rows that were saved under AniList IDs.

Default mode is dry-run. Use ``--apply`` to write changes.
"""
import argparse
import asyncio
from collections import defaultdict
from datetime import datetime, timezone

import httpx

from backend.database import get_db

JIKAN_BASE_URL = "https://api.jikan.moe/v4"
ANILIST_URL = "https://graphql.anilist.co"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _is_valid_mal_id(client: httpx.AsyncClient, mal_id: int) -> bool:
    try:
        response = await client.get(f"{JIKAN_BASE_URL}/anime/{mal_id}")
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        response.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"Jikan validation failed for id={mal_id}: {exc}") from exc
    return False


async def _get_mal_id_for_anilist_id(client: httpx.AsyncClient, anilist_id: int) -> int | None:
    query = """
    query ($id: Int) {
      Media(id: $id, type: ANIME) {
        idMal
      }
    }
    """
    try:
        response = await client.post(
            ANILIST_URL,
            json={"query": query, "variables": {"id": anilist_id}},
        )
        response.raise_for_status()
        payload = response.json()
        media = (payload.get("data") or {}).get("Media") or {}
        return media.get("idMal")
    except Exception as exc:
        raise RuntimeError(f"AniList lookup failed for id={anilist_id}: {exc}") from exc


async def _resolve_id_status(http_client: httpx.AsyncClient, stored_id: int) -> tuple[str, int | None]:
    if await _is_valid_mal_id(http_client, stored_id):
        return "valid_mal", stored_id

    mapped_mal_id = await _get_mal_id_for_anilist_id(http_client, stored_id)
    if mapped_mal_id and mapped_mal_id != stored_id:
        return "wrong_anilist_id", mapped_mal_id

    return "unknown", None


async def _merge_provider_mapping(db, old_doc: dict, new_mal_id: int, apply_changes: bool) -> str:
    target = await db["provider_mappings"].find_one({"mal_id": new_mal_id, "provider": "reanime"})
    merged = {
        "provider": "reanime",
        "mal_id": new_mal_id,
        "anilist_id": new_mal_id,
        "title": (target or {}).get("title") or old_doc.get("title"),
        "slug": (target or {}).get("slug") or old_doc.get("slug"),
        "latest_episode": (target or {}).get("latest_episode") or old_doc.get("latest_episode"),
        "last_mapped_at": (target or {}).get("last_mapped_at") or old_doc.get("last_mapped_at"),
        "last_scraped_at": (target or {}).get("last_scraped_at") or old_doc.get("last_scraped_at"),
        "cleanup_migrated_from_id": old_doc.get("mal_id"),
        "cleanup_migrated_at": _utc_now_iso(),
    }
    merged = {key: value for key, value in merged.items() if value is not None}

    if apply_changes:
        await db["provider_mappings"].update_one(
            {"mal_id": new_mal_id, "provider": "reanime"},
            {"$set": merged},
            upsert=True,
        )
        await db["provider_mappings"].delete_one({"_id": old_doc["_id"]})

    return "merged existing mapping" if target else "migrated mapping"


async def _merge_stream_documents(db, old_doc: dict, new_mal_id: int, apply_changes: bool) -> str:
    query = {"mal_id": new_mal_id, "episode": old_doc["episode"], "source": "reanime"}
    target = await db["streams"].find_one(query)

    merged = {
        "mal_id": new_mal_id,
        "anilist_id": new_mal_id,
        "episode": old_doc["episode"],
        "source": "reanime",
        "stream_url": (target or {}).get("stream_url") or old_doc.get("stream_url"),
        "embed_url": (target or {}).get("embed_url") or old_doc.get("embed_url"),
        "referer_url": (target or {}).get("referer_url") or old_doc.get("referer_url"),
        "subtitles": (target or {}).get("subtitles") or old_doc.get("subtitles", []),
        "updated_at": (target or {}).get("updated_at") or old_doc.get("updated_at"),
        "cleanup_migrated_from_id": old_doc.get("mal_id"),
        "cleanup_migrated_at": _utc_now_iso(),
    }
    merged = {key: value for key, value in merged.items() if value is not None}

    if apply_changes:
        await db["streams"].update_one(query, {"$set": merged}, upsert=True)
        await db["streams"].delete_one({"_id": old_doc["_id"]})

    return "merged existing stream" if target else "migrated stream"


async def _clear_reanime_latest_cache(db, apply_changes: bool) -> None:
    if apply_changes:
        await db["cache"].delete_one({"key": "latest_releases_reanime"})


async def run_cleanup(apply_changes: bool) -> None:
    db = get_db()
    mapping_docs = await db["provider_mappings"].find({"provider": "reanime"}).to_list(length=None)
    stream_docs = await db["streams"].find({"source": "reanime"}).to_list(length=None)

    grouped: dict[int, dict[str, list[dict]]] = defaultdict(lambda: {"mappings": [], "streams": []})
    for document in mapping_docs:
        grouped[int(document.get("mal_id", 0))]["mappings"].append(document)
    for document in stream_docs:
        grouped[int(document.get("mal_id", document.get("anilist_id", 0)))]["streams"].append(document)

    inspected = 0
    migrated_mappings = 0
    migrated_streams = 0
    skipped = 0

    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as http_client:
        for stored_id in sorted(grouped.keys()):
            if stored_id <= 0:
                continue
            inspected += 1
            try:
                status, corrected_mal_id = await _resolve_id_status(http_client, stored_id)
            except Exception as exc:
                print(f"SKIP id={stored_id}: lookup error: {exc}")
                skipped += 1
                continue

            if status != "wrong_anilist_id" or not corrected_mal_id:
                print(f"KEEP id={stored_id}: status={status}")
                continue

            print(f"MIGRATE id={stored_id} -> mal_id={corrected_mal_id}")

            for mapping_doc in grouped[stored_id]["mappings"]:
                result = await _merge_provider_mapping(db, mapping_doc, corrected_mal_id, apply_changes)
                migrated_mappings += 1
                print(f"  mapping: {result} title={mapping_doc.get('title')!r}")

            for stream_doc in grouped[stored_id]["streams"]:
                result = await _merge_stream_documents(db, stream_doc, corrected_mal_id, apply_changes)
                migrated_streams += 1
                print(
                    f"  stream: {result} episode={stream_doc.get('episode')} "
                    f"embed={bool(stream_doc.get('embed_url'))} stream={bool(stream_doc.get('stream_url'))}"
                )

    if migrated_mappings or migrated_streams:
        print("Clearing Re:ANIME latest releases cache so it can repopulate cleanly.")
        await _clear_reanime_latest_cache(db, apply_changes)

    mode = "APPLY" if apply_changes else "DRY-RUN"
    print(
        f"{mode} summary: inspected={inspected}, migrated_mappings={migrated_mappings}, "
        f"migrated_streams={migrated_streams}, skipped={skipped}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely clean stale Re:ANIME cache rows.")
    parser.add_argument("--apply", action="store_true", help="Write the migration changes to MongoDB.")
    args = parser.parse_args()
    asyncio.run(run_cleanup(apply_changes=args.apply))


if __name__ == "__main__":
    main()
