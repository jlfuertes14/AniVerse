"""
Scraper Runner -- Subprocess entry point for Playwright-based scraping.

This script is called by the backend services via subprocess.run().
It runs with its own asyncio event loop (ProactorEventLoop on Windows),
completely isolated from Uvicorn's SelectorEventLoop.

Usage:
    python scraper_runner.py <action> <json_params>

Actions:
    anizone_search   {"title": "..."}
    anizone_scrape   {"url": "..."}
    animepahe_full   {"title": "...", "max_episodes": 0}
    animepahe_stream {"session": "...", "episode_session": "..."}

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


async def run_action(action: str, params: dict):
    """Dispatch to the appropriate scraper function."""

    if action == "anizone_search":
        return await anizone_search(params["title"])

    elif action == "anizone_scrape":
        return await anizone_scrape(params["url"])

    elif action == "anizone_episode":
        return await anizone_scrape_episode(params["url"], params["episode_number"])

    elif action == "animepahe_full":
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

    elif action == "anime_schedule":
        from scraper import scrape_anime_schedule
        return await scrape_anime_schedule()

    else:
        log(f"Unknown action: {action}")
        return None


# ── AniZone actions ──────────────────────────────────────────

async def anizone_search(title: str) -> dict | None:
    """Search AniZone for an anime title."""
    from playwright.async_api import async_playwright

    log(f"[AniZone] Searching for: {title}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        try:
            # Correct search URL for AniZone (URL-encode to support Japanese titles)
            search_url = f"https://anizone.to/anime?search={quote_plus(title)}"
            await page.goto(search_url, wait_until="networkidle", timeout=15000)

            # Look for any link containing '/anime/'
            result_selector = "a[href*='/anime/']"
            await page.wait_for_selector(result_selector, timeout=10000)

            # Get all results and find the best match
            results = await page.locator(result_selector).all()
            best_url = None
            search_title_lower = title.lower()
            
            for res in results:
                href = await res.get_attribute("href")
                if not href or "/anime/" not in href or href.endswith("/anime"):
                    continue
                
                # Try to get the title from the link or its parent/child
                link_text = await res.inner_text()
                if not link_text:
                    # Look for a title nearby
                    link_text = await res.locator("xpath=..").inner_text()
                
                res_title = link_text.lower()
                full_url = href if href.startswith("http") else f"https://anizone.to{href}"
                
                if search_title_lower in res_title or res_title in search_title_lower:
                    log(f"[AniZone] Match found: {link_text} -> {full_url}")
                    return {"url": full_url}
                
                if not best_url:
                    best_url = full_url
            
            if best_url:
                log(f"[AniZone] Fallback to first result: {best_url}")
                return {"url": best_url}
        except Exception as e:
            log(f"[AniZone] Search error: {e}")
        finally:
            await browser.close()
    return None


async def anizone_scrape(url: str) -> dict | None:
    """Scrape HLS links from an AniZone anime page."""
    from playwright.async_api import async_playwright

    log(f"[AniZone] Scraping: {url}")
    episodes_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Extract slug from URL: https://anizone.to/anime/ul5zmckr
            slug = url.strip('/').split('/')[-1]
            # Selector for episodes is links containing the slug followed by a slash
            episode_selector = f"a[href*='/anime/{slug}/']"
            
            # Infinite scroll: scroll down to load episodes
            log(f"[AniZone] Scrolling to load episodes for {slug}...")
            for i in range(3): # Reduced from 5 to 3
                await page.evaluate("window.scrollBy(0, 3000)")
                await page.wait_for_timeout(500) # Reduced from 1000 to 500

            try:
                await page.wait_for_selector(episode_selector, timeout=10000)
            except:
                log(f"[AniZone] No episodes found with selector {episode_selector} at {url}")
                return {"episodes": []}

            # Use a broad selector and filter in Python (more reliable)
            links = await page.locator("a").all()
            episode_targets = []
            seen_urls = set()
            
            for el in links:
                href = await el.get_attribute("href")
                if not href or href in seen_urls:
                    continue
                
                # Check if it's an episode link: contains /anime/slug/
                if f"/anime/{slug}/" in href:
                    seen_urls.add(href)
                    full_href = href if href.startswith("http") else f"https://anizone.to{href}"
                    # Episode number is the last part
                    ep_num = full_href.strip('/').split('/')[-1]
                    if ep_num.isdigit():
                        episode_targets.append({"number": ep_num, "url": full_href})

            log(f"[AniZone] Found {len(episode_targets)} episodes")

            for target in episode_targets:
                log(f"[AniZone] Extracting Ep {target['number']}...")
                await page.goto(target["url"], wait_until="domcontentloaded")

                try:
                    player = await page.wait_for_selector("media-player", timeout=10000)
                    m3u8_url = await player.get_attribute("src")

                    subtitles = []
                    track_elements = await page.locator("media-player track").all()
                    for track in track_elements:
                        kind = await track.get_attribute("kind")
                        if kind in ["subtitles", "captions"]:
                            sub_src = await track.get_attribute("src")
                            sub_label = await track.get_attribute("label")
                            sub_lang = await track.get_attribute("srclang")
                            if sub_src:
                                subtitles.append({
                                    "url": sub_src,
                                    "label": sub_label or "Unknown",
                                    "lang": sub_lang or "en"
                                })

                    if m3u8_url and ".m3u8" in m3u8_url:
                        ep_num = int(target["number"]) if target["number"].isdigit() else target["number"]
                        episodes_data.append({
                            "ep_number": ep_num,
                            "stream_url": m3u8_url,
                            "subtitles": subtitles,
                            "provider": "anizone",
                            "referer_url": target["url"],
                        })
                        log(f"  -> Ep {target['number']}: OK")
                except Exception as e:
                    log(f"  -> Failed Ep {target['number']}: {e}")
                await page.wait_for_timeout(500)

        except Exception as e:
            log(f"[AniZone] Scrape error: {e}")
        finally:
            await browser.close()

    return {"episodes": episodes_data}


async def anizone_scrape_episode(url: str, episode_number: int) -> dict | None:
    """Scrape a single AniZone episode directly from its episode page."""
    from playwright.async_api import async_playwright

    log(f"[AniZone] Scraping single episode {episode_number} from: {url}")
    slug = url.strip("/").split("/")[-1]
    episode_url = f"https://anizone.to/anime/{slug}/{episode_number}"

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await page.goto(episode_url, wait_until="domcontentloaded", timeout=20000)
            player = await page.wait_for_selector("media-player", timeout=10000)
            m3u8_url = await player.get_attribute("src")

            subtitles = []
            track_elements = await page.locator("media-player track").all()
            for track in track_elements:
                kind = await track.get_attribute("kind")
                if kind in ["subtitles", "captions"]:
                    sub_src = await track.get_attribute("src")
                    if sub_src:
                        subtitles.append({
                            "url": sub_src,
                            "label": await track.get_attribute("label") or "Unknown",
                            "lang": await track.get_attribute("srclang") or "en"
                        })

            if m3u8_url and ".m3u8" in m3u8_url:
                return {
                    "episodes": [{
                        "ep_number": int(episode_number),
                        "stream_url": m3u8_url,
                        "subtitles": subtitles,
                        "provider": "anizone",
                        "referer_url": episode_url,
                    }]
                }
        except Exception as e:
            log(f"[AniZone] Single-episode scrape error: {e}")
        finally:
            await browser.close()

    return {"episodes": []}


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
    """
    Warm the browser session for DDoS-Guard protected pages.
    Treat the landing page as a cookie/bootstrap step instead of failing
    the whole scrape if full DOM readiness is slow.
    """
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    try:
        page.goto(ANIMEPAHE_BASE, wait_until="commit", timeout=45000)
    except PlaywrightTimeoutError:
        log("[AnimePahe] Warmup timed out at commit stage; continuing with current session state")

    page.wait_for_timeout(5000)


def _animepahe_json_request(page, url: str, label: str):
    """Fetch a JSON page with a retry-friendly timeout profile."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    last_error = None
    for attempt in range(3):
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
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
                session_id = results[0]["session"]
                result["session"] = session_id

            anime_url = f"{ANIMEPAHE_BASE}/anime/{session_id}"
            page.goto(anime_url, wait_until="domcontentloaded", timeout=30000)

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
            page.goto(play_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
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
            page.goto(anime_url, wait_until="domcontentloaded", timeout=30000)
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
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Usage: python scraper_runner.py <action> <json_params>"}))
        sys.exit(1)

    action = sys.argv[1]
    params = json.loads(sys.argv[2])

    result = asyncio.run(run_action(action, params))

    # Print JSON result to stdout (this is what the backend parses)
    print(json.dumps(result if result else {}))
