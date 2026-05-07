import Link from "next/link";
import StreamPendingRefresher from "@/components/StreamPendingRefresher";
import StreamNotFoundRefresher from "@/components/StreamNotFoundRefresher";
import WatchNavbar from "@/components/WatchNavbar";
import WatchPlaybackClient from "@/components/WatchPlaybackClient";
import WatchCommunity from "@/components/WatchCommunity";
import type { Anime, AnimeDetail, CatalogStatus, StreamResponse } from "@/lib/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

interface PendingStreamState {
    isScraping: true;
    available_episodes?: number;
    catalog_status?: CatalogStatus;
}

function isPendingStreamState(
    streamData: StreamResponse | PendingStreamState | null
): streamData is PendingStreamState {
    return Boolean(streamData && "isScraping" in streamData);
}

async function getStreamData(
    malId: string,
    ep: string,
    prefer?: string,
    from?: string,
): Promise<StreamResponse | PendingStreamState | null> {
    const params = new URLSearchParams();
    if (prefer) params.set("prefer", prefer);
    if (from) params.set("from", from);
    const query = params.toString() ? `?${params.toString()}` : "";
    const res = await fetch(`${API_BASE}/stream/${malId}/${ep}${query}`, {
        cache: "no-store",
    });
    if (res.status === 202) {
        const pendingData = await res.json().catch(() => ({}));
        return {
            isScraping: true,
            available_episodes: pendingData.available_episodes,
            catalog_status: pendingData.catalog_status,
        };
    }
    if (!res.ok) return null;
    return res.json();
}

async function getAnimeData(malId: string): Promise<AnimeDetail | null> {
    const res = await fetch(`${API_BASE}/anime/${malId}?source=jikan`, {
        next: { revalidate: 3600 },
    });
    if (!res.ok) return null;
    return res.json();
}

async function getRelatedRecommendations(malId: string): Promise<AnimeDetail["recommendations"]> {
    const res = await fetch(`${API_BASE}/ai/similar/${malId}?count=6`, {
        cache: "no-store",
    });
    if (!res.ok) return [];

    const data = await res.json().catch(() => null);
    if (!data?.model_ready || !Array.isArray(data.results)) {
        return [];
    }

    return data.results;
}

async function getTrendingItems(): Promise<Anime[]> {
    const res = await fetch(`${API_BASE}/anime/trending?page=1`, {
        next: { revalidate: 1800 },
    });
    if (!res.ok) return [];
    const data = await res.json().catch(() => null);
    if (!data?.data || !Array.isArray(data.data)) return [];
    return data.data.slice(0, 10);
}

function buildEpisodeList(total: number, current: number): number[] {
    if (!Number.isFinite(current) || current <= 0) return [];
    if (!total || total <= 1) return [current];
    return Array.from({ length: total }, (_, i) => i + 1);
}

export default async function WatchPage({
    params,
    searchParams,
}: {
    params: Promise<{ mal_id: string; ep: string }>;
    searchParams: Promise<{ prefer?: string; from?: string }>;
}) {
    const [resolvedParams, resolvedSearchParams] = await Promise.all([params, searchParams]);
    const { mal_id, ep } = resolvedParams;
    const preferProvider = resolvedSearchParams?.prefer;
    const fromContext = resolvedSearchParams?.from;

    const [streamData, anime, aiRelated, trendingItems] = await Promise.all([
        getStreamData(mal_id, ep, preferProvider, fromContext),
        getAnimeData(mal_id),
        getRelatedRecommendations(mal_id),
        getTrendingItems(),
    ]);

    const title = anime?.title_english || anime?.title || "Unknown Title";
    const thumbnailUrl = anime?.large_image_url || anime?.image_url || "";
    const currentEpisode = Number(ep);
    const normalizedEpisode = Number.isFinite(currentEpisode) && currentEpisode > 0 ? currentEpisode : 1;
    const streamProvider = !isPendingStreamState(streamData) && streamData ? streamData.provider : null;
    const streamAvailableEpisodes = !isPendingStreamState(streamData) && streamData
        ? streamData.available_episodes
        : undefined;
    
    // Combine all sources of truth for episode count
    const jikanEpisodes = anime?.episodes || 0;
    const providerEpisodes = typeof streamAvailableEpisodes === "number" ? streamAvailableEpisodes : 0;
    const isAiring = anime?.status === "Currently Airing";

    // Logic: 
    // 1. If it's airing, we trust the provider's available count more than the total planned episodes.
    // 2. We always show at least the episode the user is currently watching.
    // 3. We fallback to 12 as a sensible minimum for UI layout if no data exists.
    let totalEpisodes: number;

    if (isAiring) {
        // For airing shows, limit to what's actually available to watch, 
        // or what Jikan says has aired so far (if provider is empty).
        totalEpisodes = Math.max(providerEpisodes, normalizedEpisode);
        if (totalEpisodes === 0) totalEpisodes = Math.max(jikanEpisodes, 12);
    } else {
        // For finished shows, the Jikan total is the source of truth.
        totalEpisodes = Math.max(jikanEpisodes, providerEpisodes, normalizedEpisode, 12);
    }
    
    const episodeItems = buildEpisodeList(totalEpisodes, normalizedEpisode);
    const relatedItems = (aiRelated?.length ? aiRelated : anime?.recommendations?.length ? anime.recommendations : anime?.related || []).slice(0, 6);

    if (isPendingStreamState(streamData)) {
        return (
            <>
                <WatchNavbar />
                <main className="watch-page" suppressHydrationWarning={true}>
                    <StreamPendingRefresher
                        title={title}
                        thumbnailUrl={thumbnailUrl}
                        episodeLabel={`Episode ${ep}`}
                        availableEpisodes={streamData.available_episodes}
                        catalogStatus={streamData.catalog_status}
                        provider={preferProvider || "animepahe"}
                    />
                </main>
            </>
        );
    }

    if (!streamData) {
        return (
            <>
                <WatchNavbar />
                <main className="watch-page" suppressHydrationWarning={true}>
                    <StreamNotFoundRefresher malId={mal_id} />
                </main>
            </>
        );
    }

    const resolvedStreamData: StreamResponse = streamData;

    return (
        <>
            <WatchNavbar />
            <main className="watch-page" suppressHydrationWarning={true}>

                <WatchPlaybackClient
                    malId={mal_id}
                    title={title}
                    thumbnailUrl={thumbnailUrl}
                    currentEpisode={normalizedEpisode}
                    totalEpisodes={totalEpisodes}
                    episodeItems={episodeItems}
                    streamData={resolvedStreamData}
                    relatedItems={relatedItems}
                />

                {anime && (
                    <WatchCommunity
                        animeId={Number(mal_id)}
                        episode={normalizedEpisode}
                        title={title}
                        imageUrl={thumbnailUrl}
                        anime={anime}
                        trendingItems={trendingItems}
                        relatedItems={relatedItems}
                    />
                )}
            </main>
        </>
    );
}
