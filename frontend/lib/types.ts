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
    broadcast?: string | null;
    producers?: string[] | null;
    scored_by?: number | null;
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

export interface SubtitleTrack {
    url: string;
    label: string;
    lang: string;
}

export interface CatalogStatus {
    provider: string;
    latest_episode?: number | null;
    last_checked_at?: string | null;
    is_refreshing: boolean;
    is_stale: boolean;
    provider_status?: string | null;
    is_airing?: boolean | null;
    last_success_at?: string | null;
    last_scrape_error?: string | null;
    last_scrape_duration_ms?: number | null;
    next_airing_episode?: number | null;
    next_airing_at?: string | null;
}

export interface StreamResponse {
    mal_id: number;
    ep_number: number;
    embed_url?: string;
    stream_url?: string;
    referer_url?: string;
    subtitles?: SubtitleTrack[];
    provider: string;
    available_episodes?: number;
    catalog_status?: CatalogStatus;
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
    type?: string;
    page?: number;
}

export interface LatestRelease {
    title: string;
    episode: string;
    display_episode?: string;
    snapshot: string;
    mal_id?: number;
    session: string;
}

export interface AiringShow {
    title: string;
    episode: string;
    airing_at: string;
    display_time: string;
    image_url: string;
    show_id: string;
    route: string;
    air_type?: string;
    status?: string;
    episodes?: string;
    popularity?: string;
    media_type?: string;
    anime_url?: string;
    date_label?: string;
    is_filtered_out?: boolean;
    reference_airing_at?: string | null;
    week_offset_days?: number;
}

export interface WeeklySchedule {
    monday: AiringShow[];
    tuesday: AiringShow[];
    wednesday: AiringShow[];
    thursday: AiringShow[];
    friday: AiringShow[];
    saturday: AiringShow[];
    sunday: AiringShow[];
}
