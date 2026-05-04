import asyncio
import httpx
from backend.database import init_db, get_db

async def seed_banners():
    print("Seeding banners...")
    await init_db()
    db = get_db()
    
    # We will clear the old invalid banners
    await db["banners"].delete_many({})
    
    urls = []
    
    # Fetch 15 images from waifu.im
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        for _ in range(15):
            try:
                res = await client.get("https://api.waifu.im/images?IncludedTags=waifu&IsNsfw=False")
                data = res.json()
                if "items" in data and len(data["items"]) > 0:
                    urls.append(data["items"][0]["url"])
            except Exception as e:
                print(f"Error fetching: {e}")
    
    if not urls:
        print("No URLs fetched.")
        return
    
    # Sync to DB
    for url in urls:
        await db["banners"].update_one(
            {"url": url},
            {"$set": {"url": url}},
            upsert=True
        )
    
    print(f"Successfully seeded {len(urls)} curated banners from waifu.im.")

if __name__ == "__main__":
    asyncio.run(seed_banners())
