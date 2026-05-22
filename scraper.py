import asyncio
import json
import sys
import re
import os
from dotenv import load_dotenv
load_dotenv() # Load .env variables

# Ensure Playwright uses a project-local browser cache on Render
_playwright_cache = os.path.join(os.path.dirname(__file__), ".playwright")
if os.path.exists(_playwright_cache):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", _playwright_cache)

from playwright.async_api import async_playwright

# Fix for Windows: Playwright requires ProactorEventLoop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# ── MongoDB Connectivity (Cache Layer) ─────────────────────────
import pymongo
from pymongo import MongoClient

MONGODB_URI = os.environ.get("MONGODB_URI")
MONGODB_DB = os.environ.get("MONGODB_DB", "aniverse")

def get_db():
    if not MONGODB_URI:
        return None
    try:
        client = MongoClient(MONGODB_URI)
        return client[MONGODB_DB]
    except Exception as e:
        _log(f"[DB] Connection Error: {e}")
        return None

db = get_db()

# When called as a subprocess, redirect all prints to stderr
# so stdout stays clean for JSON output
_is_subprocess = os.environ.get("SCRAPER_SUBPROCESS") == "1"

def _log(msg: str):
    if _is_subprocess:
        print(msg, file=sys.stderr)
    else:
        print(msg)

# ── API Scraper Integrations (Rotational Fallback) ──────────────────────────
ZYTE_API_KEY = os.environ.get("ZYTE_API_KEY")
SCRAPER_API_KEY = os.environ.get("SCRAPER_API_KEY")
SCRAPINGANT_API_KEY = os.environ.get("SCRAPINGANT_API_KEY")
WEBSCRAPING_AI_KEY = os.environ.get("WEBSCRAPING_AI_KEY")

class APILimitReached(Exception):
    pass

def _extract_json_from_html(html, use_browser):
    if use_browser and isinstance(html, str) and ("{" in html and "}" in html):
        import json, re
        match = re.search(r'\{.*\}', html, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                return parsed
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
    _log(f"[ScraperAPI] Fetching: {url}")
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
            _log(f"[ScraperAPI] Limit/Auth Error ({response.status_code}). Exhausted.")
            raise APILimitReached("ScraperAPI Exhausted")
        response.raise_for_status()
        html = response.text
        if _is_cloudflare_blocked(html):
            _log("[ScraperAPI] Cloudflare/DDoS-Guard block detected. Treating as failure.")
            return None
        return _extract_json_from_html(html, use_browser)
    except APILimitReached:
        raise
    except Exception as e:
        _log(f"[ScraperAPI] Error: {e}")
        return None

def _try_scrapingant_api(url, use_browser=True, wait_for_selector=None):
    if not SCRAPINGANT_API_KEY: return None
    import requests
    _log(f"[ScrapingAnt] Fetching: {url}")
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
            _log(f"[ScrapingAnt] Limit/Auth Error ({response.status_code}). Exhausted.")
            raise APILimitReached("ScrapingAnt Exhausted")
        response.raise_for_status()
        html = response.text
        if _is_cloudflare_blocked(html):
            _log("[ScrapingAnt] Cloudflare/DDoS-Guard block detected. Treating as failure.")
            return None
        return _extract_json_from_html(html, use_browser)
    except APILimitReached:
        raise
    except Exception as e:
        _log(f"[ScrapingAnt] Error: {e}")
        return None

def _try_webscraping_ai(url, use_browser=True):
    if not WEBSCRAPING_AI_KEY: return None
    import requests
    _log(f"[WebScraping.AI] Fetching: {url}")
    params = {"api_key": WEBSCRAPING_AI_KEY, "url": url, "proxy": "residential"}
    if use_browser: params["js"] = "true"
    
    try:
        response = requests.get("https://api.webscraping.ai/html", params=params, timeout=60)
        if response.status_code in [401, 402, 403, 429]:
            _log(f"[WebScraping.AI] Limit/Auth Error ({response.status_code}). Exhausted.")
            raise APILimitReached("WebScraping.AI Exhausted")
        response.raise_for_status()
        html = response.text
        if _is_cloudflare_blocked(html):
            _log("[WebScraping.AI] Cloudflare/DDoS-Guard block detected. Treating as failure.")
            return None
        return _extract_json_from_html(html, use_browser)
    except APILimitReached:
        raise
    except Exception as e:
        _log(f"[WebScraping.AI] Error: {e}")
        return None

def _try_zyte_api(url, use_browser=True, zyte_actions=None):
    if not ZYTE_API_KEY: return None
    import requests
    _log(f"[Zyte API] Fetching: {url}")
    payload = {"url": url, "browserHtml": use_browser}
    if zyte_actions: payload["actions"] = zyte_actions
        
    try:
        response = requests.post("https://api.zyte.com/v1/extract", auth=(ZYTE_API_KEY, ""), json=payload, timeout=60)
        if response.status_code in [401, 402, 403, 429]:
            _log(f"[Zyte API] Limit/Auth Error ({response.status_code}). Exhausted.")
            raise APILimitReached("Zyte API Exhausted")
        response.raise_for_status()
        data = response.json()
        if use_browser:
            html = data.get("browserHtml", "")
            if _is_cloudflare_blocked(html):
                _log("[Zyte API] Cloudflare/DDoS-Guard block detected. Treating as failure.")
                return None
            return _extract_json_from_html(html, use_browser)
        return data
    except APILimitReached:
        raise
    except Exception as e:
        _log(f"[Zyte API] Error: {e}")
        return None

def _fetch_with_api_fallback(url, use_browser=True, zyte_actions=None, sapi_instructions=None, wait_for_selector=None):
    """
    Rotational API fetcher.
    Priority: ScraperAPI -> ScrapingAnt -> WebScraping.AI -> Zyte API -> None (Local Playwright)
    """
    html = None
    is_animepahe = "animepahe" in url or "kwik" in url
    
    if is_animepahe:
        _log("[API Status] AnimePahe/Kwik URL detected — skipping ScraperAPI/ScrapingAnt/WebScraping.AI, going straight to Zyte or Local Playwright")
    
    if not is_animepahe:
        # 1. ScraperAPI
        try:
            html = _try_scraper_api(url, use_browser, sapi_instructions, wait_for_selector)
            if html:
                _log("[API Status] Successfully fetched via ScraperAPI")
                return html
        except APILimitReached:
            pass
            
        # 2. ScrapingAnt
        try:
            html = _try_scrapingant_api(url, use_browser, wait_for_selector)
            if html:
                _log("[API Status] Successfully fetched via ScrapingAnt")
                return html
        except APILimitReached:
            pass
            
        # 3. WebScraping.AI
        try:
            html = _try_webscraping_ai(url, use_browser)
            if html:
                _log("[API Status] Successfully fetched via WebScraping.AI")
                return html
        except APILimitReached:
            pass
        
    # 4. Zyte API
    try:
        html = _try_zyte_api(url, use_browser, zyte_actions)
        if html:
            _log("[API Status] Successfully fetched via Zyte API")
            return html
    except APILimitReached:
        pass
        
    _log("[API Status] All APIs exhausted or failed. Falling back to local Playwright...")
    return None




# ═══════════════════════════════════════════════════════════════
#  AnimePahe Scraper (Playwright — bypasses DDoS-Guard)
# ═══════════════════════════════════════════════════════════════

ANIMEPAHE_BASE = "https://animepahe.pw"


async def _new_animepahe_page(playwright):
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    page = await context.new_page()
    return browser, page


def _parse_episode_number(value) -> int | None:
    """Normalize AnimePahe episode values like 1, '1', or '1.0'."""
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _select_animepahe_episode(episodes: list, requested_episode: int):
    """
    Pick the best matching AnimePahe release for a requested season-relative episode.

    AnimePahe sometimes exposes franchise-global numbering for sequel pages
    (for example, a season page may start at episode 67 instead of 1).
    In that case, fall back to relative ordering: request #1 -> first release,
    request #2 -> second release, and so on.
    """
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
    available_numbers = [ep_num for ep_num, _ in normalized]
    min_available = available_numbers[0]

    if min_available > requested_episode and 1 <= requested_episode <= len(normalized):
        fallback_ep = normalized[requested_episode - 1][1]
        return fallback_ep, "relative"

    return None, "missing"

async def animepahe_search(title: str) -> dict | None:
    """
    Search AnimePahe for an anime title.
    Hybrid: Tries Zyte API first, falls back to Local Playwright.
    """
    # 0. Check Cache (MongoDB)
    if db is not None:
        cached = db.provider_mappings.find_one({"title": title, "provider": "animepahe"})
        if cached and cached.get("session"):
            _log(f"[AnimePahe][Cache] Hit: {cached.get('title')} (session: {cached.get('session')})")
            return {"session": cached["session"], "title": cached.get("title", title)}

    # 1. Try Zyte API (Turbo)
    api_url = f"{ANIMEPAHE_BASE}/api?m=search&q={title}"
    zyte_data = _fetch_with_api_fallback(api_url, use_browser=True)
    
    if zyte_data and isinstance(zyte_data, dict) and "data" in zyte_data:
        results = zyte_data["data"]
        best_match = results[0]
        search_title_lower = title.lower()
        for res in results:
            res_title = res.get("title", "").lower()
            if res_title == search_title_lower or search_title_lower in res_title:
                best_match = res
                if res_title == search_title_lower: break
        
        _log(f"[AnimePahe][Zyte] Match found: {best_match.get('title')}")
        return {"session": best_match["session"], "title": best_match.get("title", title)}

    # 2. Fallback to Local Playwright (Free)
    _log(f"[AnimePahe][Local] Using local Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # Navigate to homepage first (sets DDoS-Guard cookies)
            await page.goto(ANIMEPAHE_BASE, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)

            # Now call the API through the browser context (cookies are set)
            api_url = f"{ANIMEPAHE_BASE}/api?m=search&q={title}"
            response = await page.goto(api_url, wait_until="domcontentloaded", timeout=15000)

            # Parse the JSON from the page body
            body_text = await page.inner_text("body")
            data = json.loads(body_text)

            if data and data.get("data") and len(data["data"]) > 0:
                results = data["data"]
                # Try to find the best match
                best_match = results[0]
                search_title_lower = title.lower()
                
                for res in results:
                    res_title = res.get("title", "").lower()
                    # Exact match or contains the full title (useful for seasons)
                    if res_title == search_title_lower:
                        best_match = res
                        break
                    if search_title_lower in res_title:
                        best_match = res
                        # Keep looking for an even better (exact) match

                _log(f"[AnimePahe] Best match: {best_match.get('title')} (session: {best_match.get('session')})")
                return {
                    "session": best_match["session"],
                    "title": best_match.get("title", title)
                }
            else:
                _log(f"[AnimePahe] No results for: {title}")
        except Exception as e:
            _log(f"[AnimePahe] Search error: {e}")
        finally:
            await browser.close()
    return None


async def _animepahe_search_with_page(page, title: str) -> dict | None:
    api_url = f"{ANIMEPAHE_BASE}/api?m=search&q={title}"
    await page.goto(api_url, wait_until="domcontentloaded", timeout=15000)

    body_text = await page.inner_text("body")
    data = json.loads(body_text)

    if data and data.get("data") and len(data["data"]) > 0:
        results = data["data"]
        best_match = results[0]
        search_title_lower = title.lower()

        for res in results:
            res_title = res.get("title", "").lower()
            if res_title == search_title_lower:
                best_match = res
                break
            if search_title_lower in res_title:
                best_match = res

        _log(f"[AnimePahe] Best match: {best_match.get('title')} (session: {best_match.get('session')})")
        return {
            "session": best_match["session"],
            "title": best_match.get("title", title)
        }

    _log(f"[AnimePahe] No results for: {title}")
    return None


async def animepahe_get_episodes(session: str, max_pages: int = 100, target_episode: int = None) -> list:
    """
    Fetch episode list from AnimePahe.
    Hybrid: Tries Zyte API first, falls back to Local Playwright.
    """
    _log(f"[AnimePahe] Fetching episodes for session: {session} (Target Ep: {target_episode})")
    
    # 1. Try Zyte API (Turbo)
    # If we have a target episode, calculate the likely page (30 eps per page)
    target_page = 1
    if target_episode and target_episode > 30:
        target_page = ((target_episode - 1) // 30) + 1
        _log(f"[AnimePahe][Zyte] Calculating target page for Ep {target_episode} -> Page {target_page}")

    api_url = f"{ANIMEPAHE_BASE}/api?m=release&id={session}&sort=episode_asc&page={target_page}"
    zyte_data = _fetch_with_api_fallback(api_url, use_browser=True)
    
    if zyte_data and isinstance(zyte_data, dict) and "data" in zyte_data:
        _log(f"[AnimePahe][Zyte] Successfully fetched episode data (Page {target_page})")
        all_episodes = zyte_data.get("data", [])
        
        # If we didn't find our target episode on this page (and it's not the first page),
        # or if it's a short series and we want the first few pages anyway:
        if target_page == 1:
            last_page = zyte_data.get("last_page", 1)
            if last_page > 1:
                max_zyte_pages = min(last_page, 3)
                for pg in range(2, max_zyte_pages + 1):
                    pg_url = f"{ANIMEPAHE_BASE}/api?m=release&id={session}&sort=episode_asc&page={pg}"
                    pg_data = _fetch_with_api_fallback(pg_url, use_browser=True)
                    if pg_data and isinstance(pg_data, dict) and "data" in pg_data:
                        all_episodes.extend(pg_data["data"])
                        _log(f"[AnimePahe][Zyte] Fetched additional page {pg}")
        
        return all_episodes

    # 2. Fallback to Local Playwright (Free)
    _log(f"[AnimePahe][Local] Using local Playwright...")
    all_episodes = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # CRITICAL: Visit homepage first to set DDoS-Guard cookies
            await page.goto(ANIMEPAHE_BASE, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)

            # Now hit the anime page to get the internal ID
            anime_url = f"{ANIMEPAHE_BASE}/anime/{session}"
            await page.goto(anime_url, wait_until="domcontentloaded", timeout=15000)

            # Wait for actual content to render
            try:
                await page.wait_for_selector(".content-wrapper, .anime-content", timeout=10000)
            except:
                await page.wait_for_timeout(3000)

            # Extract the `id` variable from the page's <script> tags
            # Pattern from research: `let id = "ba878a27-0911-...";`
            page_content = await page.content()
            id_match = re.search(r'let\s+id\s*=\s*"([a-f0-9-]+)"', page_content)

            if not id_match:
                _log("[AnimePahe] Could not find anime ID in page source")
                return []

            anime_id = id_match.group(1)
            _log(f"[AnimePahe] Internal ID: {anime_id}")

            # Fetch episodes page by page
            for pg in range(1, max_pages + 1):
                api_url = f"{ANIMEPAHE_BASE}/api?m=release&id={anime_id}&sort=episode_asc&page={pg}"
                await page.goto(api_url, wait_until="domcontentloaded", timeout=15000)

                body_text = await page.inner_text("body")
                try:
                    data = json.loads(body_text)
                except json.JSONDecodeError:
                    _log(f"[AnimePahe] Failed to parse page {pg}")
                    break

                episodes = data.get("data", [])
                if not episodes:
                    break

                all_episodes.extend(episodes)
                _log(f"[AnimePahe] Page {pg}: {len(episodes)} episodes (total: {len(all_episodes)})")

                # Check if there are more pages
                last_page = data.get("last_page", 1)
                if pg >= last_page:
                    break

                await page.wait_for_timeout(500)

        except Exception as e:
            _log(f"[AnimePahe] Episode fetch error: {e}")
        finally:
            await browser.close()

    return all_episodes


async def animepahe_get_stream(session: str, episode_session: str) -> dict | None:
    """
    Get the kwik.cx streaming embed URL for a specific episode.
    Returns dict with 'stream_url' (kwik embed), 'quality' keys.
    """
    play_url = f"{ANIMEPAHE_BASE}/play/{session}/{episode_session}"
    _log(f"[AnimePahe] Resolving stream: {play_url}")

    # 1. Try Zyte API (Turbo)
    html = _fetch_with_api_fallback(play_url, use_browser=True)
    if html:
        kwik_matches = re.findall(r'https://kwik\.[a-z]+/e/[a-zA-Z0-9]+', html)
        if kwik_matches:
            _log(f"[AnimePahe][Zyte] Successfully resolved stream")
            return {
                "stream_url": kwik_matches[0],
                "all_qualities": list(set(kwik_matches)),
                "provider": "animepahe"
            }

    # 2. Fallback to Local Playwright (Free)
    _log(f"[AnimePahe][Local] Using local Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # CRITICAL: Visit homepage first to set DDoS-Guard cookies
            await page.goto(ANIMEPAHE_BASE, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)

            await page.goto(play_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)

            # Extract kwik URLs from the page source
            # Pattern from research: kwik.cx/e/UXyar0HZkcod
            page_content = await page.content()
            kwik_matches = re.findall(r'https://kwik\.[a-z]+/e/[a-zA-Z0-9]+', page_content)

            if kwik_matches:
                # Return the first one (usually highest quality)
                return {
                    "stream_url": kwik_matches[0],
                    "all_qualities": list(set(kwik_matches)),
                    "provider": "animepahe"
                }
            else:
                _log(f"[AnimePahe] No kwik URLs found on play page")

        except Exception as e:
            _log(f"[AnimePahe] Stream resolve error: {e}")
        finally:
            await browser.close()

    return None


async def scrape_animepahe_episode(title: str, episode_number: int, session_id: str = None):
    """
    Resolve a single AnimePahe episode in one browser session.
    This avoids paying the Chromium startup cost for search, release list,
    and play-page resolution as separate subprocess steps.
    """
    result = {
        "title": title,
        "provider": "animepahe",
        "session": session_id,
        "episode": None
    }

    async with async_playwright() as p:
        browser, page = await _new_animepahe_page(p)

        try:
            await page.goto(ANIMEPAHE_BASE, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)

            if not session_id:
                search_result = await _animepahe_search_with_page(page, title)
                if not search_result:
                    return result
                session_id = search_result["session"]
                result["session"] = session_id

            anime_url = f"{ANIMEPAHE_BASE}/anime/{session_id}"
            await page.goto(anime_url, wait_until="domcontentloaded", timeout=15000)

            try:
                await page.wait_for_selector(".content-wrapper, .anime-content", timeout=10000)
            except Exception:
                await page.wait_for_timeout(3000)

            page_content = await page.content()
            id_match = re.search(r'let\s+id\s*=\s*"([a-f0-9-]+)"', page_content)
            if not id_match:
                _log("[AnimePahe] Could not find anime ID in page source")
                return result

            anime_id = id_match.group(1)
            _log(f"[AnimePahe] Internal ID: {anime_id}")

            all_episodes = []
            for pg in range(1, 101):
                api_url = f"{ANIMEPAHE_BASE}/api?m=release&id={anime_id}&sort=episode_asc&page={pg}"
                await page.goto(api_url, wait_until="domcontentloaded", timeout=15000)

                body_text = await page.inner_text("body")
                data = json.loads(body_text)
                episodes = data.get("data", [])
                if not episodes:
                    break

                all_episodes.extend(episodes)

                if pg >= data.get("last_page", 1):
                    break

            target_episode, match_mode = _select_animepahe_episode(all_episodes, int(episode_number))
            if not target_episode:
                available = [_parse_episode_number(ep.get("episode")) for ep in all_episodes]
                available = [ep for ep in available if ep is not None]
                if available:
                    _log(
                        f"[AnimePahe] Episode {episode_number} not found for session {session_id}. "
                        f"Available episode numbers: {available[:10]}"
                    )
                else:
                    _log(f"[AnimePahe] Episode {episode_number} not found for session {session_id}")
                return result

            if match_mode == "relative":
                _log(
                    f"[AnimePahe] Falling back to relative episode order for request {episode_number} "
                    f"(provider numbering starts at {_parse_episode_number(all_episodes[0].get('episode'))})"
                )

            play_url = f"{ANIMEPAHE_BASE}/play/{session_id}/{target_episode['session']}"
            await page.goto(play_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(1000)

            play_content = await page.content()
            kwik_matches = re.findall(r'https://kwik\.[a-z]+/e/[a-zA-Z0-9]+', play_content)
            stream_url = kwik_matches[0] if kwik_matches else None

            result["episode"] = {
                "ep_number": int(episode_number),
                "provider_ep_number": _parse_episode_number(target_episode.get("episode")),
                "episode_session": target_episode["session"],
                "snapshot": target_episode.get("snapshot"),
                "stream_url": stream_url,
                "provider": "animepahe",
                "anime_session": session_id
            }
        except Exception as e:
            _log(f"[AnimePahe] Episode resolve error: {e}")
        finally:
            await browser.close()

    return result


async def scrape_animepahe(title: str, max_episodes: int = 0, session_id: str = None, target_episode: int = None):
    """
    Full AnimePahe pipeline: search (if no session_id) → episodes → streams.
    Returns structured data ready for DB insertion.
    
    Args:
        title: Anime title to search for
        max_episodes: Max episodes to resolve streams for (0 = all, just store metadata)
        session_id: Optional session ID to skip search
        target_episode: Optional specific episode to ensure is fetched
    """
    result = {
        "title": title,
        "provider": "animepahe",
        "session": session_id,
        "episodes": []
    }

    # 1. Search (only if no session_id provided)
    if not session_id:
        search_result = await animepahe_search(title)
        if not search_result:
            return result
        session = search_result["session"]
        result["session"] = session
    else:
        session = session_id

    # 2. Get episode list
    episodes = await animepahe_get_episodes(session, target_episode=target_episode)
    if not episodes:
        return result

    # 3. Store episode metadata (session IDs for later on-demand resolution)
    for ep in episodes:
        ep_data = {
            "ep_number": ep.get("episode"),
            "episode_session": ep.get("session"),
            "snapshot": ep.get("snapshot"),
            "provider": "animepahe",
            "anime_session": session,
            "stream_url": None  # Will be resolved on-demand
        }
        result["episodes"].append(ep_data)

    # 4. Optionally resolve streams for first N episodes
    if max_episodes > 0:
        to_resolve = result["episodes"][:max_episodes]
        for ep_data in to_resolve:
            stream = await animepahe_get_stream(session, ep_data["episode_session"])
            if stream:
                ep_data["stream_url"] = stream["stream_url"]
                _log(f"  -> Ep {ep_data['ep_number']}: {stream['stream_url']}")
            await asyncio.sleep(0.5)  # Be polite

    _log(f"[AnimePahe] Complete: {len(result['episodes'])} episodes catalogued")
    return result


async def scrape_animepahe_latest(pages: int = 3) -> list:
    """
    Fetch the latest releases from AnimePahe.
    Hybrid: Tries Zyte API first, falls back to Local Playwright.
    """
    _log(f"[AnimePahe] Fetching latest releases ({pages} pages)")
    
    # 1. Try Zyte API (Turbo)
    # We'll just fetch the first page via Zyte to see if it works
    api_url = f"{ANIMEPAHE_BASE}/api?m=airing&page=1"
    zyte_data = _fetch_with_api_fallback(api_url, use_browser=True)
    
    if zyte_data and isinstance(zyte_data, dict) and "data" in zyte_data:
        _log(f"[AnimePahe][Zyte] Successfully fetched latest releases")
        return zyte_data.get("data", [])

    # 2. Fallback to Local Playwright (Free)
    _log(f"[AnimePahe][Local] Using local Playwright...")
    all_releases = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            for pg_num in range(1, pages + 1):
                url = ANIMEPAHE_BASE if pg_num == 1 else f"{ANIMEPAHE_BASE}/?page={pg_num}"
                _log(f"  -> Scraping page {pg_num}: {url}")
                
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    
                    # Wait for the episodes to load
                    await page.wait_for_selector(".episode-wrap", timeout=20000)
                    
                    episodes = await page.locator(".episode-wrap").all()
                    if not episodes:
                        _log(f"  -> No episodes found on page {pg_num}, stopping.")
                        break

                    for ep in episodes:
                        try:
                            title_el = ep.locator(".episode-title a")
                            title = await title_el.inner_text()
                            href = await title_el.get_attribute("href") # /anime/session
                            session = href.split("/")[-1] if href else None
                            
                            # Use session + title as unique key to avoid duplicates across pages
                            # (though unlikely on latest releases unless we scrape very fast)
                            if session in seen_sessions:
                                continue
                            seen_sessions.add(session)

                            snapshot_el = ep.locator(".episode-snapshot img")
                            snapshot = await snapshot_el.get_attribute("data-src") or await snapshot_el.get_attribute("src")
                            
                            ep_num_el = ep.locator(".episode-number")
                            ep_num_text = await ep_num_el.inner_text()
                            
                            # Ep num text is usually "Wistoria Season 2 Episode 15" or "Ep 15"
                            nums = re.findall(r"(\d+)", ep_num_text)
                            ep_num = nums[-1] if nums else "1"
                            
                            latest_releases.append({
                                "title": title.strip(),
                                "session": session,
                                "snapshot": snapshot,
                                "episode": ep_num,
                                "provider": "animepahe"
                            })
                        except Exception as e:
                            _log(f"  -> Failed to parse an episode on page {pg_num}: {e}")
                    
                    # Small delay between pages
                    await page.wait_for_timeout(1000)
                except Exception as pg_e:
                    _log(f"  -> Error on page {pg_num}: {pg_e}")
                    break
                    
            _log(f"[AnimePahe] Found {len(latest_releases)} total latest releases across {pages} pages")
        except Exception as e:
            _log(f"[AnimePahe] Latest releases scrape error: {e}")
        finally:
            await browser.close()

    return latest_releases


async def scrape_reanime_latest() -> list:
    """
    Fetch latest releases from Re:ANIME.
    Hybrid: Tries Zyte API first, falls back to Local Playwright.
    """
    _log("[Re:ANIME] Fetching latest releases")
    
    # 1. Try Zyte API (Turbo)
    # Re:ANIME usually has a JSON endpoint for latest releases if we look close, 
    # but for now we'll use browserHtml on the homepage.
    html = _fetch_with_api_fallback("https://reanime.to/")
    if html:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        # Simplified parsing for the hybrid logic
        releases = []
        # Look for cards on the homepage
        cards = soup.select("a[href*='/watch/']")
        for card in cards:
            title = card.select_one("h3")
            if title:
                releases.append({
                    "title": title.get_text(strip=True),
                    "url": card.get("href")
                })
        if releases:
            _log(f"[Re:ANIME][Zyte] Found {len(releases)} latest releases")
            return releases

    # 2. Fallback to Local Playwright (Free)
    _log("[Re:ANIME][Local] Using local Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        try:
            async def _extract_latest_cards():
                return await page.evaluate("""() => {
                    const results = [];
                    const toAbsoluteUrl = (value) => {
                        if (!value) return '';
                        try {
                            return new URL(value, window.location.origin).href;
                        } catch {
                            return value;
                        }
                    };

                    const getSnapshot = (card) => {
                        const imgEl = card.querySelector('img');
                        if (imgEl) {
                            const direct =
                                imgEl.currentSrc ||
                                imgEl.getAttribute('src') ||
                                imgEl.getAttribute('data-src') ||
                                imgEl.getAttribute('data-lazy-src') ||
                                imgEl.getAttribute('data-image') ||
                                imgEl.getAttribute('data-original') ||
                                imgEl.getAttribute('data-src-img') ||
                                '';
                            if (direct) return toAbsoluteUrl(direct);

                            const srcset =
                                imgEl.getAttribute('srcset') ||
                                imgEl.getAttribute('data-srcset') ||
                                '';
                            if (srcset) {
                                const first = srcset.split(',')[0]?.trim().split(' ')[0];
                                if (first) return toAbsoluteUrl(first);
                            }
                        }

                        const posterEl = card.querySelector('[style*="background-image"]');
                        const bg = posterEl instanceof HTMLElement ? posterEl.style.backgroundImage : '';
                        const bgMatch = bg ? bg.match(/url\\(["']?(.*?)["']?\\)/) : null;
                        return bgMatch?.[1] ? toAbsoluteUrl(bgMatch[1]) : '';
                    };

                    const cards = Array.from(document.querySelectorAll('a[href*="/watch/"]'))
                        .filter(a => {
                            const href = a.getAttribute('href') || '';
                            return href.includes('?ep=latest') || a.querySelector('h3');
                        });
                    
                    for (const card of cards) {
                        const href = card.getAttribute('href') || '';
                        const slugMatch = href.match(/\\/watch\\/([^?]+)/);
                        if (!slugMatch) continue;
                        const slug = slugMatch[1];
                        
                        const titleEl = card.querySelector('h3');
                        if (!titleEl) continue;
                        const title = titleEl.innerText.trim();
                        const snapshot = getSnapshot(card);
                        
                        let epNum = '1';
                        const subBadge = card.querySelector('[title="Subbed Episodes"]');
                        if (subBadge) {
                            epNum = subBadge.innerText.trim();
                        } else {
                            const badges = card.querySelectorAll('span');
                            for (const b of badges) {
                                if (/^\\d+$/.test(b.innerText.trim())) {
                                    epNum = b.innerText.trim();
                                    break;
                                }
                            }
                        }
                        
                        if (results.some(r => r.slug === slug)) continue;

                        results.push({
                            title: title,
                            slug: slug,
                            snapshot: snapshot,
                            episode: epNum,
                            provider: 'reanime'
                        });

                        if (results.length >= 12) break;
                    }
                    return results;
                }""")

            async def _block_heavy_requests(route):
                resource_type = route.request.resource_type
                if resource_type in {"media", "font"}:
                    await route.abort()
                    return
                await route.continue_()

            await page.route("**/*", _block_heavy_requests)
            await page.goto("https://reanime.to/home", wait_until="domcontentloaded", timeout=20000)

            # Give the SPA time to hydrate and inject release cards.
            try:
                await page.wait_for_function(
                    "() => document.querySelectorAll('a[href*=\"/watch/\"]').length >= 6",
                    timeout=18000,
                )
            except Exception:
                await page.wait_for_timeout(5000)

            for attempt in range(3):
                if attempt > 0:
                    await page.wait_for_timeout(1500 * attempt)

                latest_releases = await _extract_latest_cards()
                snapshot_count = sum(1 for item in latest_releases if item.get("snapshot"))
                _log(
                    f"[Re:ANIME] Latest scrape attempt {attempt + 1}: "
                    f"{len(latest_releases)} cards, {snapshot_count} snapshots"
                )

                if latest_releases and (snapshot_count >= min(len(latest_releases), 8) or attempt == 2):
                    break

                await page.mouse.wheel(0, 1200)
                await page.wait_for_timeout(1200)
                await page.mouse.wheel(0, -800)

            _log(f"[Re:ANIME] Found {len(latest_releases)} total latest releases")
        except Exception as e:
            _log(f"[Re:ANIME] Latest releases scrape error: {e}")
        finally:
            await browser.close()
            
    return latest_releases


# ═══════════════════════════════════════════════════════════════
#  CLI Test Interface
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "animepahe":
        title = sys.argv[2] if len(sys.argv) > 2 else "Bleach"
        max_ep = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        result = asyncio.run(scrape_animepahe(title, max_episodes=max_ep))
        print("\n--- SCRAPE COMPLETE ---")
        print(f"Title: {result['title']}")
        print(f"Session: {result['session']}")
        print(f"Episodes: {len(result['episodes'])}")
        for ep in result["episodes"][:10]:
            print(f"  Ep {ep['ep_number']}: {ep.get('stream_url', 'metadata only')}")
    elif len(sys.argv) > 1 and sys.argv[1] == "latest":
        result = asyncio.run(scrape_animepahe_latest())
        print(json.dumps(result))
    elif len(sys.argv) > 1 and sys.argv[1] == "reanime_latest":
        result = asyncio.run(scrape_reanime_latest())
        print(json.dumps(result))
    else:
        _log("Usage: python scraper.py <animepahe|latest|reanime_latest> [params]")

# ═══════════════════════════════════════════════════════════════
#  AnimeSchedule.net Scraper
# ═══════════════════════════════════════════════════════════════

async def scrape_anime_schedule():
    """Scrapes the weekly airing schedule from animeschedule.net."""
    _log("[Schedule] Starting hybrid scraper for animeschedule.net")
    
    # 1. Try Zyte API (Turbo)
    html = _fetch_with_api_fallback("https://animeschedule.net/")
    if html:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        schedule_data = {"monday":[], "tuesday":[], "wednesday":[], "thursday":[], "friday":[], "saturday":[], "sunday":[]}
        
        # Simple parsing for the hybrid logic
        days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        columns = soup.select(".timetable-column")
        for i, col in enumerate(columns):
            if i >= len(days): break
            day = days[i]
            shows = col.select(".timetable-column-show")
            for show in shows:
                title = show.select_one(".show-title-bar, h3")
                time_el = show.select_one(".show-air-time, time")
                if title:
                    schedule_data[day].append({
                        "title": title.get_text(strip=True),
                        "time": time_el.get_text(strip=True) if time_el else "??:??"
                    })
        
        if any(schedule_data.values()):
            _log(f"[Schedule][Zyte] Successfully parsed schedule")
            return schedule_data

    # 2. Fallback to Local Playwright (Free)
    _log("[Schedule][Local] Using local Playwright...")
    schedule_data = {
        "monday": [], "tuesday": [], "wednesday": [],
        "thursday": [], "friday": [], "saturday": [], "sunday": []
    }
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            timezone_id="UTC"
        )
        page = await context.new_page()

        async def _route_handler(route):
            if route.request.resource_type == "image":
                await route.abort()
                return
            await route.continue_()

        await page.route("**/*", _route_handler)

        try:
            await page.goto("https://animeschedule.net/", wait_until="domcontentloaded")
            await page.wait_for_selector("h1.timetable-column-date, .timetable-column-show", timeout=15000)

            parsed_schedule = await page.evaluate(
                """() => {
                    const normalizeUrl = (value) => {
                        if (!value) return null;
                        if (value.startsWith("//")) return `https:${value}`;
                        if (value.startsWith("http")) return value;
                        return new URL(value, "https://animeschedule.net/").href;
                    };

                    const weekdayKeys = {
                        monday: "monday",
                        tuesday: "tuesday",
                        wednesday: "wednesday",
                        thursday: "thursday",
                        friday: "friday",
                        saturday: "saturday",
                        sunday: "sunday",
                    };

                    const emptySchedule = {
                        monday: [],
                        tuesday: [],
                        wednesday: [],
                        thursday: [],
                        friday: [],
                        saturday: [],
                        sunday: [],
                    };

                    const dayHeaders = Array.from(document.querySelectorAll("h1.timetable-column-date"));
                    for (const header of dayHeaders) {
                        const headerLines = (header.innerText || "")
                            .split(/\\n+/)
                            .map((line) => line.trim())
                            .filter(Boolean);
                        const weekday = (headerLines[headerLines.length - 1] || "").toLowerCase();
                        const dayKey = weekdayKeys[weekday];
                        if (!dayKey) continue;

                        let node = header.nextElementSibling;
                        while (node && !(node.matches && node.matches("h1.timetable-column-date"))) {
                            if (node.classList && node.classList.contains("timetable-column-show")) {
                                const title = node.querySelector(".show-title-bar")?.textContent?.trim() || "";
                                const episode = node.querySelector(".show-episode")?.textContent?.trim() || "";
                                const timeEl = node.querySelector(".show-air-time");
                                const airTypeEl = node.querySelector(".air-type-text");
                                const posterEl = node.querySelector(".show-poster");
                                const linkEl = node.querySelector("a.show-link");

                                const displayTime = timeEl?.textContent?.trim() || "";
                                const airType = airTypeEl?.textContent?.trim() || "";
                                const combinedDisplayTime = [displayTime, airType].filter(Boolean).join(" ");

                                emptySchedule[dayKey].push({
                                    title,
                                    episode,
                                    airing_at: timeEl?.getAttribute("datetime") || "",
                                    display_time: combinedDisplayTime || displayTime,
                                    image_url: "",
                                    show_id: node.getAttribute("showid") || node.getAttribute("route") || "",
                                    route: node.getAttribute("route") || "",
                                    air_type: airType,
                                    status: Array.from(node.classList).find((cls) =>
                                        ["aired", "airing", "unaired"].includes(cls)
                                    ) || "",
                                    episodes: node.getAttribute("episodes") || "",
                                    popularity: node.getAttribute("popularity") || "",
                                    media_type: node.getAttribute("mediatype") || "",
                                    anime_url: normalizeUrl(linkEl?.getAttribute("href")) || "",
                                    date_label: headerLines.join(" "),
                                    is_filtered_out: node.classList.contains("filtered-out"),
                                });
                            }
                            node = node.nextElementSibling;
                        }
                    }

                    return emptySchedule;
                }"""
            )

            for day_name, shows in parsed_schedule.items():
                schedule_data[day_name] = shows
                _log(f"[Schedule] Parsed {day_name}: {len(shows)} shows")

            _log("[Schedule] Scraping completed successfully")
        except Exception as e:
            _log(f"[Schedule] Global error: {e}")
        finally:
            await browser.close()

    return schedule_data

# Re-implementing a simple search CLI for manual testing
async def main():
    import sys
    import json
    if len(sys.argv) < 2:
        _log("Usage: python scraper.py <animepahe|latest|reanime_latest> [params]")
        return

    action = sys.argv[1]
    if action == "animepahe":
        title = sys.argv[2] if len(sys.argv) > 2 else "Bleach"
        res = await animepahe_search(title)
        print(json.dumps(res))
    elif action == "latest":
        res = await scrape_animepahe_latest()
        print(json.dumps(res))
    elif action == "reanime_latest":
        res = await scrape_reanime_latest()
        print(json.dumps(res))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
