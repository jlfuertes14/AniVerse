import os
import requests
import json
from dotenv import load_dotenv
from bs4 import BeautifulSoup

load_dotenv()

def test_stream_extraction():
    scrape_do_key = os.environ.get("SCRAPEDO_API_KEY")
    scrapingbee_key = os.environ.get("SCRAPINGBEE_API_KEY")
    
    # 1. Get session ID for Bleach (Using direct request since search is easy)
    search_url = "https://animepahe.pw/api?m=search&q=bleach"
    print(f"Fetching search API: {search_url}")
    res = requests.get(
        "https://app.scrapingbee.com/api/v1/",
        params={
            "api_key": scrapingbee_key,
            "url": search_url,
            "render_js": "true",
            "premium_proxy": "true",
            "stealth_proxy": "true",
            "wait": "5000"
        },
        timeout=60
    )
    data = res.json()
    session_id = data["data"][0]["session"]
    print(f"Found Session ID: {session_id}")
    
    # 2. Get episode_session ID (Using direct request)
    release_url = f"https://animepahe.pw/api?m=release&id={session_id}&sort=episode_asc&page=1"
    print(f"Fetching release API: {release_url}")
    res = requests.get(
        "https://app.scrapingbee.com/api/v1/",
        params={
            "api_key": scrapingbee_key,
            "url": release_url,
            "render_js": "true",
            "premium_proxy": "true",
            "stealth_proxy": "true",
            "wait": "5000"
        },
        timeout=60
    )
    ep_data = res.json()
    episode_session = ep_data["data"][0]["session"]
    print(f"Found Episode Session ID: {episode_session}")
    
    # 3. Test Scrape.do on the play page
    play_url = f"https://animepahe.pw/play/{session_id}/{episode_session}"
    print(f"\n--- Testing Scrape.do on Play Page ---")
    print(f"URL: {play_url}")
    try:
        r = requests.get(
            "http://api.scrape.do", 
            params={
                "token": scrape_do_key, 
                "url": play_url, 
                "render": "true",
                "playWithBrowser": '[{"Action":"Wait","Timeout":7000}]'
            }, 
            timeout=40
        )
        if "kwik" in r.text or "player" in r.text.lower():
            soup = BeautifulSoup(r.text, 'html.parser')
            embed = soup.select_one("div#resolutionMenu button")
            if embed:
                print("[Scrape.do] Success! Found Kwik stream button/data.")
            else:
                print("[Scrape.do] Loaded page but could not find the stream data.")
        elif "Just a moment..." in r.text:
            print("[Scrape.do] Blocked by Cloudflare on the play page.")
        else:
            print("[Scrape.do] Unknown response.")
    except Exception as e:
        print(f"[Scrape.do] Error: {e}")
        
    # 4. Test ScrapingBee on the play page
    print(f"\n--- Testing ScrapingBee on Play Page ---")
    try:
        r = requests.get(
            "https://app.scrapingbee.com/api/v1/",
            params={
                "api_key": scrapingbee_key,
                "url": play_url,
                "render_js": "true",
                "premium_proxy": "true",
                "stealth_proxy": "true",
                "wait": "7000"
            },
            timeout=40
        )
        if "kwik" in r.text or "player" in r.text.lower():
            soup = BeautifulSoup(r.text, 'html.parser')
            embed = soup.select_one("div#resolutionMenu button")
            if embed:
                print("[ScrapingBee] Success! Found Kwik stream button/data.")
            else:
                print("[ScrapingBee] Loaded page but could not find the stream data.")
        elif "Just a moment..." in r.text:
            print("[ScrapingBee] Blocked by Cloudflare on the play page.")
        else:
            print("[ScrapingBee] Unknown response.")
    except Exception as e:
        print(f"[ScrapingBee] Error: {e}")

if __name__ == "__main__":
    test_stream_extraction()
