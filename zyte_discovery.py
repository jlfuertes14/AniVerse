import os
import json
import requests
import pymongo
from dotenv import load_dotenv
from bs4 import BeautifulSoup
import time
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

ZYTE_API_KEY = os.getenv("ZYTE_API_KEY")
MONGODB_URI = os.getenv("MONGODB_URI")
MONGODB_DB = "aniverse"

class ZyteDiscovery:
    def __init__(self):
        if not ZYTE_API_KEY:
            raise ValueError("ZYTE_API_KEY not found in .env file!")
        
        self.client = pymongo.MongoClient(MONGODB_URI)
        self.db = self.client[MONGODB_DB]
        logger.info(f"Connected to MongoDB: {MONGODB_DB}")

    def search_anime(self, mal_id, title):
        logger.info(f"Starting discovery for: {title} (MAL: {mal_id})")
        
        # Search API URL for AnimePahe
        search_url = f"https://animepahe.pw/api?m=search&q={requests.utils.quote(title)}"
        
        try:
            # Call Zyte API with Browser Rendering for the API endpoint
            logger.info(f"Calling Zyte API (Browser Rendering) for API: {search_url}")
            response = requests.post(
                "https://api.zyte.com/v1/extract",
                auth=(ZYTE_API_KEY, ""),
                json={
                    "url": search_url,
                    "browserHtml": True,
                },
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            html = data.get("browserHtml", "")

            # The browser will wrap the JSON response in HTML tags
            if "{" in html and "}" in html:
                # Extract JSON from the HTML body
                import re
                json_match = re.search(r'\{.*\}', html, re.DOTALL)
                if json_match:
                    json_data = json.loads(json_match.group())
                    results = json_data.get("data", [])
                    logger.info(f"Successfully extracted {len(results)} results from API")
                else:
                    results = []
            else:
                results = []
            
            best_match = None
            for res in results:
                res_title = res.get("title", "")
                res_id = res.get("session", "")
                
                if title.lower() in res_title.lower() or len(results) == 1:
                    best_match = {"id": res_id, "title": res_title}
                    break
            
            if best_match:
                logger.info(f"MATCH FOUND: {best_match['title']} -> {best_match['id']}")
                self.save_mapping(mal_id, "animepahe", best_match['id'], best_match['title'])
                return best_match
            else:
                logger.warning(f"No match found for {title}")
                return None

        except Exception as e:
            logger.error(f"Zyte API Error: {str(e)}")
            return None

    def save_mapping(self, mal_id, provider, provider_id, title):
        mapping = {
            "mal_id": int(mal_id),
            "provider": provider,
            "provider_id": provider_id,
            "title": title,
            "updated_at": time.time()
        }
        self.db.provider_mappings.update_one(
            {"mal_id": int(mal_id), "provider": provider},
            {"$set": mapping},
            upsert=True
        )
        logger.info(f"Saved mapping to MongoDB for MAL ID: {mal_id}")

    def get_episodes(self, provider_id, page=1):
        """Fetch the list of episodes for a given anime session ID"""
        api_url = f"https://animepahe.pw/api?m=release&id={provider_id}&sort=recent&page={page}"
        logger.info(f"Fetching episodes from: {api_url}")
        
        try:
            response = requests.post(
                "https://api.zyte.com/v1/extract",
                auth=(ZYTE_API_KEY, ""),
                json={"url": api_url, "browserHtml": True},
                timeout=60
            )
            response.raise_for_status()
            html = response.json().get("browserHtml", "")
            
            import re
            json_match = re.search(r'\{.*\}', html, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                episodes = data.get("data", [])
                logger.info(f"Retrieved {len(episodes)} episodes (Page {page})")
                return episodes
            return []
        except Exception as e:
            logger.error(f"Error fetching episodes: {str(e)}")
            return []

    def get_stream_sources(self, anime_session, episode_session):
        """Fetch the actual video stream links for an episode"""
        play_url = f"https://animepahe.pw/play/{anime_session}/{episode_session}"
        logger.info(f"Extracting stream links from: {play_url}")
        
        try:
            response = requests.post(
                "https://api.zyte.com/v1/extract",
                auth=(ZYTE_API_KEY, ""),
                json={
                    "url": play_url, 
                    "browserHtml": True
                },
                timeout=60
            )
            response.raise_for_status()
            html = response.json().get("browserHtml", "")
            
            soup = BeautifulSoup(html, 'html.parser')
            # AnimePahe stores stream info in buttons/links on the play page
            links = []
            for btn in soup.select('#resolutionMenu button'):
                quality = btn.get_text(strip=True)
                # The actual link is often in the 'data-src' or similar
                stream_url = btn.get('data-src') or btn.get('data-url')
                if stream_url:
                    links.append({"quality": quality, "url": stream_url})
            
            if not links:
                # Fallback: Scrape anything that looks like a kwik link
                import re
                kwik_links = re.findall(r'https://kwik\.cx/e/[a-zA-Z0-9]+', html)
                for i, link in enumerate(list(set(kwik_links))):
                    links.append({"quality": f"Unknown {i+1}", "url": link})

            logger.info(f"Found {len(links)} stream sources")
            return links
        except Exception as e:
            logger.error(f"Error fetching streams: {str(e)}")
            return []

    def save_streams(self, mal_id, episode_num, sources):
        """Save stream links to the database"""
        for source in sources:
            stream_data = {
                "mal_id": int(mal_id),
                "episode": int(episode_num),
                "quality": source["quality"],
                "url": source["url"],
                "provider": "animepahe",
                "updated_at": time.time()
            }
            self.db.streams.update_one(
                {"mal_id": int(mal_id), "episode": int(episode_num), "quality": source["quality"]},
                {"$set": stream_data},
                upsert=True
            )
        logger.info(f"Saved {len(sources)} streams for Episode {episode_num}")

if __name__ == "__main__":
    # Test Full Flow
    discovery = ZyteDiscovery()
    
    # 1. Search
    anime = discovery.search_anime(21, "One Piece")
    
    if anime:
        # 2. Get Episodes (Just the first page for testing)
        episodes = discovery.get_episodes(anime['id'])
        
        if episodes:
            # 3. Get Streams for the latest episode
            latest = episodes[0]
            logger.info(f"Processing Latest Episode: {latest['episode']}")
            sources = discovery.get_stream_sources(anime['id'], latest['session'])
            
            if sources:
                # 4. Save to DB
                discovery.save_streams(21, latest['episode'], sources)

