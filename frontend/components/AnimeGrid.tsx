"use client";

import AnimeCard, { AnimeCardSkeleton } from "./AnimeCard";
import type { Anime } from "@/lib/types";

interface AnimeGridProps {
    anime: Anime[];
    loading?: boolean;
    hasMore?: boolean;
    onLoadMore?: () => void;
    onAnimeClick: (anime: Anime) => void;
    loadingMore?: boolean;
}

export default function AnimeGrid({
    anime,
    loading = false,
    hasMore = false,
    onLoadMore,
    onAnimeClick,
    loadingMore = false,
}: AnimeGridProps) {
    if (loading) {
        return (
            <div className="container">
                <div className="anime-grid">
                    {Array.from({ length: 12 }).map((_, i) => (
                        <AnimeCardSkeleton key={i} />
                    ))}
                </div>
            </div>
        );
    }

    if (!anime.length) {
        return (
            <div className="empty-state">
                <div className="empty-state-icon">🔍</div>
                <p className="empty-state-text">No anime found. Try a different search or vibe!</p>
            </div>
        );
    }

    return (
        <div className="container">
            <div className="anime-grid">
                {anime.map((a) => (
                    <AnimeCard key={`${a.source}-${a.id}`} anime={a} onClick={onAnimeClick} />
                ))}
            </div>

            {hasMore && onLoadMore && (
                <div className="load-more-container">
                    {loadingMore ? (
                        <div className="spinner" />
                    ) : (
                        <button className="btn-load-more" onClick={onLoadMore}>
                            Load More
                        </button>
                    )}
                </div>
            )}
        </div>
    );
}
