"use client";

import Link from "next/link";
import { useCallback, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import TheaterPlayer from "@/components/TheaterPlayer";
import type { Anime, AnimeDetail, StreamResponse } from "@/lib/types";

interface WatchPlaybackClientProps {
    malId: string;
    title: string;
    thumbnailUrl: string;
    currentEpisode: number;
    totalEpisodes: number;
    episodeItems: number[];
    streamData: StreamResponse;
    relatedItems: (Anime | AnimeDetail)[];
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
}: WatchPlaybackClientProps) {
    const router = useRouter();
    const searchParams = useSearchParams();
    const autoNextTriggeredRef = useRef(false);
    const [episodeQuery, setEpisodeQuery] = useState("");
    const [rangeOverride, setRangeOverride] = useState<number | null>(null);
    const isFromLatest = searchParams.get("from") === "latest";
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

        const nextUrl = `/watch/${malId}/${episodeNumber}`;
        if (typeof window !== "undefined" && window.location.pathname !== nextUrl) {
            window.location.assign(nextUrl);
            return;
        }

        router.push(nextUrl);
    }, [malId, router]);

    return (
        <div className="watch-playback-container" suppressHydrationWarning={true}>
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
                                <Link
                                    key={epNum}
                                    href={`/watch/${malId}/${epNum}`}
                                    className={`watch-episode-btn ${epNum === currentEpisode ? "active" : ""} ${epNum === currentEpisode && isFromLatest ? "highlight-latest" : ""}`}
                                    aria-current={epNum === currentEpisode ? "true" : undefined}
                                >
                                    {String(epNum)}
                                </Link>
                            ))}
                        </div>
                        {filteredEpisodes.length === 0 && (
                            <div className="watch-episode-empty">No episodes match.</div>
                        )}
                    </div>
                </div>
            </aside>

            <section className="watch-main">
                <TheaterPlayer
                    embedUrl={streamData.embed_url}
                    streamUrl={streamData.stream_url}
                    subtitles={streamData.subtitles}
                    provider={streamData.provider}
                    thumbnailUrl={thumbnailUrl}
                    title={title}
                    episodeNumber={currentEpisode}
                    isFromLatest={isFromLatest}
                />

                <div className="watch-controls">
                    <div className="watch-control-group">
                        <span className="watch-control-chip active">SUB</span>
                        <span className="watch-control-chip">Server: Auto</span>
                        <span className="watch-control-chip">Quality: 720p</span>
                    </div>
                    {hasNextEpisode && (
                        <div className="watch-control-group">
                            <button
                                type="button"
                                className="watch-control-btn active"
                                onClick={() => navigateToEpisode(currentEpisode + 1)}
                            >
                                Next Episode
                            </button>
                        </div>
                    )}
                </div>

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
                            <Link
                                href={`/watch/${item.mal_id || item.id}/1`}
                                className="watch-related-card"
                                key={item.id}
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
                            </Link>
                        ))}
                    </div>
                </div>
            </aside>
        </div>
    );
}
