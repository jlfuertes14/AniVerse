"""
Anime Discovery Engine — FastAPI Backend
Main application entry point.
"""
import asyncio
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()  # Load .env before anything else

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import anime, screenshot, filters, ai, auth, user, comments
from backend.services import recommendation_engine
from backend.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and build recommendation model on startup."""
    await init_db()
    print("[AI] Building recommendation model in background...")
    asyncio.create_task(recommendation_engine.build_model(count=200))
    yield
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
        },
    }


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "ai_ready": recommendation_engine.is_ready(),
    }

