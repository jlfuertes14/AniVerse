"""
Scraper Runner -- Subprocess entry point for Playwright-based scraping.

This script is called by the backend services via subprocess.run().
It runs with its own asyncio event loop (ProactorEventLoop on Windows),
completely isolated from Uvicorn's SelectorEventLoop.

Usage:
    python scraper_runner.py <action> <json_params>

Actions:
    animepahe_full   {"title": "...", "max_episodes": 0}
    animepahe_stream {"session": "...", "episode_session": "..."}
    reanime_search   {"title": "...", "anilist_id": 123}
    reanime_scrape_episode {"slug": "...", "episode_number": 1}

Output:
    Prints JSON result to stdout (last line).
    All logs go to stderr so they don't interfere with JSON parsing.
"""

import asyncio
import json
import sys
import os
from dotenv import load_dotenv
load_dotenv() # Load .env variables
import re
from urllib.parse import quote_plus
from playwright.async_api import async_playwright

# Ensure Playwright uses a project-local browser cache on Render/CI if available
_playwright_cache = os.path.join(os.path.dirname(__file__), ".playwright")
if os.path.exists(_playwright_cache):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", _playwright_cache)

# Signal to scraper.py that we're running as a subprocess
# This makes scraper.py redirect print() to stderr
os.environ["SCRAPER_SUBPROCESS"] = "1"

# Fix for Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

PLAYWRIGHT_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-setuid-sandbox",
]


# ── MongoDB Connectivity (Cache Layer) ─────────────────────────
import pymongo
from pymongo import MongoClient

MONGODB_URI = os.environ.get("MONGODB_URI")
MONGODB_DB = os.environ.get("MONGODB_DB", "aniverse")

def get_db():
    if not MONGODB_URI:
        return None
    try:
        # Use a short timeout for the cache check
        client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=2000)
        return client[MONGODB_DB]
    except Exception as e:
        log(f"[DB] Connection Error: {e}")
        return None

db = get_db()


def log(msg: str):
    """Log to stderr so stdout stays clean for JSON output."""
    print(msg, file=sys.stderr)


# ── API Scraper Integrations (Rotational Fallback) ──────────────────────────
ZYTE_API_KEY = os.environ.get("ZYTE_API_KEY")
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")
SCRAPINGANT_API_KEY = os.environ.get("SCRAPINGANT_API_KEY")
WEBSCRAPING_AI_KEY = os.environ.get("WEBSCRAPING_AI_KEY")

class APILimitReached(Exception):
    pass

def _extract_json_from_html(html, use_browser):
    if use_browser and ("{" in html and "}" in html):
        import json, re
        match = re.search(r'\{.*\}', html, re.DOTALL)
        if match:
            try:
                json.loads(match.group())
                return match.group()
            except Exception:
                pass
    return html

def _is_cloudflare_blocked(html) -> bool:
    if not isinstance(html, str):
        return False
    # Check for common Cloudflare / DDoS-Guard challenge indicators
    html_lower = html.lower()
    return "just a moment..." in html_lower or "cf-browser-verification" in html_lower or "ddos-guard" in html_lower

def _try_scraper_api(url, use_browser=True, sapi_instructions=None, wait_for_selector=None):
    if not SCRAPER_API_KEY: return None
    import requests
    log(f"[ScraperAPI] Fetching: {url}")
    params = {"api_key": SCRAPER_API_KEY, "url": url, "premium": "true"}
    if use_browser: params["render"] = "true"
    if wait_for_selector: params["wait_for_selector"] = wait_for_selector
    
    headers = {}
    if sapi_instructions:
        import json
        headers["x-sapi-render-js-instructions"] = json.dumps(sapi_instructions)
        
    try:
        response = requests.get("http://api.scraperapi.com", params=params, headers=headers, timeout=60)
        if response.status_code in [401, 402, 403, 429]:
            log(f"[ScraperAPI] Limit/Auth Error ({response.status_code}). Exhausted.")
            raise APILimitReached("ScraperAPI Exhausted")
        response.raise_for_status()
        html = response.text
        if _is_cloudflare_blocked(html):
            log("[ScraperAPI] Cloudflare/DDoS-Guard block detected. Treating as failure.")
            return None
        return _extract_json_from_html(html, use_browser)
    except APILimitReached:
        raise
    except Exception as e:
        log(f"[ScraperAPI] Error: {e}")
        return None

def _try_scrapingant_api(url, use_browser=True, wait_for_selector=None):
    if not SCRAPINGANT_API_KEY: return None
    import requests
    log(f"[ScrapingAnt] Fetching: {url}")
    params = {
        "url": url, 
        "browser": "true" if use_browser else "false",
        "proxy_type": "residential",
        "x-api-key": SCRAPINGANT_API_KEY
    }
    if wait_for_selector: params["wait_for_selector"] = wait_for_selector
    
    try:
        response = requests.get("https://api.scrapingant.com/v2/general", params=params, timeout=60)
        if response.status_code in [401, 402, 403, 429]:
            log(f"[ScrapingAnt] Limit/Auth Error ({response.status_code}). Exhausted.")
            raise APILimitReached("ScrapingAnt Exhausted")
        response.raise_for_status()
        html = response.text
        if _is_cloudflare_blocked(html):
            log("[ScrapingAnt] Cloudflare/DDoS-Guard block detected. Treating as failure.")
            return None
        return _extract_json_from_html(html, use_browser)
    except APILimitReached:
        raise
    except Exception as e:
        log(f"[ScrapingAnt] Error: {e}")
        return None

def _try_webscraping_ai(url, use_browser=True, js_snippet=None, timeout_ms=None):
    if not WEBSCRAPING_AI_KEY: return None
    import requests
    log(f"[WebScraping.AI] Fetching: {url}")
    params = {"api_key": WEBSCRAPING_AI_KEY, "url": url, "proxy": "residential"}
    if use_browser: params["js"] = "true"
    if js_snippet: params["js_snippet"] = js_snippet
    if timeout_ms: params["timeout"] = str(timeout_ms)
    
    try:
        response = requests.get("https://api.webscraping.ai/html", params=params, timeout=90)
        if response.status_code in [401, 402, 403, 429]:
            log(f"[WebScraping.AI] Limit/Auth Error ({response.status_code}). Exhausted.")
            raise APILimitReached("WebScraping.AI Exhausted")
        response.raise_for_status()
        html = response.text
        if _is_cloudflare_blocked(html):
            log("[WebScraping.AI] Cloudflare/DDoS-Guard block detected. Treating as failure.")
            return None
        return _extract_json_from_html(html, use_browser)
    except APILimitReached:
        raise
    except Exception as e:
        log(f"[WebScraping.AI] Error: {e}")
        return None

def _try_zyte_api(url, use_browser=True, zyte_actions=None):
    if not ZYTE_API_KEY: return None
    import requests
    log(f"[Zyte API] Fetching: {url}")
    payload = {"url": url, "browserHtml": use_browser}
    if zyte_actions: payload["actions"] = zyte_actions
        
    try:
        response = requests.post("https://api.zyte.com/v1/extract", auth=(ZYTE_API_KEY, ""), json=payload, timeout=60)
        if response.status_code in [401, 402, 403, 429]:
            log(f"[Zyte API] Limit/Auth Error ({response.status_code}). Exhausted.")
            raise APILimitReached("Zyte API Exhausted")
        data = response.json()
        if use_browser:
            html = data.get("browserHtml", "")
            if _is_cloudflare_blocked(html):
                log("[Zyte API] Cloudflare/DDoS-Guard block detected. Treating as failure.")
                return None
            return _extract_json_from_html(html, use_browser)
    except APILimitReached:
        raise
    except Exception as e:
        log(f"[Zyte API] Error: {e}")
        return None

def _fetch_with_api_fallback(url, use_browser=True, zyte_actions=None, sapi_instructions=None, wait_for_selector=None):
    """
    Rotational API fetcher.
    Priority: All other APIs -> None (Local Playwright)
    """
    html = None
    is_animepahe = "animepahe" in url or "kwik" in url
    
    if is_animepahe:
        log("[API Status] AnimePahe/Kwik URL detected.")
        
    # 1. ScrapingAnt
    try:
        html = _try_scrapingant_api(url, use_browser, wait_for_selector)
        if html:
            log("[API Status] Successfully fetched via ScrapingAnt")
            return html
    except APILimitReached: pass
        
    # 2. WebScraping.AI
    try:
        html = _try_webscraping_ai(url, use_browser)
        if html:
            log("[API Status] Successfully fetched via WebScraping.AI")
            return html
    except APILimitReached: pass

    # 3. ScrapingBee
    try:
        html = _try_scrapingbee(url, use_browser, wait_for_selector)
        if html:
            log("[API Status] Successfully fetched via ScrapingBee")
            return html
    except APILimitReached: pass
    
    # 4. Zenscrape
    try:
        html = _try_zenscrape(url, use_browser, wait_for_selector)
        if html:
            log("[API Status] Successfully fetched via Zenscrape")
            return html
    except APILimitReached: pass
    
    # 5. Scrape.do
    try:
        html = _try_scrapedo(url, use_browser, wait_for_selector)
        if html:
            log("[API Status] Successfully fetched via Scrape.do")
            return html
    except APILimitReached: pass

    # 6. Scrapfly
    try:
        html = _try_scrapfly(url, use_browser, wait_for_selector)
        if html:
            log("[API Status] Successfully fetched via Scrapfly")
            return html
    except APILimitReached: pass
        
    log("[API Status] All APIs exhausted or failed. Falling back to local Playwright...")
    return None


def _normalize_title(value: str | None) -> str:
    if not value:
        return ""
    normalized = value.lower()
    normalized = normalized.replace("&", " and ")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    normalized = re.sub(r"\b(season|part|cour|tv)\b", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _title_similarity_score(source_title: str, candidate_title: str) -> float:
    source = _normalize_title(source_title)
    candidate = _normalize_title(candidate_title)
    if not source or not candidate:
        return 0.0
    if source == candidate:
        return 1.0
    if source in candidate or candidate in source:
        shorter = min(len(source), len(candidate))
        longer = max(len(source), len(candidate))
        return shorter / longer

    source_tokens = set(source.split())
    candidate_tokens = set(candidate.split())
    if not source_tokens or not candidate_tokens:
        return 0.0
    overlap = len(source_tokens & candidate_tokens)
    union = len(source_tokens | candidate_tokens)
    return overlap / union if union else 0.0




# ── Re:ANIME actions ──────────────────────────────────────────

async def reanime_search(title: str, target_anilist_id: int = None) -> dict | None:
    """Search Re:ANIME for an anime title and optionally verify AniList ID."""
    from bs4 import BeautifulSoup
    import re

    log(f"[Re:ANIME] Searching for: {title} (Target AniList: {target_anilist_id})")

    # 0. Check Cache (MongoDB)
    if db is not None:
        query = {"provider": "reanime"}
        if target_anilist_id: query["mal_id"] = target_anilist_id
        else: query["title"] = title
        
        cached = db.provider_mappings.find_one(query)
        if cached and cached.get("slug"):
            log(f"[Re:ANIME][Cache] Hit: {cached.get('title')} (slug: {cached.get('slug')})")
            return {"slug": cached["slug"], "anilist_id": cached.get("mal_id")}

    # 1. Try Rotational API Fallback (Turbo)
    # Using direct search URL so APIs don't need to simulate typing
    search_url = f"https://reanime.to/search?q={quote_plus(title)}"
    html = _fetch_with_api_fallback(
        search_url, 
        use_browser=True, 
        wait_for_selector="a[href*='/anime/']"
    )
    
    if html:
        log(f"[Re:ANIME][Zyte] Parsing search results...")
        soup = BeautifulSoup(html, 'html.parser')
        cards = soup.select("a[href*='/anime/']")
        for card in cards:
            href = card.get("href")
            if not href or "/anime/" not in href: continue
            
            res_title = card.select_one("h3")
            res_title = res_title.get_text(strip=True) if res_title else ""
            img = card.select_one("img")
            img_src = img.get("src") if img else ""
            
            found_anilist_id = None
            if img_src:
                id_match = re.search(r'/bx(\d+)-', img_src)
                if id_match: found_anilist_id = int(id_match.group(1))
            
            if target_anilist_id and found_anilist_id == target_anilist_id:
                slug = href.split("/")[-1]
                log(f"[Re:ANIME][Zyte] ID Match: {slug}")
                return {"slug": slug, "anilist_id": found_anilist_id}
            
            similarity = _title_similarity_score(title, res_title)
            if title.lower() in res_title.lower() or similarity >= 0.72:
                slug = href.split("/")[-1]
                log(f"[Re:ANIME][Zyte] Title Match: {slug}")
                return {"slug": slug, "anilist_id": found_anilist_id}

    # 2. Fallback to Local Playwright (Free)
    log(f"[Re:ANIME][Local] Falling back to local Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=PLAYWRIGHT_LAUNCH_ARGS)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        try:
            search_url = f"https://reanime.to/search?q={quote_plus(title)}"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30000)

            # Wait for results
            await page.wait_for_timeout(3000)
            result_selector = "a[href*='/anime/']"
            try:
                await page.wait_for_selector(result_selector, timeout=10000)
            except:
                log(f"[Re:ANIME] No results found for {title}")
                return None

            # Get all result cards
            cards = await page.locator("a[href*='/anime/']").all()
            
            for card in cards:
                href = await card.get_attribute("href")
                if not href or "/anime/" not in href:
                    continue
                
                # Get title and image
                res_title = await card.locator("h3").inner_text()
                res_title = res_title.strip() if res_title else ""
                res_title_lower = res_title.lower()
                
                img_src = await card.locator("img").get_attribute("src")
                
                found_anilist_id = None
                if img_src:
                    match = re.search(r'/bx(\d+)-', img_src)
                    if match:
                        found_anilist_id = int(match.group(1))
                
                # If we have a target ID, check it
                if target_anilist_id and found_anilist_id == target_anilist_id:
                    slug = href.split("/")[-1]
                    log(f"[Re:ANIME] ID Match found: {slug} (AniList: {found_anilist_id})")
                    return {"slug": slug, "anilist_id": found_anilist_id}
                
                # If no target ID or no image match, fallback to flexible title matching
                similarity = _title_similarity_score(title, res_title)
                if title.lower() in res_title_lower or res_title_lower in title.lower() or similarity >= 0.72:
                    slug = href.split("/")[-1]
                    log(f"[Re:ANIME] Title match found: {slug} (score: {similarity:.2f})")
                    return {"slug": slug, "anilist_id": found_anilist_id}

            log(f"[Re:ANIME] No direct match found for '{title}' in {len(cards)} results")

        except Exception as e:
            log(f"[Re:ANIME] Search error: {e}")
        finally:
            await browser.close()
    return None

async def reanime_scrape_episode(slug: str, episode_number: int) -> dict | None:
    """Extract kwik streaming URL for a Re:ANIME episode."""
    from bs4 import BeautifulSoup
    watch_url = f"https://reanime.to/watch/{slug}?ep={episode_number}"
    log(f"[Re:ANIME] Starting scrape for Ep {episode_number}: {watch_url}")

    # 0. Check Cache (MongoDB)
    if db is not None:
        cached = db.streams.find_one({"referer_url": watch_url, "provider": "reanime"})
        if cached and cached.get("embed_url"):
            log(f"[Re:ANIME][Cache] Hit for Ep {episode_number}")
            return {
                "embed_url": cached["embed_url"],
                "provider": "reanime",
                "referer_url": watch_url,
                "available_episodes": cached.get("available_episodes", episode_number)
            }

    # Helper to count episodes from parsed HTML
    def _count_episodes_from_soup(soup):
        ep_elements = soup.select("a[data-episode]")
        if ep_elements:
            try:
                ep_nums = [int(el.get("data-episode")) for el in ep_elements if el.get("data-episode", "").isdigit()]
                if ep_nums: return max(ep_nums)
            except: pass
        return 1

    # 1. Try WebScraping.AI with JS snippet (most reliable for ReAnime)
    # This executes JavaScript ON the proxy server to wait for the iframe
    # to be dynamically injected by ReAnime's player loader.
    if WEBSCRAPING_AI_KEY:
        log(f"[Re:ANIME][WebScraping.AI+JS] Trying JS snippet extraction...")
        js_wait_snippet = """
            // Wait up to 40s for the video player iframe to get a valid src
            await new Promise((resolve) => {
                let elapsed = 0;
                const interval = setInterval(() => {
                    const ifr = document.querySelector('iframe#video-player') || document.querySelector('iframe[src*="flixcloud"]');
                    if (ifr && ifr.src && ifr.src.includes('flixcloud')) {
                        clearInterval(interval);
                        resolve();
                    }
                    elapsed += 500;
                    if (elapsed >= 40000) {
                        clearInterval(interval);
                        resolve();
                    }
                }, 500);
            });
        """
        try:
            html = _try_webscraping_ai(watch_url, use_browser=True, js_snippet=js_wait_snippet, timeout_ms=60000)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                iframe = soup.select_one("iframe#video-player, iframe[src*='flixcloud']")
                embed_url = iframe.get("src") if iframe else None
                
                if embed_url and "flixcloud" in embed_url:
                    log(f"[Re:ANIME][WebScraping.AI+JS] Found FlixCloud embed: {embed_url}")
                    return {
                        "embed_url": embed_url,
                        "stream_url": None,
                        "provider": "reanime",
                        "referer_url": watch_url,
                        "available_episodes": _count_episodes_from_soup(soup)
                    }
                else:
                    log(f"[Re:ANIME][WebScraping.AI+JS] HTML returned but no flixcloud iframe found")
        except Exception as e:
            log(f"[Re:ANIME][WebScraping.AI+JS] Error: {e}")

    # 2. Try standard rotational API fallback (ScraperAPI/ScrapingAnt/Zyte with wait_for_selector)
    html = _fetch_with_api_fallback(
        watch_url, 
        use_browser=True, 
        zyte_actions=[{"action": "waitForSelector", "selector": {"type": "css", "value": "iframe#video-player"}, "timeout": 15}],
        wait_for_selector="iframe#video-player"
    )
    
    if html:
        soup = BeautifulSoup(html, 'html.parser')
        iframe = soup.select_one("iframe#video-player, iframe[src*='flixcloud']")
        embed_url = iframe.get("src") if iframe else None
        
        if embed_url and "flixcloud" in embed_url:
            log(f"[Re:ANIME][API] Found FlixCloud embed: {embed_url}")
            return {
                "embed_url": embed_url,
                "stream_url": None,
                "provider": "reanime",
                "referer_url": watch_url,
                "available_episodes": _count_episodes_from_soup(soup)
            }

    # 3. Fallback to Local Playwright with extended timeout + retry
    log(f"[Re:ANIME][Local] Using local Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=PLAYWRIGHT_LAUNCH_ARGS)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            iframe_js_check = """() => {
                const ifr = document.querySelector('iframe#video-player') || document.querySelector('iframe[src*="flixcloud"]');
                return ifr && ifr.src && ifr.src !== '' && ifr.src.includes('flixcloud');
            }"""

            for attempt in range(1, 3):  # Up to 2 attempts
                log(f"[Re:ANIME][Local] Attempt {attempt}/2...")
                await page.goto(watch_url, wait_until="load", timeout=60000)
                
                log(f"[Re:ANIME] Waiting for player to be injected and synced...")
                try:
                    await page.wait_for_function(iframe_js_check, timeout=45000)
                    
                    iframe = await page.query_selector("iframe#video-player, iframe[src*='flixcloud']")
                    embed_url = await iframe.get_attribute("src") if iframe else None
                    
                    if embed_url and "flixcloud" in embed_url:
                        log(f"[Re:ANIME] Found FlixCloud embed: {embed_url}")
                        
                        available_episodes = 1
                        try:
                            ep_elements = await page.query_selector_all("a[data-episode]")
                            if ep_elements:
                                ep_nums = []
                                for el in ep_elements:
                                    ep_str = await el.get_attribute("data-episode")
                                    if ep_str and ep_str.isdigit():
                                        ep_nums.append(int(ep_str))
                                if ep_nums:
                                    available_episodes = max(ep_nums)
                                    log(f"[Re:ANIME] Detected {available_episodes} available episodes")
                        except Exception as ee:
                            log(f"[Re:ANIME] Failed to count episodes: {ee}")

                        return {
                            "embed_url": embed_url,
                            "stream_url": None,
                            "provider": "reanime",
                            "referer_url": watch_url,
                            "available_episodes": available_episodes
                        }
                    else:
                        log(f"[Re:ANIME] Iframe found but src is empty or invalid")
                except Exception as e:
                    log(f"[Re:ANIME] Player src timeout (attempt {attempt}): {e}")
                    if await page.query_selector("div:has-text('Syncing')"):
                        log(f"[Re:ANIME] Page stuck on 'Syncing' — will retry with reload")
                    elif await page.query_selector("div:has-text('Loading')"):
                        log(f"[Re:ANIME] Page stuck on 'Loading' — will retry with reload")
                    else:
                        break  # Unknown state, don't retry
                
        except Exception as e:
            log(f"[Re:ANIME] Scrape error for {watch_url}: {e}")
        finally:
            await browser.close()

    return None


ANIMEPAHE_BASE = "https://animepahe.pw"


def _parse_episode_number(value) -> int | None:
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _select_animepahe_episode(episodes: list, requested_episode: int):
    normalized = []
    for ep in episodes:
        ep_num = _parse_episode_number(ep.get("episode"))
        if ep_num is not None:
            normalized.append((ep_num, ep))

    for ep_num, ep in normalized:
        if ep_num == requested_episode:
            return ep, "exact"

    if not normalized:
        return None, "empty"

    normalized.sort(key=lambda item: item[0])
    min_available = normalized[0][0]
    if min_available > requested_episode and 1 <= requested_episode <= len(normalized):
        return normalized[requested_episode - 1][1], "relative"

    return None, "missing"


def _animepahe_warmup(page):
    """Navigate to home page and wait for DDoS-Guard/Cloudflare to clear."""
    try:
        log("[AnimePahe] Warming up to clear DDoS-Guard...")
        page.goto(ANIMEPAHE_BASE, wait_until="load", timeout=60000)
        
        # Wait for "Checking your browser" to disappear
        for _ in range(15): # Up to 15 seconds
            title = page.title()
            if "Checking your browser" not in title and "Just a moment" not in title:
                break
            page.wait_for_timeout(1000)
        
        # Ensure we are on a real page by waiting for a common element
        try:
            page.wait_for_selector(".navbar, .logo, .content-wrapper", timeout=10000)
            log("[AnimePahe] Warmup successful.")
        except Exception:
            log("[AnimePahe] Warmup timed out waiting for navbar, but proceeding anyway.")
            
    except Exception as e:
        log(f"[AnimePahe] Warmup error: {e}")

    page.wait_for_timeout(5000)


def _animepahe_json_request(page, url: str, label: str):
    """Fetch a JSON page with a retry-friendly timeout profile."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    last_error = None
    for attempt in range(3):
        try:
            response = page.goto(url, wait_until="commit", timeout=45000)
            page.wait_for_timeout(2000)
            body_text = page.locator("body").inner_text().strip()
            if not body_text:
                raise json.JSONDecodeError("Empty response body", body_text, 0)
            return json.loads(body_text)
        except PlaywrightTimeoutError as exc:
            last_error = exc
            log(f"[AnimePahe] Timeout fetching {label} (attempt {attempt + 1}/3)")
            _animepahe_warmup(page)
            page.wait_for_timeout(4000)
        except json.JSONDecodeError as exc:
            last_error = exc
            preview = page.locator("body").inner_text().strip()[:160]
            log(f"[AnimePahe] Non-JSON response fetching {label} (attempt {attempt + 1}/3): {preview!r}")
            _animepahe_warmup(page)
            page.wait_for_timeout(4000)

    raise last_error


def scrape_animepahe_episode_sync(title: str, episode_number: int, session_id: str | None = None, offset: int = 0):
    """Resolve one AnimePahe episode using sync Playwright to avoid Windows async spawn issues."""
    from playwright.sync_api import sync_playwright

    result = {
        "title": title,
        "provider": "animepahe",
        "session": session_id,
        "episode": None,
        "episodes": [],
        "available_episodes": 0,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=PLAYWRIGHT_LAUNCH_ARGS)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            _animepahe_warmup(page)

            if not session_id:
                api_url = f"{ANIMEPAHE_BASE}/api?m=search&q={quote_plus(title)}"
                data = _animepahe_json_request(page, api_url, f"search for {title}")
                results = data.get("data", [])
                if not results:
                    log(f"[AnimePahe] No results for: {title}")
                    return result
                
                # Use similarity check to find the best match instead of just picking results[0]
                best_match = results[0]
                search_title_norm = _normalize_title(title)
                best_score = _title_similarity_score(title, best_match.get("title", ""))
                
                for res in results:
                    res_title = res.get("title", "")
                    score = _title_similarity_score(title, res_title)
                    if score > best_score:
                        best_score = score
                        best_match = res
                    if score > 0.95: # Close enough to stop
                        break
                
                session_id = best_match["session"]
                log(f"[AnimePahe] Best search match: {best_match.get('title')} (score: {best_score:.2f})")
                result["session"] = session_id

            anime_url = f"{ANIMEPAHE_BASE}/anime/{session_id}"
            response = page.goto(anime_url, wait_until="commit", timeout=45000)
            
            if response and response.status == 404:
                log(f"[AnimePahe] 404 Not Found for {anime_url}. Attempting to re-search...")
                # Clear session_id and trigger a re-search
                api_url = f"{ANIMEPAHE_BASE}/api?m=search&q={quote_plus(title)}"
                data = _animepahe_json_request(page, api_url, f"recovery search for {title}")
                results = data.get("data", [])
                if results:
                    best_match = results[0]
                    best_score = 0
                    for res in results:
                        score = _title_similarity_score(title, res.get("title", ""))
                        if score > best_score:
                            best_score = score
                            best_match = res
                    
                    session_id = best_match["session"]
                    result["session"] = session_id
                    anime_url = f"{ANIMEPAHE_BASE}/anime/{session_id}"
                    log(f"[AnimePahe] Re-search found: {best_match.get('title')} (session: {session_id})")
                    page.goto(anime_url, wait_until="commit", timeout=45000)
                else:
                    log(f"[AnimePahe] Recovery search failed for {title}")
                    return result
            
            page.wait_for_timeout(2000)

            try:
                page.wait_for_selector(".content-wrapper, .anime-content", timeout=15000)
            except Exception:
                page.wait_for_timeout(5000)

            page_content = page.content()
            id_match = re.search(r'let\s+id\s*=\s*"([a-f0-9-]+)"', page_content)
            if not id_match:
                log("[AnimePahe] Could not find anime ID in page source")
                return result
            anime_id = id_match.group(1)

            # Resolve episode with offset
            adjusted_ep = int(episode_number) + offset
            all_episodes = []
            target_page = (adjusted_ep // 30) + 2
            for pg in range(1, 101):
                api_url = f"{ANIMEPAHE_BASE}/api?m=release&id={anime_id}&sort=episode_asc&page={pg}"
                data = _animepahe_json_request(page, api_url, f"release page {pg} for {anime_id}")
                episodes = data.get("data", [])
                if not episodes:
                    break
                all_episodes.extend(episodes)
                if pg >= data.get("last_page", 1):
                    break

            normalized = []
            for release in all_episodes:
                ep_num = _parse_episode_number(release.get("episode"))
                if ep_num is None:
                    continue
                normalized.append((ep_num, release))

            normalized.sort(key=lambda item: item[0])
            use_relative_order = bool(normalized) and normalized[0][0] > 1

            ordered_episodes = []
            for idx, (provider_ep_num, release) in enumerate(normalized, start=1):
                ordered_episodes.append({
                    "ep_number": idx if use_relative_order else provider_ep_num,
                    "provider_ep_number": provider_ep_num,
                    "episode_session": release.get("session"),
                    "snapshot": release.get("snapshot"),
                    "stream_url": None,
                    "provider": "animepahe",
                    "anime_session": session_id,
                })

            result["episodes"] = ordered_episodes
            result["available_episodes"] = len(ordered_episodes)

            target_episode, match_mode = _select_animepahe_episode(all_episodes, adjusted_ep)
            if not target_episode:
                available = [_parse_episode_number(ep.get("episode")) for ep in all_episodes]
                available = [ep for ep in available if ep is not None]
                log(f"[AnimePahe] Episode {episode_number} not found for session {session_id}. Available: {available[:10]}")
                return result

            if match_mode == "relative" and all_episodes:
                log(f"[AnimePahe] Falling back to relative episode order for request {episode_number}")

            play_url = f"{ANIMEPAHE_BASE}/play/{session_id}/{target_episode['session']}"
            page.goto(play_url, wait_until="commit", timeout=45000)
            page.wait_for_timeout(3000)
            play_content = page.content()
            kwik_matches = re.findall(r'https://kwik\.[a-z]+/e/[a-zA-Z0-9]+', play_content)

            result["episode"] = {
                "ep_number": int(episode_number),
                "provider_ep_number": _parse_episode_number(target_episode.get("episode")),
                "episode_session": target_episode["session"],
                "snapshot": target_episode.get("snapshot"),
                "stream_url": kwik_matches[0] if kwik_matches else None,
                "provider": "animepahe",
                "anime_session": session_id
            }
            for episode_meta in result["episodes"]:
                if episode_meta["episode_session"] == target_episode["session"]:
                    episode_meta["stream_url"] = kwik_matches[0] if kwik_matches else None
                    break
            return result
        finally:
            browser.close()


def scrape_animepahe_catalog_sync(title: str, session_id: str | None = None, offset: int = 0):
    """Fetch AnimePahe episode metadata without opening a play page."""
    from playwright.sync_api import sync_playwright

    result = {
        "title": title,
        "provider": "animepahe",
        "session": session_id,
        "episodes": [],
        "available_episodes": 0,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=PLAYWRIGHT_LAUNCH_ARGS)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            _animepahe_warmup(page)

            if not session_id:
                api_url = f"{ANIMEPAHE_BASE}/api?m=search&q={quote_plus(title)}"
                data = _animepahe_json_request(page, api_url, f"search for {title}")
                results = data.get("data", [])
                if not results:
                    log(f"[AnimePahe] No results for: {title}")
                    return result
                session_id = results[0]["session"]
                result["session"] = session_id

            anime_url = f"{ANIMEPAHE_BASE}/anime/{session_id}"
            response = page.goto(anime_url, wait_until="commit", timeout=45000)
            if response and response.status == 404:
                log(f"[AnimePahe] 404 Not Found for {anime_url}. Session ID may be stale.")
            page.wait_for_timeout(2000)
            try:
                page.wait_for_selector(".content-wrapper, .anime-content", timeout=15000)
            except Exception:
                page.wait_for_timeout(5000)

            page_content = page.content()
            id_match = re.search(r'let\s+id\s*=\s*"([a-f0-9-]+)"', page_content)
            if not id_match:
                log("[AnimePahe] Could not find anime ID in page source")
                return result
            anime_id = id_match.group(1)

            all_episodes = []
            for pg in range(1, 101):
                api_url = f"{ANIMEPAHE_BASE}/api?m=release&id={anime_id}&sort=episode_asc&page={pg}"
                data = _animepahe_json_request(page, api_url, f"release page {pg} for {anime_id}")
                episodes = data.get("data", [])
                if not episodes:
                    break
                all_episodes.extend(episodes)
                if pg >= data.get("last_page", 1):
                    break

            filtered_releases = []
            for release in all_episodes:
                ep_num = _parse_episode_number(release.get("episode"))
                if ep_num is None:
                    continue
                if offset > 0 and ep_num <= offset:
                    continue
                filtered_releases.append((ep_num, release))

            filtered_releases.sort(key=lambda item: item[0])
            use_relative_order = bool(filtered_releases) and filtered_releases[0][0] > 1

            ordered_episodes = []
            for idx, (provider_ep_num, release) in enumerate(filtered_releases, start=1):
                ordered_episodes.append({
                    "ep_number": idx if use_relative_order else provider_ep_num - offset if offset > 0 else provider_ep_num,
                    "provider_ep_number": provider_ep_num,
                    "episode_session": release.get("session"),
                    "snapshot": release.get("snapshot"),
                    "stream_url": None,
                    "provider": "animepahe",
                    "anime_session": session_id,
                })

            result["episodes"] = ordered_episodes
            result["available_episodes"] = len(ordered_episodes)
            return result
        finally:
            browser.close()


async def animepahe_get_stream(session: str, episode_session: str) -> dict | None:
    """Resolve a specific AnimePahe episode to its stream metadata."""
    from playwright.async_api import async_playwright
    from bs4 import BeautifulSoup
    import re

    play_url = f"https://animepahe.pw/play/{session}/{episode_session}"
    log(f"[AnimePahe] Resolving stream: {play_url}")

    # 1. Try Rotational API Fallback (Turbo)
    html = _fetch_with_api_fallback(
        play_url, 
        use_browser=True, 
        zyte_actions=[{"action": "waitForSelector", "selector": {"type": "css", "value": "#resolutionMenu button"}, "timeout": 15}],
        wait_for_selector="#resolutionMenu button"
    )
    
    if html:
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        for btn in soup.select('#resolutionMenu button'):
            quality = btn.get_text(strip=True)
            stream_url = btn.get('data-src') or btn.get('data-url')
            if stream_url: links.append({"quality": quality, "url": stream_url})
        
        if links:
            log(f"[AnimePahe][Zyte] Found {len(links)} streams")
            return {
                "stream_url": links[0]["url"],
                "all_qualities": [l["url"] for l in links],
                "provider": "animepahe"
            }
        
        # Fallback regex for Kwik links in HTML
        kwik_matches = re.findall(r'https://kwik\.cx/e/[a-zA-Z0-9]+', html)
        if kwik_matches:
            log(f"[AnimePahe][Zyte] Found Kwik links via Regex: {len(kwik_matches)}")
            return {
                "stream_url": kwik_matches[0],
                "all_qualities": list(set(kwik_matches)),
                "provider": "animepahe"
            }

    # 2. Fallback to Local Playwright (Free)
    log(f"[AnimePahe][Local] Using local Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=PLAYWRIGHT_LAUNCH_ARGS)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await page.goto(ANIMEPAHE_BASE, wait_until="commit", timeout=45000)
            await page.wait_for_timeout(5000)
            await page.goto(play_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(2000)
            page_content = await page.content()
            kwik_matches = re.findall(r'https://kwik\.[a-z]+/e/[a-zA-Z0-9]+', page_content)
            if kwik_matches:
                resolved = await resolve_kwik_stream(kwik_matches[0])
                if resolved:
                    resolved.setdefault("embed_url", kwik_matches[0])
                    return resolved
                return {
                    "stream_url": kwik_matches[0],
                    "embed_url": kwik_matches[0],
                    "all_qualities": list(set(kwik_matches)),
                    "provider": "animepahe"
                }
        finally:
            await browser.close()

    return None


async def resolve_kwik_stream(url: str) -> dict | None:
    """Resolve a kwik embed page to a direct playable media URL."""
    from playwright.async_api import async_playwright
    import re

    # 0. Check Cache (MongoDB)
    if db is not None:
        cached = db.streams.find_one({"url": url})
        if cached and cached.get("stream_url"):
            log(f"[Kwik][Cache] Hit for: {url}")
            return {"stream_url": cached["stream_url"], "provider": "kwik"}

    # 1. Skip Rotational API Fallback for Kwik
    # Kwik.cx requires JS execution to decrypt the URL. Zyte/ScraperAPI/etc. HTML response 
    # will not contain the decrypted .m3u8, so the regex always fails. 
    # We go straight to Local Playwright to save API credits.

    # 2. Fallback to Local Playwright (Free)
    log(f"[Kwik][Local] Using local Playwright...")
    request_candidates: list[str] = []
    response_candidates: list[str] = []

    def push_candidate(candidate: str | None):
        if not candidate:
            return
        lower = candidate.lower()
        if ".m3u8" in lower or ".mp4" in lower:
            request_candidates.append(candidate)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=PLAYWRIGHT_LAUNCH_ARGS)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        page.on("request", lambda req: push_candidate(req.url))

        def handle_response(res):
            content_type = (res.headers.get("content-type") or "").lower()
            lower_url = res.url.lower()
            if ".m3u8" in lower_url or ".mp4" in lower_url or "mpegurl" in content_type or "video/" in content_type:
                response_candidates.append(res.url)

        page.on("response", handle_response)

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(6000)
            html = await page.content()
        finally:
            await browser.close()

    html_candidates = re.findall(r'https?://[^"\']+\.(?:m3u8|mp4)[^"\']*', html)
    ordered_candidates = []
    for candidate in [*response_candidates, *request_candidates, *html_candidates]:
        if candidate not in ordered_candidates:
            ordered_candidates.append(candidate)

    if ordered_candidates:
        return {
            "stream_url": ordered_candidates[0],
            "embed_url": url,
            "all_qualities": ordered_candidates,
            "provider": "animepahe",
        }

    return None


# ── Entry point ──────────────────────────────────────────────

async def run_action(action: str, params: dict):
    """Dispatch to the appropriate scraper function."""

    if action == "animepahe_full":
        from scraper import scrape_animepahe
        result = await scrape_animepahe(
            params["title"],
            max_episodes=params.get("max_episodes", 0),
            session_id=params.get("session_id")
        )
        return result

    elif action == "animepahe_stream":
        return await animepahe_get_stream(
            params["session"],
            params["episode_session"]
        )

    elif action == "kwik_stream":
        return await resolve_kwik_stream(
            params["url"]
        )

    elif action == "animepahe_episode":
        from scraper import scrape_animepahe
        result = await scrape_animepahe(
            params["title"],
            session_id=params.get("session_id"),
            target_episode=int(params["episode_number"])
        )
        # Find the specific episode in the catalog result
        target_ep = str(params["episode_number"])
        found_ep = next((ep for ep in result.get("episodes", []) if str(ep.get("ep_number")) == target_ep), None)
        return {"episode": found_ep, "session": result.get("session")} if found_ep else result

    elif action == "animepahe_catalog":
        from scraper import scrape_animepahe
        result = await scrape_animepahe(
            params["title"],
            session_id=params.get("session_id")
        )
        return result

    elif action == "animepahe_latest":
        from scraper import scrape_animepahe_latest
        return await scrape_animepahe_latest(params.get("pages", 3))
    elif action == "reanime_latest":
        from scraper import scrape_reanime_latest
        return await scrape_reanime_latest()

    elif action == "anime_schedule":
        from scraper import scrape_anime_schedule
        return await scrape_anime_schedule()

    elif action == "reanime_search":
        return await reanime_search(params["title"], params.get("anilist_id"))

    elif action == "reanime_scrape_episode":
        return await reanime_scrape_episode(params["slug"], params["episode_number"])

    elif action == "miruro_episode":
        from scraper import miruro_scrape_episode
        return await miruro_scrape_episode(params["anilist_id"], params["episode_number"])

    elif action == "shiroko_episode":
        from scraper import shiroko_scrape_episode
        return await shiroko_scrape_episode(params["anilist_id"], params["episode_number"])

    elif action == "animeverse_episode":
        from scraper import animeverse_scrape_episode
        return await animeverse_scrape_episode(params["title"], params["episode_number"])

    elif action == "uniquestream_episode":
        from scraper import uniquestream_scrape_episode
        return await uniquestream_scrape_episode(params["title"], params["episode_number"])

    else:
        log(f"Unknown action: {action}")
        return None

if __name__ == "__main__":
    import sys
    import json
    import asyncio

    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: python scraper_runner.py <action> <json_params>"}))
        sys.exit(1)

    action = sys.argv[1]
    params = json.loads(sys.argv[2])

    result = asyncio.run(run_action(action, params))

    # Print JSON result to stdout (this is what the backend parses)
    print(json.dumps(result if result else {}))
