# AniVerse Streaming Improvements

## Already Implemented

- AnimePahe catalog freshness tracking is implemented in `backend/services/animepahe_service.py`.
- The backend now stores these fields in `provider_mappings`:
  - `last_catalog_check_at`
  - `latest_episode`
- Automatic refresh logic is implemented in `backend/routers/streaming.py`.
- The backend now refreshes AnimePahe metadata when:
  - the cached catalog is stale
  - the user requests an episode higher than the latest known episode

This means the backend can now detect cases like:
- "we only know up to episode 5"
- "the user asked for episode 6"
- "refresh AnimePahe catalog again"

## Not Implemented Yet

- A true release schedule feature
- Scheduled background jobs that proactively recheck airing anime on a timer
- UI that shows `next episode drops on ...`

## Recommended Next Improvements

### 1. Show Catalog Status In The Watch Page

Add visible stream metadata such as:
- latest known episode
- last checked time
- refreshing state

This makes the backend freshness logic visible to users.

### 2. Add A Manual Catalog Refresh Endpoint

Example:

```text
POST /api/v1/stream/refresh/{mal_id}
```

This is useful for:
- admin repair
- testing
- manually forcing a refresh when needed

### 3. Add A Background Scheduler For Airing Anime

Recheck active airing shows every few hours.

Important:
- refresh metadata first
- do not resolve every stream immediately

Possible implementations:
- `APScheduler` inside the backend for simple setups
- a separate worker service for a more production-ready architecture

### 4. Track Airing / Completed Status Per Mapping

Suggested fields:
- `provider_status`
- `is_airing`

Then:
- airing anime can be checked frequently
- completed anime can be checked rarely or only on demand

### 5. Add Smarter Stale Rules

Suggested rules:
- airing anime: refresh every 3 to 6 hours
- finished anime: refresh every few days or only when requested

### 6. Add Request Deduping Or Locking

Prevent multiple users from triggering the same AnimePahe refresh at the same time.

Possible solutions:
- DB-based lock
- in-memory task registry

### 7. Add Scraper Telemetry

Store fields like:
- `last_scrape_error`
- `last_scrape_duration_ms`
- `last_success_at`

This will make debugging production scraper issues much easier.

## Schedule Feature Recommendation

I do not recommend scraping AnimePahe for episode drop schedule as the first source.

### Better Schedule Sources

#### 1. AniList

Best first choice for:
- airing metadata
- next episode metadata
- schedule timing

Advantages:
- cleaner
- more stable
- easier to maintain than scraper-based schedule logic

#### 2. Jikan / MAL-Derived Metadata

Usable as a fallback.

Less ideal than AniList for next-episode timing, but still better than relying on a provider scraper.

#### 3. Scraping Provider Pages

Use only as a last resort.

Disadvantages:
- fragile
- high maintenance
- poor long-term reliability

## Best Plan For The Schedule Feature

1. Add schedule fields in MongoDB
2. Fetch next airing metadata from AniList
3. Show countdown in the UI
4. After the airing time passes, refresh AnimePahe catalog automatically

Suggested UI example:

```text
Episode 6 airs in 2d 4h
```

Suggested responsibility split:
- AniList tells us when an episode should air
- AnimePahe tells us when the stream is actually available

## Deployment Assessment

### Current Stack

- Frontend: Vercel
- Backend: Render Free Tier

### Frontend On Vercel

This is fine for now.

### Backend On Render Free

This is okay for demo use, but not ideal for public launch.

Main reasons:
- free instances spin down on idle
- cold starts will hurt the watch flow
- Playwright scraping is resource heavy
- scraper jobs are slow compared to normal API requests
- background refreshes can be interrupted or delayed

## GitHub Education Pack Hosting Options

The GitHub Student Developer Pack can be a much better path than relying on Render Free for this project.

### Strong Options Found

#### 1. DigitalOcean

Offer observed:

```text
$200 in platform credit for 1 year
```

Why this is a strong fit:
- simple VPS-style deployment
- full backend control
- much better for FastAPI + Playwright than tiny free-tier web services
- easier to reason about than serverless-style platforms for browser automation

Recommended use:
- keep frontend on Vercel
- run backend + scraper on one DigitalOcean droplet
- keep MongoDB external

Best near-term shape:
- Vercel: frontend
- DigitalOcean droplet: FastAPI + Playwright
- MongoDB: external database

This is the recommended student-credit option for this project.

#### 2. Microsoft Azure

Offer observed:

```text
Free access to 25+ Microsoft Azure cloud services plus $100 in Azure credit
```

Why it is useful:
- solid student cloud option
- enough for backend experiments and small deployments
- better than Render Free for this workload

Tradeoff:
- more setup friction than DigitalOcean for this specific stack

Azure is a good second choice, especially if the student offer is easy for you to activate.

#### 3. Domain Offers

Name.com / Namecheap offers are useful for:
- custom domains
- branding

They are not backend hosting solutions.

## Recommended Hosting Choice From The Pack

### Best Choice

`DigitalOcean`

Why:
- easiest path for this exact project
- better fit for Playwright
- easier deployment story than Azure for a single backend VM
- stronger option than Render Free for public use

### Second Choice

`Azure`

Why:
- still strong
- more infrastructure options
- but likely more setup work

## Suggested Architecture Using Student Benefits

### Best Low-Cost / Student-Credit Setup

- Frontend: Vercel
- Backend + scraper: DigitalOcean droplet
- Database: MongoDB

### Short-Term Deployment Shape

Run:
- FastAPI API
- Playwright scraper

on the same VM first.

### Later Upgrade Path

Split into:
- API service
- scraper worker
- scheduler worker

## Practical Recommendation

If launching without personal monthly spending right now:

1. Keep the frontend on Vercel
2. Move the backend off Render Free
3. Use GitHub Education Pack credits
4. Prefer DigitalOcean first
5. Use Azure if DigitalOcean is not convenient

## Hosting Option Ranking

1. DigitalOcean
2. Azure
3. Oracle Cloud Always Free
4. Render Free for demo/testing only

## Why These Are Better Than Render Free

- more usable compute
- less constrained than tiny free web services
- better chance of stable Playwright execution
- fewer cold start problems
- better path toward a public release

## Better Deployment Path

### Short Term

1. Keep frontend on Vercel
2. Move backend to an always-on paid instance
3. Keep MongoDB external

### Longer Term

Split responsibilities into:
- API service
- scraper worker service
- scheduler / refresh worker

## Best Production Improvements

### 1. Separate Scraping From The Web API

The API should queue jobs.

A worker should run Playwright.

### 2. Add Retry Queue Logic

Failed provider refreshes should retry safely.

### 3. Add Cache TTLs Across The App

Examples:
- anime detail cache
- recommendation cache
- provider mapping cache
- episode catalog cache

### 4. Add Rate Limiting

Especially for:

```text
/stream/{mal_id}/{ep}
```

### 5. Add Monitoring And Structured Logging

At minimum log:
- request start
- scrape start
- scrape end
- scrape error
- latest episode found

### 6. Add Manual Provider Override Tooling

This is better than hardcoding future mapping fixes in source code.

### 7. Add Health / Admin Endpoints

Examples:
- recommendation engine readiness
- scraper runner status
- latest refresh stats

## Recommended Order Of Work

1. Show latest episode and last checked time in the watch UI
2. Add AniList-based schedule source
3. Add periodic catalog refresh job
4. Add job deduping / locking
5. Upgrade backend hosting before public launch
6. Later split scraper into a worker service

## Best Immediate Next Step

If continuing right away, the strongest next tasks would be one of:
- show `latest episode / last checked` in the watch page
- add AniList-based schedule storage and API


I have thoroughly reviewed the **Antigravity** internal skills (Clean Code, Performance Profiling, Backend Architect, Security Auditor) and the project's codebase.

The current system is functional but faces architectural challenges: **heavy scraping logic is tightly coupled with the API request cycle**, and **security/performance controls are minimal**.

I have updated `suggestions.md` with a comprehensive roadmap to evolve **AniVerse** from a high-quality prototype into a production-ready, secure, and high-performance streaming engine.

### Key Improvements Added to `suggestions.md`

#### 1. Performance & Scalability
*   **Asynchronous Worker Pattern**: Decouple Playwright scraping from the main FastAPI process using a task queue (like `Celery` or `BullMQ`) to prevent API timeouts.
*   **Multi-Layer Caching**: Implement Redis-based distributed caching for provider mappings and episode catalogs to eliminate redundant scraping.
*   **Request Deduping**: Implement a "Single Flight" or locking mechanism to prevent multiple simultaneous scrapes for the same anime when a new episode drops.

#### 2. Security & Reliability
*   **Admin Override Dashboard**: Instead of manual script fixes (like `fix_mapping.py`), build a protected UI for administrators to manually override MAL-to-Provider ID mappings.
*   **Scraper Isolation & Rate Limiting**: Move scrapers to dedicated instances and implement rate limiting on sensitive streaming endpoints to prevent abuse.
*   **Audit Logging**: Implement structured JSON logging to track scraper performance, errors, and mapping health.

#### 3. Advanced Features
*   **AniList-Driven Scheduling**: Proactively refresh catalog data based on real AniList air dates rather than scraping on-demand.
*   **Vibe Search Refactoring**: Transition from simple keyword matching to a vector-based similarity search for "Vibes" using embeddings.

### Recommended Next Steps
1.  **UI Feedback**: Display "Latest Known Episode" and "Last Checked Time" on the Watch Page to make backend freshness logic visible to users.
2.  **Manual Refresh API**: Create a protected `POST /refresh/{mal_id}` endpoint for forced updates.
3.  **Hosting Migration**: Prepare for DigitalOcean deployment to move off the Render free tier and its cold-start limitations.

You can view the full detailed roadmap in [suggestions.md](file:///c:/Users/Lenovo/Desktop/Project%20Based%20Learning%20Python/Anime%20Discovery%20Engine/suggestions.md).