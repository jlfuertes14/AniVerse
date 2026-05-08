"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import TheaterPlayer from "@/components/TheaterPlayer";
import type { Anime, AnimeDetail, StreamResponse } from "@/lib/types";
import LoadingLink from "@/components/LoadingLink";
import { useLoadingToast } from "@/components/LoadingToastProvider";

interface WatchPlaybackClientProps {
    malId: string;
    title: string;
    thumbnailUrl: string;
    currentEpisode: number;
    totalEpisodes: number;
    episodeItems: number[];
    streamData: StreamResponse;
    relatedItems: (Anime | AnimeDetail)[];
    isMovie?: boolean;
}

export default function WatchPlaybackClient({
    malId,
    title,
    thumbnailUrl,
    currentEpisode,
    totalEpisodes,
    episodeItems,
    streamData,
    relatedItems,
    isMovie = false,
}: WatchPlaybackClientProps) {
    const router = useRouter();
    const searchParams = useSearchParams();
    const { showLoading } = useLoadingToast();
    const autoNextTriggeredRef = useRef(false);
    const [episodeQuery, setEpisodeQuery] = useState("");
    const [rangeOverride, setRangeOverride] = useState<number | null>(null);
    const isFromLatest = searchParams.get("from") === "latest";
    const directParam = searchParams.get("direct");
    const forceDirectPlayback =
        directParam === "1" || (streamData.provider === "reanime" && directParam !== "0");
    const activeRangeIndex = rangeOverride ?? Math.floor((currentEpisode - 1) / 100);
    const hasNextEpisode = Boolean(totalEpisodes && currentEpisode < totalEpisodes);

    const episodeChunks: { start: number; end: number; label: string }[] = [];
    for (let i = 0; i < episodeItems.length; i += 100) {
        const start = episodeItems[i];
        const end = episodeItems[Math.min(i + 99, episodeItems.length - 1)];
        episodeChunks.push({
            start,
            end,
            label: `${String(start).padStart(3, "0")}-${String(end).padStart(3, "0")}`,
        });
    }

    const query = episodeQuery.trim();
    const filteredEpisodes = query
        ? episodeItems.filter((epNum) => String(epNum).includes(query))
        : episodeItems.slice(activeRangeIndex * 100, (activeRangeIndex + 1) * 100);

    const navigateToEpisode = useCallback((episodeNumber: number) => {
        if (autoNextTriggeredRef.current) return;
        autoNextTriggeredRef.current = true;
        showLoading(`Loading episode ${episodeNumber}...`);

        const nextUrl = `/watch/${malId}/${episodeNumber}`;
        if (typeof window !== "undefined" && window.location.pathname !== nextUrl) {
            window.location.assign(nextUrl);
            return;
        }

        router.push(nextUrl);
    }, [malId, router, showLoading]);

    const switchProvider = useCallback((newProvider: string) => {
        const params = new URLSearchParams(searchParams.toString());
        params.set("prefer", newProvider);
        showLoading(`Switching to ${newProvider === "reanime" ? "Re:ANIME" : "AnimePahe"}...`);
        router.push(`/watch/${malId}/${currentEpisode}?${params.toString()}`);
    }, [currentEpisode, malId, router, searchParams, showLoading]);

    return (
        <div className={`watch-playback-container ${isMovie ? "movie-mode" : ""}`} suppressHydrationWarning={true}>
            {!isMovie && (
                <aside className="watch-sidebar">
                    <div className="watch-side-panel">
                        <div className="watch-side-top">
                            <span className="watch-chip active">Episodes</span>
                            {episodeChunks.map((chunk, idx) => (
                                <button
                                    key={idx}
                                    className={`watch-chip-btn ${idx === activeRangeIndex ? "active" : ""}`}
                                    onClick={() => setRangeOverride(idx)}
                                >
                                    {chunk.label}
                                </button>
                            ))}
                        </div>
                        <div className="watch-episode-search">
                        <input
                            type="text"
                            placeholder="Find ep"
                            aria-label="Find episode"
                            value={episodeQuery}
                            onChange={(e) => setEpisodeQuery(e.target.value)}
                        />
                    </div>
                    <div className="watch-episode-list-container">
                        <div className="watch-episode-list">
                            {filteredEpisodes.map((epNum) => (
                                <LoadingLink
                                    key={epNum}
                                    href={`/watch/${malId}/${epNum}`}
                                    className={`watch-episode-btn ${epNum === currentEpisode ? "active" : ""} ${epNum === currentEpisode && isFromLatest ? "highlight-latest" : ""}`}
                                    aria-current={epNum === currentEpisode ? "true" : undefined}
                                    loadingMessage={`Loading episode ${epNum}...`}
                                >
                                    {String(epNum)}
                                </LoadingLink>
                            ))}
                        </div>
                        {filteredEpisodes.length === 0 && (
                            <div className="watch-episode-empty">No episodes match.</div>
                        )}
                    </div>
                </div>
                </aside>
            )}

            <section className="watch-main">
                <TheaterPlayer
                    embedUrl={streamData.embed_url}
                    streamUrl={streamData.stream_url}
                    refererUrl={streamData.referer_url}
                    subtitles={streamData.subtitles}
                    provider={streamData.provider}
                    thumbnailUrl={thumbnailUrl}
                    title={title}
                    episodeNumber={currentEpisode}
                    isFromLatest={isFromLatest}
                    forceDirectPlayback={forceDirectPlayback}
                />

                <div className="watch-player-meta">
                    <div className="watch-meta-group">
                        <div className="watch-meta-chip">
                            <span className="icon">SUB</span> EN
                        </div>
                        <div className="watch-meta-chip server-selector">
                            <span className="icon">SERVER:</span>
                            <button
                                type="button"
                                className={`server-btn ${streamData.provider === "animepahe" ? "active" : ""}`}
                                onClick={() => switchProvider("animepahe")}
                            >
                                PAHE
                            </button>
                            <button
                                type="button"
                                className={`server-btn ${streamData.provider === "reanime" ? "active" : ""}`}
                                onClick={() => switchProvider("reanime")}
                            >
                                RE:ANIME
                            </button>
                        </div>
                        <div className="watch-meta-chip">
                            <span className="icon">QUALITY:</span> 1080P
                        </div>
                    </div>

                    {hasNextEpisode && (
                        <button
                            type="button"
                            className="watch-next-ep-btn desktop-next-btn"
                            onClick={() => navigateToEpisode(currentEpisode + 1)}
                        >
                            <span className="play-icon">▶</span>
                            NEXT EPISODE (Ep {currentEpisode + 1})
                        </button>
                    )}
                </div>

                {/* Mobile Next Episode Button */}
                {hasNextEpisode && (
                    <button
                        type="button"
                        className="watch-next-ep-btn mobile-next-btn"
                        onClick={() => navigateToEpisode(currentEpisode + 1)}
                    >
                        <span className="play-icon">▶</span>
                        NEXT EPISODE (Ep {currentEpisode + 1})
                    </button>
                )}

                {/* New Mobile Episode Guide */}
                {!isMovie && (episodeItems.length > 1) && (
                    <section className="watch-ep-guide">
                        <h3>Episode Guide</h3>
                        <div className="watch-ep-scroll">
                            {episodeItems.map((epNum) => (
                                <LoadingLink
                                    key={epNum}
                                    href={`/watch/${malId}/${epNum}`}
                                    className={`watch-ep-card ${epNum === currentEpisode ? "active" : ""}`}
                                    loadingMessage={`Loading episode ${epNum}...`}
                                >
                                    <div className={`watch-ep-thumb ${epNum === currentEpisode ? "active" : ""}`}>
                                        <img src={thumbnailUrl} alt={`Episode ${epNum}`} loading="lazy" />
                                        <div className="play-icon">▶</div>
                                    </div>
                                    <div className="watch-ep-label">Episode {epNum}</div>
                                    <div className="watch-ep-indicator"></div>
                                </LoadingLink>
                            ))}
                        </div>
                    </section>
                )}

                {/* New Mobile Recommendations */}
                <section className="watch-related-mobile">
                    <h3>YOU MIGHT ALSO LIKE</h3>
                    <div className="watch-related-list-mobile">
                        {relatedItems.map((item) => (
                            <LoadingLink
                                key={item.id}
                                href={`/watch/${item.mal_id || item.id}/1`}
                                className="watch-mobile-card"
                                loadingMessage={`Loading ${item.title_english || item.title}...`}
                            >
                                <div className="watch-mobile-thumb">
                                    <img
                                        src={item.image_url || item.large_image_url || "/file.svg"}
                                        alt={item.title}
                                        loading="lazy"
                                    />
                                </div>
                                <div className="watch-mobile-info">
                                    <div className="watch-mobile-title">{item.title_english || item.title}</div>
                                    <div className="watch-mobile-meta">
                                        <span className="watch-mobile-genre">
                                            [{item.type || "TV"}]
                                        </span>
                                        <span className="watch-mobile-rating">
                                            ★ {(item as AnimeDetail).score || "N/A"}
                                        </span>
                                    </div>
                                </div>
                                <div className="watch-mobile-play">▶</div>
                            </LoadingLink>
                        ))}
                    </div>
                </section>

            </section>

            <aside className="watch-related">
                <div className="watch-related-panel">
                    <div className="watch-related-header">
                        <h3>Related</h3>
                        <button type="button" className="watch-related-more">More</button>
                    </div>
                    <div className="watch-related-list">
                        {relatedItems.length === 0 && (
                            <div className="watch-related-empty">No related titles yet.</div>
                        )}
                        {relatedItems.map((item) => (
                            <LoadingLink
                                href={`/watch/${item.mal_id || item.id}/1`}
                                className="watch-related-card"
                                key={item.id}
                                loadingMessage={`Loading ${item.title_english || item.title}...`}
                            >
                                <img
                                    src={item.image_url || item.large_image_url || "/file.svg"}
                                    alt={item.title}
                                    loading="lazy"
                                />
                                <div className="watch-related-meta">
                                    <p className="watch-related-title">{item.title_english || item.title}</p>
                                    <p className="watch-related-sub">
                                        {item.type || "TV"}
                                        {item.year ? ` · ${item.year}` : ""}
                                    </p>
                                </div>
                            </LoadingLink>
                        ))}
                    </div>
                </div>
            </aside>
        </div>
    );
}
