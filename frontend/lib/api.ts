/* ============================================
   Anime Discovery Engine — API Client
   ============================================ */
import type {
    Anime,
    AnimeDetail,
    PaginatedResponse,
    ScreenshotResult,
    VibePreset,
    Genre,
    Studio,
    SearchFilters,
    LatestRelease,
    WeeklySchedule,
} from "./types";
import { getToken } from "./auth";
import type { User } from "./auth";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const token = getToken();
    const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(options?.headers as Record<string, string>),
    };
    if (token) {
        headers["Authorization"] = `Bearer ${token}`;
    }

    const res = await fetch(`${API_BASE}${endpoint}`, {
        ...options,
        headers,
    });

    if (!res.ok) {
        const errorBody = await res.json().catch(() => ({}));
        throw new Error(errorBody.detail || `API Error: ${res.status} ${res.statusText}`);
    }

    return res.json();
}

// ─── Anime Endpoints ────────────────────────────────────

export async function searchAnime(filters: SearchFilters): Promise<PaginatedResponse> {
    const params = new URLSearchParams();
    if (filters.query) params.set("q", filters.query);
    if (filters.vibe) params.set("vibe", filters.vibe);
    if (filters.genres) params.set("genres", filters.genres);
    if (filters.studios) params.set("studios", filters.studios);
    if (filters.year_from) params.set("year_from", String(filters.year_from));
    if (filters.year_to) params.set("year_to", String(filters.year_to));
    if (filters.status) params.set("status", filters.status);
    if (filters.rating) params.set("rating", filters.rating);
    if (filters.type) params.set("type", filters.type);
    if (filters.page) params.set("page", String(filters.page));

    return fetchAPI<PaginatedResponse>(`/anime/search?${params.toString()}`);
}

export async function getTrending(page: number = 1): Promise<PaginatedResponse> {
    return fetchAPI<PaginatedResponse>(`/anime/trending?page=${page}`);
}

export async function getLatestReleases(prefer: string = "animepahe"): Promise<LatestRelease[]> {
    return fetchAPI<LatestRelease[]>(`/anime/latest?prefer=${prefer}`, {
        next: { revalidate: 300 },
    });
}

export async function getAiringSchedule(): Promise<WeeklySchedule> {
    return fetchAPI<WeeklySchedule>("/anime/schedule", {
        next: { revalidate: 43200 }, // 12 hours
    });
}

export async function getTopAnime(page: number = 1, filter?: string): Promise<PaginatedResponse> {
    const params = new URLSearchParams({ page: String(page) });
    if (filter) params.set("filter", filter);
    return fetchAPI<PaginatedResponse>(`/anime/top?${params.toString()}`);
}

export async function getSpotlight(): Promise<Anime[]> {
    return fetchAPI<Anime[]>("/anime/spotlight");
}

export async function getVibes(): Promise<VibePreset[]> {
    return fetchAPI<VibePreset[]>("/anime/vibes");
}

export async function getRandomAnime(): Promise<Anime> {
    return fetchAPI<Anime>("/anime/random");
}

export async function getSeasonalAnime(
    year: number,
    season: string,
    page: number = 1
): Promise<PaginatedResponse> {
    return fetchAPI<PaginatedResponse>(`/anime/seasonal/${year}/${season}?page=${page}`);
}

export async function getAnimeDetail(
    id: number,
    source: string = "anilist"
): Promise<AnimeDetail> {
    return fetchAPI<AnimeDetail>(`/anime/${id}?source=${source}`);
}

// ─── Screenshot Endpoints ───────────────────────────────

export async function searchByScreenshot(file: File): Promise<{ results: ScreenshotResult[] }> {
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch(`${API_BASE}/screenshot/search`, {
        method: "POST",
        body: formData,
    });

    if (!res.ok) throw new Error(`Screenshot search failed: ${res.status}`);
    return res.json();
}

export async function searchByScreenshotUrl(url: string): Promise<{ results: ScreenshotResult[] }> {
    const res = await fetch(`${API_BASE}/screenshot/search?url=${encodeURIComponent(url)}`, {
        method: "POST",
    });
    if (!res.ok) throw new Error(`Screenshot search failed: ${res.status}`);
    return res.json();
}

// ─── Filter Endpoints ───────────────────────────────────

export async function getGenres(): Promise<Genre[]> {
    return fetchAPI<Genre[]>("/filters/genres");
}

export async function getStudios(): Promise<Studio[]> {
    return fetchAPI<Studio[]>("/filters/studios");
}

// ─── AI Endpoints ───────────────────────────────────────

export interface AISearchResponse {
    filters: {
        genres?: string[];
        tags?: string[];
        mood?: string;
        year_from?: number;
        year_to?: number;
        studios?: string[];
        description?: string;
    } | null;
    raw_query: string;
    results: Anime[];
    total: number;
    error?: string;
}

export async function aiSearch(query: string): Promise<AISearchResponse> {
    return fetchAPI<AISearchResponse>("/ai/search", {
        method: "POST",
        body: JSON.stringify({ query }),
    });
}

export async function getSimilarAnime(animeId: number, count: number = 10): Promise<{ results: Anime[]; model_ready: boolean }> {
    return fetchAPI<{ results: Anime[]; model_ready: boolean }>(`/ai/similar/${animeId}?count=${count}`);
}

export async function getAIStatus(): Promise<{ nlp_search: boolean; recommendation_engine: boolean; corpus_size: number }> {
    return fetchAPI<{ nlp_search: boolean; recommendation_engine: boolean; corpus_size: number }>("/ai/status");
}

export async function getBanners(): Promise<string[]> {
    return fetchAPI<string[]>("/banners");
}

// ─── Auth Endpoints ─────────────────────────────────────

export async function registerUser(username: string, email: string, password: string): Promise<{ token: string; user: User }> {
    return fetchAPI<{ token: string; user: User }>("/auth/register", {
        method: "POST",
        body: JSON.stringify({ username, email, password }),
    });
}

export async function loginUser(email: string, password: string): Promise<{ token: string; user: User }> {
    return fetchAPI<{ token: string; user: User }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password }),
    });
}

export async function getMe(): Promise<User> {
    return fetchAPI<User>("/auth/me");
}

export async function updateMe(payload: { username: string; email: string }): Promise<User> {
    return fetchAPI<User>("/auth/me", {
        method: "PUT",
        body: JSON.stringify(payload),
    });
}

export async function uploadAvatar(file: File): Promise<{ avatar_url: string }> {
    const token = getToken();
    const formData = new FormData();
    formData.append("file", file);

    const res = await fetch(`${API_BASE}/auth/avatar`, {
        method: "PUT",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
    });

    if (!res.ok) {
        const errorBody = await res.json().catch(() => ({}));
        throw new Error(errorBody.detail || `Upload failed: ${res.status}`);
    }
    return res.json();
}

// ─── User Endpoints ─────────────────────────────────────

export interface WatchlistItem {
    id: string;
    user_id: string;
    anime_id: number;
    anime_title: string;
    anime_image: string;
    status: string;
    added_at: string;
}

export interface Comment {
    id: string;
    anime_id: number;
    content: string;
    created_at: string;
    updated_at: string;
    user: { id: string; username: string; avatar_url: string | null };
}

export async function getWatchlist(status?: string): Promise<WatchlistItem[]> {
    const params = status ? `?status=${status}` : "";
    return fetchAPI<WatchlistItem[]>(`/user/watchlist${params}`);
}

export async function addToWatchlist(animeId: number, animeTitle: string, animeImage: string, status: string = "plan_to_watch"): Promise<{ message: string; status: string }> {
    return fetchAPI<{ message: string; status: string }>("/user/watchlist", {
        method: "POST",
        body: JSON.stringify({ anime_id: animeId, anime_title: animeTitle, anime_image: animeImage, status }),
    });
}

export async function updateWatchlistStatus(animeId: number, status: string): Promise<{ message: string; status: string }> {
    return fetchAPI<{ message: string; status: string }>(`/user/watchlist/${animeId}`, {
        method: "PUT",
        body: JSON.stringify({ status }),
    });
}

export async function removeFromWatchlist(animeId: number): Promise<{ message: string }> {
    return fetchAPI<{ message: string }>(`/user/watchlist/${animeId}`, { method: "DELETE" });
}

export async function getWatchlistStatus(animeId: number): Promise<{ in_watchlist: boolean; status: string | null }> {
    return fetchAPI<{ in_watchlist: boolean; status: string | null }>(`/user/watchlist-status/${animeId}`);
}

export async function getFavorites(): Promise<WatchlistItem[]> {
    return fetchAPI<WatchlistItem[]>("/user/favorites");
}

export async function toggleFavorite(animeId: number, animeTitle: string = "", animeImage: string = ""): Promise<{ favorited: boolean }> {
    return fetchAPI<{ favorited: boolean }>(`/user/favorites/${animeId}?anime_title=${encodeURIComponent(animeTitle)}&anime_image=${encodeURIComponent(animeImage)}`, {
        method: "POST",
    });
}

export async function isFavorited(animeId: number): Promise<{ favorited: boolean }> {
    return fetchAPI<{ favorited: boolean }>(`/user/is-favorited/${animeId}`);
}

// ─── Comment Endpoints ──────────────────────────────────

export async function getComments(animeId: number, episode: number = 0): Promise<Comment[]> {
    const params = episode > 0 ? `?episode=${episode}` : "";
    return fetchAPI<Comment[]>(`/comments/${animeId}${params}`);
}

export async function addComment(animeId: number, content: string, episode: number = 0): Promise<Comment> {
    const params = episode > 0 ? `?episode=${episode}` : "";
    return fetchAPI<Comment>(`/comments/${animeId}${params}`, {
        method: "POST",
        body: JSON.stringify({ content }),
    });
}

export async function deleteComment(commentId: string): Promise<{ message: string }> {
    return fetchAPI<{ message: string }>(`/comments/${commentId}`, { method: "DELETE" });
}

// ─── Waifu.im API ───────────────────────────────────────

export async function getWaifuImage(tag: string = "waifu"): Promise<string> {
    try {
        const res = await fetch(`https://api.waifu.im/images?IncludedTags=${tag}&IsNsfw=False`);
        const data = await res.json();
        return data.items?.[0]?.url || "";
    } catch {
        // Fallback to waifu.pics
        try {
            const res = await fetch(`https://api.waifu.pics/sfw/waifu`);
            const data = await res.json();
            return data.url || "";
        } catch {
            return "";
        }
    }
}
