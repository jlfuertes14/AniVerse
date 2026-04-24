"""
Anime Discovery Engine — Pydantic Schemas
Unified response models for API data normalization.
"""
from pydantic import BaseModel
from typing import Optional


class AnimeResult(BaseModel):
    """Unified anime result from Jikan or AniList."""
    id: int
    mal_id: Optional[int] = None
    anilist_id: Optional[int] = None
    title: str
    title_english: Optional[str] = None
    title_japanese: Optional[str] = None
    image_url: str
    large_image_url: Optional[str] = None
    synopsis: Optional[str] = None
    score: Optional[float] = None
    episodes: Optional[int] = None
    status: Optional[str] = None
    rating: Optional[str] = None
    year: Optional[int] = None
    season: Optional[str] = None
    type: Optional[str] = None  # TV, Movie, OVA, etc.
    genres: list[str] = []
    studios: list[str] = []
    source: str = "jikan"  # "jikan" or "anilist"


class AnimeDetail(AnimeResult):
    """Extended anime details."""
    trailer_url: Optional[str] = None
    duration: Optional[str] = None
    aired: Optional[str] = None
    rank: Optional[int] = None
    popularity: Optional[int] = None
    members: Optional[int] = None
    background: Optional[str] = None
    related: list["AnimeResult"] = []
    recommendations: list["AnimeResult"] = []
    characters: list[dict] = []
    banner_image: Optional[str] = None


class ScreenshotResult(BaseModel):
    """Result from trace.moe screenshot search."""
    anilist_id: Optional[int] = None
    mal_id: Optional[int] = None
    title: Optional[str] = None
    title_english: Optional[str] = None
    episode: Optional[int] = None
    timestamp_from: Optional[float] = None
    timestamp_to: Optional[float] = None
    similarity: float
    image_url: Optional[str] = None
    video_url: Optional[str] = None


class VibePreset(BaseModel):
    """A vibe preset configuration."""
    id: str
    name: str
    emoji: str
    description: str
    genres: list[str] = []
    tags: list[str] = []
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    studios: list[str] = []
    demographic: Optional[str] = None


class SearchParams(BaseModel):
    """Search parameters for anime discovery."""
    query: Optional[str] = None
    vibe: Optional[str] = None
    genres: list[str] = []
    studios: list[str] = []
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    rating: Optional[str] = None
    status: Optional[str] = None
    sort: Optional[str] = "score"
    page: int = 1
    limit: int = 24


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""
    data: list[AnimeResult]
    total: int = 0
    page: int = 1
    has_next: bool = False
