import asyncio
from backend.services.shiroko_service import _run_shiroko_scraper

async def run():
    res = _run_shiroko_scraper(182300, 1)
    print("Result:", res)

asyncio.run(run())
