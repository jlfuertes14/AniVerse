"""
Anime Discovery Engine — Airing Schedule Service
Stores one reference AnimeSchedule.net week and rehydrates it into the
current week's dates so the frontend can keep consuming monday→sunday buckets.
"""
import asyncio
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

from backend.database import get_db

SCRAPER_RUNNER = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "scraper_runner.py",
)
SCHEDULE_REFRESH_INTERVAL = timedelta(days=7)
DAY_KEYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
AIR_TYPE_ORDER = {
    "JPN": 0,
    "CHN": 1,
    "RAW": 2,
    "SUB": 3,
    "DUB": 4,
}


def _empty_schedule() -> dict:
    return {day: [] for day in DAY_KEYS}


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _serialize_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _week_start_utc(now: datetime | None = None) -> datetime:
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    midnight = current.replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - timedelta(days=midnight.weekday())


def _air_type_sort_key(value: str) -> tuple[int, str]:
    normalized = (value or "").strip().upper()
    return (AIR_TYPE_ORDER.get(normalized, 99), normalized)


def _compact_day_entries(shows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str, str], list[dict]] = {}
    for show in shows or []:
        key = (
            (show.get("route") or "").strip().lower(),
            (show.get("title") or "").strip().lower(),
            (show.get("episode") or "").strip().lower(),
        )
        grouped.setdefault(key, []).append(show)

    compacted = []
    for variants in grouped.values():
        variants.sort(
            key=lambda item: _parse_iso_datetime(item.get("airing_at")) or datetime.max.replace(tzinfo=timezone.utc)
        )
        base = dict(variants[0])

        seen_types = []
        timeline_parts = []
        for variant in variants:
            air_type = (variant.get("air_type") or "").strip().upper()
            if air_type and air_type not in seen_types:
                seen_types.append(air_type)

            variant_time = variant.get("airing_at") or ""
            parsed = _parse_iso_datetime(variant_time)
            if parsed:
                time_label = parsed.strftime("%I:%M %p")
                timeline_parts.append(f"{time_label} {air_type}".strip())
            elif variant.get("display_time"):
                timeline_parts.append(variant["display_time"])

        seen_types.sort(key=_air_type_sort_key)
        unique_timeline = list(dict.fromkeys(timeline_parts))

        base["air_type"] = " / ".join(seen_types)
        base["display_time"] = " · ".join(unique_timeline) if unique_timeline else base.get("display_time", "")
        base["variant_count"] = len(variants)
        base["variants"] = [
            {
                "air_type": (variant.get("air_type") or "").strip().upper(),
                "airing_at": variant.get("airing_at"),
                "display_time": variant.get("display_time"),
                "status": variant.get("status"),
            }
            for variant in variants
        ]
        base["image_url"] = ""
        base["is_filtered_out"] = any(bool(variant.get("is_filtered_out")) for variant in variants)
        compacted.append(base)

    compacted.sort(
        key=lambda item: _parse_iso_datetime(item.get("airing_at")) or datetime.max.replace(tzinfo=timezone.utc)
    )
    return compacted


def _compact_schedule(schedule_data: dict) -> dict:
    compacted = _empty_schedule()
    for day_key in DAY_KEYS:
        compacted[day_key] = _compact_day_entries(schedule_data.get(day_key, []))
    return compacted


def _rebase_schedule(reference_schedule: dict, now: datetime | None = None) -> dict:
    """
    Turn a stored reference week into the current week's dates while preserving
    each show's weekday/time recurrence.
    """
    current_week_start = _week_start_utc(now)
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    rebased = _empty_schedule()

    for day_index, day_key in enumerate(DAY_KEYS):
        target_day = current_week_start + timedelta(days=day_index)
        for show in reference_schedule.get(day_key, []) or []:
            show_copy = dict(show)
            base_airing = _parse_iso_datetime(show.get("airing_at"))

            if base_airing:
                shifted_airing = target_day.replace(
                    hour=base_airing.hour,
                    minute=base_airing.minute,
                    second=base_airing.second,
                    microsecond=base_airing.microsecond,
                    tzinfo=timezone.utc,
                )
                show_copy["airing_at"] = _serialize_datetime(shifted_airing)
                show_copy["reference_airing_at"] = show.get("airing_at")
                show_copy["week_offset_days"] = (shifted_airing.date() - base_airing.date()).days

                if show_copy.get("status") not in {"delayed", "delayed-air"}:
                    if shifted_airing <= current_time < shifted_airing + timedelta(minutes=30):
                        show_copy["status"] = "airing"
                    elif shifted_airing > current_time:
                        show_copy["status"] = "unaired"
                    else:
                        show_copy["status"] = "aired"
            else:
                show_copy.setdefault("reference_airing_at", None)
                show_copy.setdefault("week_offset_days", 0)

            rebased[day_key].append(show_copy)

    return _compact_schedule(rebased)


async def refresh_airing_schedule(force: bool = False):
    """Refresh the reference schedule scraped from AnimeSchedule.net."""
    db = get_db()

    if not force:
        meta = await db.metadata.find_one({"type": "airing_schedule"})
        if meta:
            last_refresh = _parse_iso_datetime(meta.get("last_refresh"))
            if last_refresh and datetime.now(timezone.utc) - last_refresh < SCHEDULE_REFRESH_INTERVAL:
                print("[Schedule] Cache is fresh, skipping refresh")
                return

    print("[Schedule] Refreshing airing schedule from scraper...")
    try:
        process = await asyncio.create_subprocess_exec(
            "python",
            SCRAPER_RUNNER,
            "anime_schedule",
            "{}",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            print(f"[Schedule] Scraper failed: {stderr.decode()}")
            return

        lines = stdout.decode().strip().split("\n")
        if not lines:
            print("[Schedule] Scraper returned no output")
            return

        raw_schedule = json.loads(lines[-1])
        reference_schedule = _compact_schedule(raw_schedule)
        reference_week_start = _week_start_utc()
        now_iso = datetime.now(timezone.utc).isoformat()

        await db.airing_schedule.delete_many({})
        await db.airing_schedule.insert_one(
            {
                "type": "weekly",
                "schedule_mode": "seasonal_recurring",
                "reference_week_start": _serialize_datetime(reference_week_start),
                "reference_data": reference_schedule,
                "data": _rebase_schedule(reference_schedule, reference_week_start),
                "updated_at": now_iso,
            }
        )

        await db.metadata.update_one(
            {"type": "airing_schedule"},
            {"$set": {"last_refresh": now_iso}},
            upsert=True,
        )
        print("[Schedule] Refresh completed successfully")
    except Exception as e:
        print(f"[Schedule] Error during refresh: {e}")


async def get_airing_schedule():
    """Return the current-week schedule while keeping weekday buckets unchanged."""
    db = get_db()
    doc = await db.airing_schedule.find_one({"type": "weekly"})
    if not doc:
        await refresh_airing_schedule(force=True)
        doc = await db.airing_schedule.find_one({"type": "weekly"})
        if not doc:
            return None

    reference_schedule = doc.get("reference_data") or doc.get("data") or _empty_schedule()
    return _rebase_schedule(reference_schedule)


async def schedule_scheduler():
    """Background task that keeps the seasonal reference schedule fresh."""
    print("[Schedule] Starting background scheduler...")
    while True:
        try:
            await refresh_airing_schedule()
        except Exception as e:
            print(f"[Schedule] Scheduler error: {e}")

        await asyncio.sleep(3600)
