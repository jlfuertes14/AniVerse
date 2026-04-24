"""
Anime Discovery Engine — Content-Based Recommendation Engine
Uses TF-IDF + Cosine Similarity on anime synopses and metadata.
"""
import asyncio
from typing import Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from backend.services import anilist_service
from backend.cache import metadata_cache, get_cache_key
from backend.models.schemas import AnimeResult

# In-memory model state
_corpus: list[dict] = []
_tfidf_matrix = None
_vectorizer: Optional[TfidfVectorizer] = None
_anime_ids: list[int] = []
_is_building = False
_is_ready = False


def _build_feature_text(anime: dict) -> str:
    """Combine synopsis, genres, tags, and studios into a single feature string."""
    parts = []

    synopsis = anime.get("synopsis") or ""
    # Strip HTML tags
    import re
    synopsis = re.sub(r"<[^>]*>", "", synopsis)
    parts.append(synopsis)

    # Add genres multiple times to boost their weight
    genres = anime.get("genres", [])
    if isinstance(genres, list):
        parts.append(" ".join(genres) * 3)

    # Add tags
    tags = anime.get("tags", [])
    if isinstance(tags, list):
        parts.append(" ".join(tags) * 2)

    # Add studios
    studios = anime.get("studios", [])
    if isinstance(studios, list):
        parts.append(" ".join(studios))

    # Add type and season
    if anime.get("type"):
        parts.append(anime["type"])
    if anime.get("season"):
        parts.append(anime["season"])

    return " ".join(parts).strip()


async def build_model(count: int = 200):
    """Fetch trending/popular anime and build the TF-IDF model."""
    global _corpus, _tfidf_matrix, _vectorizer, _anime_ids, _is_building, _is_ready

    if _is_building:
        return
    _is_building = True

    try:
        # Fetch anime data from AniList (multiple pages)
        all_anime = []
        for page in range(1, (count // 50) + 2):
            try:
                result = await anilist_service.get_trending(page=page, per_page=50)
                data = result.get("data", [])
                if not data:
                    break
                for anime in data:
                    if isinstance(anime, AnimeResult):
                        all_anime.append({
                            "id": anime.anilist_id or anime.id,
                            "title": anime.title,
                            "title_english": anime.title_english,
                            "synopsis": anime.synopsis,
                            "genres": anime.genres,
                            "studios": anime.studios,
                            "type": anime.type,
                            "season": anime.season,
                            "score": anime.score,
                            "image_url": anime.image_url,
                            "large_image_url": anime.large_image_url,
                            "episodes": anime.episodes,
                            "year": anime.year,
                            "status": anime.status,
                            "tags": [],
                        })
                    elif isinstance(anime, dict):
                        all_anime.append(anime)
            except Exception:
                break

        if len(all_anime) < 10:
            _is_building = False
            return

        _corpus = all_anime
        _anime_ids = [a.get("id", 0) for a in all_anime]

        # Build TF-IDF matrix
        texts = [_build_feature_text(a) for a in all_anime]
        _vectorizer = TfidfVectorizer(
            max_features=5000,
            stop_words="english",
            ngram_range=(1, 2),
        )
        _tfidf_matrix = _vectorizer.fit_transform(texts)
        _is_ready = True

    except Exception as e:
        print(f"[RecEngine] Build failed: {e}")
    finally:
        _is_building = False


def get_similar(anime_id: int, top_n: int = 10) -> list[dict]:
    """Find anime similar to the given ID using cosine similarity."""
    if not _is_ready or _tfidf_matrix is None:
        return []

    if anime_id not in _anime_ids:
        return []

    idx = _anime_ids.index(anime_id)
    sim_scores = cosine_similarity(_tfidf_matrix[idx:idx+1], _tfidf_matrix).flatten()

    # Get top N (excluding itself)
    similar_indices = np.argsort(sim_scores)[::-1][1:top_n + 1]

    results = []
    for i in similar_indices:
        if sim_scores[i] > 0.05:  # Minimum similarity threshold
            anime = _corpus[i].copy()
            anime["similarity_score"] = round(float(sim_scores[i]) * 100, 1)
            results.append(anime)

    return results


def search_by_text(query_text: str, top_n: int = 15) -> list[dict]:
    """Search the corpus using TF-IDF text similarity (for AI-generated descriptions)."""
    if not _is_ready or _vectorizer is None or _tfidf_matrix is None:
        return []

    query_vec = _vectorizer.transform([query_text])
    sim_scores = cosine_similarity(query_vec, _tfidf_matrix).flatten()

    top_indices = np.argsort(sim_scores)[::-1][:top_n]

    results = []
    for i in top_indices:
        if sim_scores[i] > 0.02:
            anime = _corpus[i].copy()
            anime["relevance_score"] = round(float(sim_scores[i]) * 100, 1)
            results.append(anime)

    return results


def is_ready() -> bool:
    """Check if the recommendation model is loaded."""
    return _is_ready


def corpus_size() -> int:
    """Return the number of anime in the model."""
    return len(_corpus)
