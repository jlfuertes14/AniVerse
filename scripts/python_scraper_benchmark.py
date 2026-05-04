import asyncio
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scraper import scrape_animepahe_episode, scrape_animepahe_latest


async def benchmark_latest():
    started_at = time.perf_counter()
    data = await scrape_animepahe_latest()
    return {
        "action": "latest",
        "duration_ms": round((time.perf_counter() - started_at) * 1000),
        "count": len(data),
        "data": data,
    }


async def benchmark_episode(title: str, episode_number: int):
    started_at = time.perf_counter()
    data = await scrape_animepahe_episode(title, episode_number)
    return {
        "action": "episode",
        "duration_ms": round((time.perf_counter() - started_at) * 1000),
        "data": data,
    }


async def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "latest"

    if action == "latest":
        print(json.dumps(await benchmark_latest()))
        return

    if action == "episode":
        title = sys.argv[2] if len(sys.argv) > 2 else "One Piece"
        episode_number = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        print(json.dumps(await benchmark_episode(title, episode_number)))
        return

    raise ValueError(f"Unknown action: {action}")


if __name__ == "__main__":
    asyncio.run(main())
