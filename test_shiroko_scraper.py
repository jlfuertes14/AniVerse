import asyncio
from scraper import shiroko_scrape_episode

async def run():
    res = await shiroko_scrape_episode(182300, 1)
    print("Result:", res)

asyncio.run(run())
