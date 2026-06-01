import asyncio
import httpx

async def get_anilist(mal_id):
    query = '''
    query ($idMal: Int) {
      Media(idMal: $idMal, type: ANIME) {
        id
      }
    }
    '''
    async with httpx.AsyncClient() as client:
        r = await client.post('https://graphql.anilist.co', json={'query': query, 'variables': {'idMal': mal_id}})
        print(r.json())

asyncio.run(get_anilist(59983))
