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
import re
from urllib.parse import quote_plus

# Ensure Playwright uses a project-local browser cache on Render
_playwright_cache = os.path.join(os.path.dirname(__file__), ".playwright")
if os.path.exists(_playwright_cache):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", _playwright_cache)

# Signal to scraper.py that we're running as a subprocess
# This makes scraper.py redirect print() to stderr
os.environ["SCRAPER_SUBPROCESS"] = "1"

# Fix for Windows
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def log(msg: str):
    """Log to stderr so stdout stays clean for JSON output."""
    print(msg, file=sys.stderr)


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
        result = await asyncio.to_thread(
            scrape_animepahe_episode_sync,
            params["title"],
            params["episode_number"],
            params.get("session_id"),
            params.get("offset", 0)
        )
        return result

    elif action == "animepahe_catalog":
        result = await asyncio.to_thread(
            scrape_animepahe_catalog_sync,
            params["title"],
            params.get("session_id"),
            params.get("offset", 0)
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

    else:
        log(f"Unknown action: {action}")
        return None


# ── Re:ANIME actions ──────────────────────────────────────────

async def reanime_search(title: str, target_anilist_id: int = None) -> dict | None:
    """Search Re:ANIME for an anime title and optionally verify AniList ID."""
    from playwright.async_api import async_playwright

    log(f"[Re:ANIME] Searching for: {title} (Target AniList: {target_anilist_id})")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720}
        )
        page = await context.new_page()
        try:
            await page.goto("https://reanime.to/", wait_until="domcontentloaded", timeout=30000)

            # Try to find any search trigger
            try:
                await page.click("button:has-text('Search')", timeout=5000)
            except:
                # Fallback: try to find the input directly if it's already there
                pass

            # Type query with delay
            search_input = "input[placeholder*='Search']"
            await page.wait_for_selector(search_input, timeout=10000)
            await page.click(search_input)
            await page.keyboard.type(title, delay=100)
            await page.keyboard.press("Enter")

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
    """Scrape the FlixCloud embed URL from a Re:ANIME watch page."""
    from playwright.async_api import async_playwright

    watch_url = f"https://reanime.to/watch/{slug}?ep={episode_number}"
    log(f"[Re:ANIME] Starting scrape for Ep {episode_number}: {watch_url}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            # Use 'load' instead of 'domcontentloaded' for heavy dynamic sites
            await page.goto(watch_url, wait_until="load", timeout=60000)
            
            # Re:ANIME has a loading sequence. Wait for the player to be injected.
            iframe_selector = "iframe#video-player, iframe[src*='flixcloud.cc']"
            
            log(f"[Re:ANIME] Waiting for player to be injected and synced...")
            try:
                # Wait up to 30s for the iframe to have a valid src
                # Re:ANIME sometimes injects the iframe with no src first, then populates it.
                await page.wait_for_function(
                    """() => {
                        const ifr = document.querySelector('iframe#video-player') || document.querySelector('iframe[src*="flixcloud.cc"]');
                        return ifr && ifr.src && ifr.src !== '' && !ifr.src.includes(window.location.host);
                    }""",
                    timeout=35000
                )
                
                iframe = await page.query_selector(iframe_selector)
                embed_url = await iframe.get_attribute("src")
                
                if embed_url:
                    log(f"[Re:ANIME] Found FlixCloud embed: {embed_url}")
                    
                    # Extract available episodes while we're here
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
                    log(f"[Re:ANIME] Iframe found but has no src attribute after waiting")
            except Exception as e:
                log(f"[Re:ANIME] Player src population timeout or error: {e}")
                
                # Debug: Log what's actually on the page
                if await page.query_selector("div:has-text('Loading')"):
                    log(f"[Re:ANIME] Page stuck on 'Loading' state")
                elif await page.query_selector("div:has-text('Syncing')"):
                    log(f"[Re:ANIME] Page stuck on 'Syncing' state")
                
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
        browser = p.chromium.launch(headless=True)
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
        browser = p.chromium.launch(headless=True)
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
    """Resolve the kwik embed URL using async Playwright."""
    from playwright.async_api import async_playwright

    play_url = f"{ANIMEPAHE_BASE}/play/{session}/{episode_session}"
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
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

    request_candidates: list[str] = []
    response_candidates: list[str] = []

    def push_candidate(candidate: str | None):
        if not candidate:
            return
        lower = candidate.lower()
        if ".m3u8" in lower or ".mp4" in lower:
            request_candidates.append(candidate)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
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

if __name__ == "__main__":
    log("DEBUG: Scraper starting")
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: python scraper_runner.py <action> <json_params>"}))
        sys.exit(1)

    action = sys.argv[1]
    params = json.loads(sys.argv[2])

    result = asyncio.run(run_action(action, params))

    # Print JSON result to stdout (this is what the backend parses)
    print(json.dumps(result if result else {}))
