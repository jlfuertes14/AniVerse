import os
import requests
from dotenv import load_dotenv

load_dotenv()

import sys

TARGET_URL = sys.argv[1] if len(sys.argv) > 1 else "https://mkissa.to/anime"
SUCCESS_KEYWORD = sys.argv[2] if len(sys.argv) > 2 else "iframe"  # generic success keyword for video sites

def check_html(html, name):
    if not html:
        print(f"[{name}] Failed: No HTML returned.")
        return False
    if "Just a moment..." in html or "Cloudflare" in html or "cf-browser-verification" in html:
        print(f"[{name}] Failed: Cloudflare blocked the request.")
        return False
    if SUCCESS_KEYWORD.lower() in html.lower():
        print(f"[{name}] Success! Bypass worked.")
        return True
    print(f"[{name}] Unknown: HTML returned but keyword '{SUCCESS_KEYWORD}' not found.")
    return False

def test_scrape_do():
    print("Testing Scrape.do...")
    api_key = os.environ.get("SCRAPEDO_API_KEY")
    try:
        response = requests.get(
            "http://api.scrape.do", 
            params={
                "token": api_key, 
                "url": TARGET_URL, 
                "render": "true",
                "playWithBrowser": '[{"Action":"Wait","Timeout":7000}]'
            }, 
            timeout=30
        )
        check_html(response.text, "Scrape.do")
    except Exception as e:
        print(f"[Scrape.do] Error: {e}")

def test_scrapingbee():
    print("Testing ScrapingBee...")
    api_key = os.environ.get("SCRAPINGBEE_API_KEY")
    try:
        response = requests.get(
            "https://app.scrapingbee.com/api/v1/",
            params={
                "api_key": api_key,
                "url": TARGET_URL,
                "render_js": "true",
                "premium_proxy": "true",
                "stealth_proxy": "true",
                "wait": "5000"
            },
            timeout=30
        )
        check_html(response.text, "ScrapingBee")
    except Exception as e:
        print(f"[ScrapingBee] Error: {e}")

def test_scrapfly():
    print("Testing Scrapfly...")
    api_key = os.environ.get("SCRAPFLY_API_KEY")
    try:
        response = requests.get(
            "https://api.scrapfly.io/scrape",
            params={
                "key": api_key,
                "url": TARGET_URL,
                "render_js": "true",
                "asp": "true",
                "timeout": "20000"
            },
            timeout=30
        )
        data = response.json()
        html = data.get("result", {}).get("content", "")
        check_html(html, "Scrapfly")
    except Exception as e:
        print(f"[Scrapfly] Error: {e}")

def test_scrapingant():
    print("Testing ScrapingAnt...")
    api_key = os.environ.get("SCRAPINGANT_API_KEY")
    try:
        response = requests.get(
            "https://api.scrapingant.com/v2/general",
            params={
                "url": TARGET_URL,
                "x-api-key": api_key,
                "browser": "true"
            },
            timeout=30
        )
        check_html(response.text, "ScrapingAnt")
    except Exception as e:
        print(f"[ScrapingAnt] Error: {e}")

def test_webscraping_ai():
    print("Testing WebScraping.AI...")
    api_key = os.environ.get("WEBSCRAPING_AI_KEY")
    try:
        response = requests.get(
            "https://api.webscraping.ai/html",
            params={
                "api_key": api_key,
                "url": TARGET_URL,
                "js": "true"
            },
            timeout=30
        )
        check_html(response.text, "WebScraping.AI")
    except Exception as e:
        print(f"[WebScraping.AI] Error: {e}")

def test_zenscrape():
    print("Testing Zenscrape...")
    api_key = os.environ.get("ZENSCRAPE_API_KEY")
    try:
        response = requests.get(
            "https://app.zenscrape.com/api/v1/get",
            params={
                "apikey": api_key,
                "url": TARGET_URL,
                "render": "true",
                "premium": "true",
                "location": "na"
            },
            headers={"apikey": api_key},
            timeout=30
        )
        check_html(response.text, "Zenscrape")
    except Exception as e:
        print(f"[Zenscrape] Error: {e}")

def test_browserless():
    print("Testing Browserless.io (Playwright)...")
    api_key = os.environ.get("BROWSERLESS_API_KEY")
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ws_endpoint = f"wss://chrome.browserless.io/?token={api_key}"
            browser = p.chromium.connect_over_cdp(ws_endpoint)
            context = browser.new_context()
            page = context.new_page()
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
            html = page.content()
            check_html(html, "Browserless.io")
            browser.close()
    except Exception as e:
        print(f"[Browserless.io] Error: {e}")

if __name__ == "__main__":
    test_scrape_do()
    test_scrapingbee()
    test_scrapfly()
    test_scrapingant()
    test_webscraping_ai()
    test_zenscrape()
    test_browserless()
