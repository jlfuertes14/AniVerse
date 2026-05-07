"""
Anime Discovery Engine — FastAPI Backend
Main application entry point.
"""
import asyncio
import os
import sys
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Fix for Windows: Playwright (and subprocesses) require ProactorEventLoop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

load_dotenv()  # Load .env before anything else

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import anime, screenshot, filters, ai, auth, user, comments, streaming, banners, proxy
from backend.services import animepahe_service, recommendation_engine, schedule_service
from backend.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and build recommendation model on startup."""
    await init_db()
    print("[AI] Building recommendation model in background...")
    recommendation_task = asyncio.create_task(recommendation_engine.build_model(count=200))
    scheduler_task = asyncio.create_task(animepahe_service.animepahe_catalog_scheduler())
    latest_releases_task = asyncio.create_task(animepahe_service.latest_releases_scheduler())
    schedule_task = asyncio.create_task(schedule_service.schedule_scheduler())
    yield
    recommendation_task.cancel()
    scheduler_task.cancel()
    latest_releases_task.cancel()
    schedule_task.cancel()
    print("[AI] Shutting down.")


app = FastAPI(
    title="Anime Discovery Engine API",
    description="Find anime by vibe, not just genre. Powered by Jikan, AniList, trace.moe, and Gemini AI.",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(anime.router, prefix="/api/v1")
app.include_router(screenshot.router, prefix="/api/v1")
app.include_router(filters.router, prefix="/api/v1")
app.include_router(ai.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(user.router, prefix="/api/v1")
app.include_router(comments.router, prefix="/api/v1")
app.include_router(streaming.router, prefix="/api/v1")
app.include_router(banners.router, prefix="/api/v1")
app.include_router(proxy.router, prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "name": "Anime Discovery Engine API",
        "version": "2.0.0",
        "docs": "/docs",
        "endpoints": {
            "search": "/api/v1/anime/search",
            "trending": "/api/v1/anime/trending",
            "top": "/api/v1/anime/top",
            "spotlight": "/api/v1/anime/spotlight",
            "vibes": "/api/v1/anime/vibes",
            "screenshot_search": "/api/v1/screenshot/search",
            "genres": "/api/v1/filters/genres",
            "studios": "/api/v1/filters/studios",
            "ai_search": "/api/v1/ai/search",
            "ai_similar": "/api/v1/ai/similar/{anime_id}",
            "ai_status": "/api/v1/ai/status",
            "stream": "/api/v1/stream/{mal_id}/{ep_number}",
        },
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "ai_ready": recommendation_engine.is_ready(),
    }

