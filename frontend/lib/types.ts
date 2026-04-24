/* ============================================
   Anime Discovery Engine — TypeScript Types
   ============================================ */

export interface Anime {
    id: number;
    mal_id?: number | null;
    anilist_id?: number | null;
    title: string;
    title_english?: string | null;
    title_japanese?: string | null;
    image_url: string;
    large_image_url?: string | null;
    synopsis?: string | null;
    score?: number | null;
    episodes?: number | null;
    status?: string | null;
    rating?: string | null;
    year?: number | null;
    season?: string | null;
    type?: string | null;
    genres: string[];
    studios: string[];
    source: string;
    banner_image?: string | null;
    trailer_url?: string | null;
}

export interface AnimeDetail extends Anime {
    duration?: string | null;
    aired?: string | null;
    rank?: number | null;
    popularity?: number | null;
    members?: number | null;
    background?: string | null;
    related?: Anime[];
    recommendations?: Anime[];
    characters?: Character[];
}

export interface Character {
    name: string;
    role?: string;
    image_url: string;
}

export interface ScreenshotResult {
    anilist_id?: number | null;
    mal_id?: number | null;
    title?: string | null;
    title_english?: string | null;
    episode?: number | null;
    timestamp_from?: number | null;
    timestamp_to?: number | null;
    similarity: number;
    image_url?: string | null;
    video_url?: string | null;
}

export interface VibePreset {
    id: string;
    name: string;
    emoji: string;
    description: string;
    genres: string[];
    tags: string[];
    year_from?: number | null;
    year_to?: number | null;
    studios: string[];
    demographic?: string | null;
}

export interface PaginatedResponse {
    data: Anime[];
    total: number;
    page: number;
    has_next: boolean;
}

export interface Genre {
    mal_id: number;
    name: string;
    count: number;
}

export interface Studio {
    mal_id: number;
    name: string;
    count: number;
}

export interface SearchFilters {
    query?: string;
    vibe?: string;
    genres?: string;
    studios?: string;
    year_from?: number;
    year_to?: number;
    status?: string;
    rating?: string;
    page?: number;
}
