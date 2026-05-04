import asyncio
import json
import sys
import re
import os

# Ensure Playwright uses a project-local browser cache on Render
_playwright_cache = os.path.join(os.path.dirname(__file__), ".playwright")
os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", _playwright_cache)

from playwright.async_api import async_playwright

# Fix for Windows: Playwright requires ProactorEventLoop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# When called as a subprocess, redirect all prints to stderr
# so stdout stays clean for JSON output
_is_subprocess = os.environ.get("SCRAPER_SUBPROCESS") == "1"

def _log(*args, **kwargs):
    """Print to stderr when running as subprocess, stdout otherwise."""
    if _is_subprocess:
        kwargs["file"] = sys.stderr
    print(*args, **kwargs)


# ═══════════════════════════════════════════════════════════════
#  AniZone Scraper (Playwright — direct HLS extraction)
# ═══════════════════════════════════════════════════════════════

async def scrape_anizone(url: str):
    """Scrapes raw HLS links from AniZone's Vidstack player."""
    _log(f"[AniZone] Starting scraper for: {url}")
    scraped_data = {"anime_url": url, "episodes": [], "provider": "anizone"}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded")
            episode_selector = "a.snap-start"
            await page.wait_for_selector(episode_selector, timeout=15000)

            ep_elements = await page.locator(episode_selector).all()
            episode_targets = []
            for el in ep_elements:
                href = await el.get_attribute("href")
                inner_text = await el.inner_text()
                ep_number = inner_text.split('\n')[0].strip() if '\n' in inner_text else inner_text.strip()
                if href:
                    episode_targets.append({"ep_number": ep_number, "url": href})

            _log(f"[AniZone] Found {len(episode_targets)} episodes")

            for target in episode_targets:
                await page.goto(target["url"], wait_until="domcontentloaded")
                try:
                    player = await page.wait_for_selector("media-player", timeout=10000)
                    m3u8_url = await player.get_attribute("src")

                    subtitles = []
                    track_elements = await page.locator("media-player track").all()
                    for track in track_elements:
                        kind = await track.get_attribute("kind")
                        if kind in ["subtitles", "captions"]:
                            subtitles.append({
                                "url": await track.get_attribute("src"),
                                "label": await track.get_attribute("label"),
                                "lang": await track.get_attribute("srclang")
                            })

                    if m3u8_url and ".m3u8" in m3u8_url:
                        scraped_data["episodes"].append({
                            "ep_number": target["ep_number"],
                            "stream_url": m3u8_url,
                            "subtitles": subtitles
                        })
                        _log(f"  -> Ep {target['ep_number']}: OK")
                except Exception as e:
                    _log(f"  -> Failed Ep {target['ep_number']}: {e}")
                await page.wait_for_timeout(500)
        except Exception as e:
            _log(f"[AniZone] Error: {e}")
        finally:
            await browser.close()
    return scraped_data


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
    Search AnimePahe for an anime title using Playwright to bypass DDoS-Guard.
    Returns dict with 'session' and 'title' keys, or None.
    """
    _log(f"[AnimePahe] Searching for: {title}")
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


async def animepahe_get_episodes(session: str, max_pages: int = 100) -> list:
    """
    Fetch episode list from AnimePahe using the browser-based API.
    Returns list of dicts with 'episode', 'session', 'snapshot' keys.
    """
    _log(f"[AnimePahe] Fetching episodes for session: {session}")
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


async def scrape_animepahe(title: str, max_episodes: int = 0, session_id: str = None):
    """
    Full AnimePahe pipeline: search (if no session_id) → episodes → streams.
    Returns structured data ready for DB insertion.
    
    Args:
        title: Anime title to search for
        max_episodes: Max episodes to resolve streams for (0 = all, just store metadata)
        session_id: Optional session ID to skip search
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
    episodes = await animepahe_get_episodes(session)
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
    """Scrapes the latest releases from the AnimePahe homepage (multi-page)."""
    _log(f"[AnimePahe] Scraping latest releases (up to {pages} pages)")
    latest_releases = []
    seen_sessions = set()

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
    else:
        target_url = sys.argv[2] if len(sys.argv) > 2 else "https://anizone.to/anime/zopo98pd"
        result = asyncio.run(scrape_anizone(target_url))
        print("\n--- SCRAPE COMPLETE ---")
        print(json.dumps(result, indent=4))

# ═══════════════════════════════════════════════════════════════
#  AnimeSchedule.net Scraper
# ═══════════════════════════════════════════════════════════════

async def scrape_anime_schedule():
    """Scrapes the weekly airing schedule from animeschedule.net."""
    _log("[Schedule] Starting scraper for animeschedule.net")
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
