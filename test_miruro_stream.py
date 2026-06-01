import os
import requests
import json
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

def extract_video_info(api_name, html_text):
    text = html_text.lower()
    if "m3u8" in text or "mp4" in text or "vidstack" in text or "<video" in text:
        print(f"[{api_name}] Success! Found potential video/stream indicators on the page.")
        
        soup = BeautifulSoup(html_text, 'html.parser')
        video_tags = soup.find_all('video')
        for v in video_tags:
            print(f"  -> Found <video> tag. src: {v.get('src')}")
            for source in v.find_all('source'):
                print(f"  -> Found <source> inside video. src: {source.get('src')}")
        
        iframes = soup.find_all('iframe')
        for iframe in iframes:
            src = iframe.get('src', '')
            if src and ('youtube' not in src and 'google' not in src):
                print(f"  -> Found potential player iframe: {src}")
                
    elif "miruro" in text:
        print(f"[{api_name}] Page loaded, but no video/stream found.")
    else:
        print(f"[{api_name}] Failed to load Miruro.")


def test_all_apis_miruro():
    scrape_do_key = os.environ.get("SCRAPEDO_API_KEY")
    scrapingant_key = os.environ.get("SCRAPINGANT_API_KEY")
    webscraping_ai_key = os.environ.get("WEBSCRAPING_AI_API_KEY")
    browserless_token = os.environ.get("BROWSERLESS_API_KEY")
    zenscrape_key = os.environ.get("ZENSCRAPE_API_KEY")
    scrapingbee_key = os.environ.get("SCRAPINGBEE_API_KEY")
    scrapfly_key = os.environ.get("SCRAPFLY_API_KEY")

    watch_url = "https://www.miruro.to/watch?id=21&ep=1"
    print(f"Testing Miruro stream extraction for: {watch_url}\n")
    
    # 1. Scrape.do
    print("--- 1. Testing Scrape.do ---")
    try:
        r = requests.get(
            "http://api.scrape.do", 
            params={"token": scrape_do_key, "url": watch_url, "render": "true", "playWithBrowser": '[{"Action":"Wait","Timeout":10000}]'}, 
            timeout=40
        )
        extract_video_info("Scrape.do", r.text)
    except Exception as e: print(f"Error: {e}")

    # 2. ScrapingAnt
    print("\n--- 2. Testing ScrapingAnt ---")
    try:
        r = requests.get(
            "https://api.scrapingant.com/v2/general",
            params={"url": watch_url, "x-api-key": scrapingant_key, "browser": "true", "wait_for_selector": "video, iframe"},
            timeout=40
        )
        extract_video_info("ScrapingAnt", r.text)
    except Exception as e: print(f"Error: {e}")

    # 3. WebScraping.AI
    print("\n--- 3. Testing WebScraping.AI ---")
    try:
        r = requests.get(
            "https://api.webscraping.ai/html",
            params={"api_key": webscraping_ai_key, "url": watch_url, "js": "true", "js_timeout": 10000},
            timeout=40
        )
        extract_video_info("WebScraping.AI", r.text)
    except Exception as e: print(f"Error: {e}")

    # 4. Browserless.io
    print("\n--- 4. Testing Browserless.io ---")
    try:
        payload = {"url": watch_url, "gotoOptions": {"waitUntil": "networkidle2"}, "waitFor": 10000}
        r = requests.post(
            f"https://production-sfo.browserless.io/content?token={browserless_token}",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=40
        )
        extract_video_info("Browserless.io", r.text)
    except Exception as e: print(f"Error: {e}")

    # 5. Zenscrape
    print("\n--- 5. Testing Zenscrape ---")
    try:
        r = requests.get(
            "https://app.zenscrape.com/api/v1/get",
            headers={"apikey": zenscrape_key},
            params={"url": watch_url, "render": "true", "premium": "true"},
            timeout=40
        )
        extract_video_info("Zenscrape", r.text)
    except Exception as e: print(f"Error: {e}")

    # 6. ScrapingBee
    print("\n--- 6. Testing ScrapingBee ---")
    try:
        r = requests.get(
            "https://app.scrapingbee.com/api/v1/",
            params={"api_key": scrapingbee_key, "url": watch_url, "render_js": "true", "wait_browser": "networkidle2"},
            timeout=40
        )
        extract_video_info("ScrapingBee", r.text)
    except Exception as e: print(f"Error: {e}")

    # 7. Scrapfly
    print("\n--- 7. Testing Scrapfly ---")
    try:
        r = requests.get(
            "https://api.scrapfly.io/scrape",
            params={"key": scrapfly_key, "url": watch_url, "render_js": "true", "asp": "true"},
            timeout=40
        )
        if r.status_code == 200:
            res_json = r.json()
            extract_video_info("Scrapfly", res_json.get("result", {}).get("content", ""))
        else:
            print(f"[Scrapfly] Error status: {r.status_code}")
    except Exception as e: print(f"Error: {e}")


if __name__ == "__main__":
    test_all_apis_miruro()
