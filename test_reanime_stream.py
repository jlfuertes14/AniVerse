import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

def test_reanime_stream():
    scrape_do_key = os.environ.get("SCRAPEDO_API_KEY")
    scrapingbee_key = os.environ.get("SCRAPINGBEE_API_KEY")
    webscraping_ai_key = os.environ.get("WEBSCRAPING_AI_KEY")
    
    watch_url = "https://reanime.to/watch/bleach?ep=1"
    print(f"Testing Re:Anime stream extraction for: {watch_url}\n")
    
    # 1. Test Scrape.do
    print(f"--- Testing Scrape.do ---")
    try:
        r = requests.get(
            "http://api.scrape.do", 
            params={
                "token": scrape_do_key, 
                "url": watch_url, 
                "render": "true",
                "playWithBrowser": '[{"Action":"Wait","Timeout":15000}]'
            }, 
            timeout=60
        )
        if "flixcloud" in r.text or "video-player" in r.text:
            soup = BeautifulSoup(r.text, 'html.parser')
            iframe = soup.select_one("iframe#video-player, iframe[src*='flixcloud']")
            if iframe and iframe.get("src"):
                print(f"[Scrape.do] Success! Found iframe src: {iframe.get('src')}")
            else:
                print("[Scrape.do] Page loaded, but video iframe source was empty.")
        elif "Just a moment..." in r.text:
            print("[Scrape.do] Blocked by Cloudflare.")
        else:
            print("[Scrape.do] Unknown or empty response.")
    except Exception as e:
        print(f"[Scrape.do] Error: {e}")

    # 2. Test ScrapingBee
    print(f"\n--- Testing ScrapingBee ---")
    try:
        r = requests.get(
            "https://app.scrapingbee.com/api/v1/",
            params={
                "api_key": scrapingbee_key,
                "url": watch_url,
                "render_js": "true",
                "premium_proxy": "true",
                "stealth_proxy": "true",
                "wait": "15000",
                "wait_browser": "networkidle2"
            },
            timeout=60
        )
        if "flixcloud" in r.text or "video-player" in r.text:
            soup = BeautifulSoup(r.text, 'html.parser')
            iframe = soup.select_one("iframe#video-player, iframe[src*='flixcloud']")
            if iframe and iframe.get("src"):
                print(f"[ScrapingBee] Success! Found iframe src: {iframe.get('src')}")
            else:
                print("[ScrapingBee] Page loaded, but video iframe source was empty.")
        elif "Just a moment..." in r.text:
            print("[ScrapingBee] Blocked by Cloudflare.")
        else:
            print("[ScrapingBee] Unknown or empty response.")
    except Exception as e:
        print(f"[ScrapingBee] Error: {e}")

    # 3. Test WebScraping.AI (with advanced JS snippet like in your backend)
    print(f"\n--- Testing WebScraping.AI (with JS snippet) ---")
    try:
        js_wait_snippet = """
            await new Promise((resolve) => {
                let elapsed = 0;
                const interval = setInterval(() => {
                    const ifr = document.querySelector('iframe#video-player') || document.querySelector('iframe[src*="flixcloud"]');
                    if (ifr && ifr.src && ifr.src.includes('flixcloud')) {
                        clearInterval(interval);
                        resolve();
                    }
                    elapsed += 500;
                    if (elapsed >= 15000) {
                        clearInterval(interval);
                        resolve();
                    }
                }, 500);
            });
        """
        r = requests.get(
            "https://api.webscraping.ai/html",
            params={
                "api_key": webscraping_ai_key,
                "url": watch_url,
                "proxy": "residential",
                "js": "true",
                "js_snippet": js_wait_snippet,
                "timeout": "40000"
            },
            timeout=60
        )
        if "flixcloud" in r.text or "video-player" in r.text:
            soup = BeautifulSoup(r.text, 'html.parser')
            iframe = soup.select_one("iframe#video-player, iframe[src*='flixcloud']")
            if iframe and iframe.get("src"):
                print(f"[WebScraping.AI] Success! Found iframe src: {iframe.get('src')}")
            else:
                print("[WebScraping.AI] Page loaded, but video iframe source was empty.")
        elif "Just a moment..." in r.text:
            print("[WebScraping.AI] Blocked by Cloudflare.")
        else:
            print("[WebScraping.AI] Unknown or empty response.")
    except Exception as e:
        print(f"[WebScraping.AI] Error: {e}")

if __name__ == "__main__":
    test_reanime_stream()
