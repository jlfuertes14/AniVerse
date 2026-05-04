import asyncio
from backend.database import get_db

async def clear_comments():
    db = get_db()
    result = await db["comments"].delete_many({})
    print(f"Cleared {result.deleted_count} comments.")

if __name__ == "__main__":
    asyncio.run(clear_comments())
