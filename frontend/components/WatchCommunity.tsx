"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import CommentSection from "@/components/CommentSection";
import AuthModal from "@/components/AuthModal";
import { isFavorited, toggleFavorite } from "@/lib/api";
import { clearAuth, getStoredUser, isLoggedIn } from "@/lib/auth";
import type { User } from "@/lib/auth";
import type { Anime, AnimeDetail } from "@/lib/types";

interface WatchCommunityProps {
    animeId: number;
    episode?: number;
    title: string;
    imageUrl: string;
    anime: AnimeDetail;
    trendingItems: Anime[];
    relatedItems: (Anime | AnimeDetail)[];
}

export default function WatchCommunity({ animeId, episode = 0, title, imageUrl, anime, trendingItems, relatedItems }: WatchCommunityProps) {
    const [currentUser, setCurrentUser] = useState<User | null>(null);
    const [favorited, setFavorited] = useState(false);
    const [showAuthModal, setShowAuthModal] = useState(false);
    const [visibleTrending, setVisibleTrending] = useState(5);

    useEffect(() => {
        const stored = getStoredUser();
        if (stored && isLoggedIn()) {
            setCurrentUser(stored);
            isFavorited(animeId)
                .then((result) => setFavorited(result.favorited))
                .catch(() => setFavorited(false));
        } else {
            setCurrentUser(null);
            setFavorited(false);
        }
    }, [animeId]);

    const handleFavoriteToggle = async () => {
        if (!currentUser) {
            setShowAuthModal(true);
            return;
        }

        try {
            const result = await toggleFavorite(animeId, title, imageUrl);
            setFavorited(result.favorited);
        } catch (error) {
            console.error("Failed to toggle favorite:", error);
        }
    };

    const infoRows = [
        { label: "Type", value: anime.type || "TV" },
        { label: "Country", value: "Japan" },
        { label: "Premiered", value: [anime.season, anime.year].filter(Boolean).join(" ") || "Unknown" },
        { label: "Date aired", value: anime.aired || "Unknown" },
        { label: "Broadcast", value: anime.broadcast || "Unknown" },
        { label: "Status", value: anime.status || "Unknown" },
        { label: "Source", value: anime.source || "Manga" },
        { label: "Genres", value: anime.genres?.join(", ") || "N/A" },
        { label: "Scores", value: anime.score ? `${anime.score} / ${anime.scored_by || 'N/A'} reviews` : "N/A" },
        { label: "Duration", value: anime.duration || "Unknown" },
        { label: "Episodes", value: anime.episodes ? String(anime.episodes) : "Unknown" },
        { label: "Studios", value: anime.studios?.length ? anime.studios.join(", ") : "Unknown" },
        { label: "Producers", value: anime.producers?.length ? anime.producers.join(", ") : "Unknown" },
    ];

    return (
        <section className="watch-community">
            <div className="watch-community-main">
                <div className="watch-community-overview">
                    <div className="watch-community-poster">
                        <img src={imageUrl || anime.image_url || "/file.svg"} alt={title} />
                    </div>

                    <div className="watch-community-copy">
                        <div className="watch-community-header">
                            <div className="watch-community-titles">
                                <h3 className="watch-community-title">{anime.title_english || anime.title}</h3>
                                {anime.title_japanese && (
                                    <p className="watch-community-subtitle">{anime.title_japanese}</p>
                                )}
                            </div>
                            
                            <div className="watch-community-actions">
                                <button
                                    type="button"
                                    className={`watch-like-btn ${favorited ? "active" : ""}`}
                                    onClick={handleFavoriteToggle}
                                >
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill={favorited ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
                                        <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" />
                                    </svg>
                                    {favorited ? "Liked" : "Like"}
                                </button>

                                <div className="watch-community-badges">
                                    <span className="watch-badge-outline">{anime.rating || "PG-13"}</span>
                                    <span className="watch-badge-outline">HD</span>
                                    <span className="watch-badge-outline">CC</span>
                                    <span className="watch-badge-outline">
                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                                            <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3z" />
                                            <path d="M17 11c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-3.08c3.39-.49 6-3.39 6-6.92h-2z" />
                                        </svg>
                                    </span>
                                </div>
                            </div>
                        </div>

                        <p className="watch-community-summary">
                            {(anime.synopsis || "No synopsis available.").replace(/<[^>]*>/g, "")}
                            <span className="watch-summary-more"> [more]</span>
                        </p>

                        <div className="watch-community-facts">
                            {infoRows.map((row) => (
                                <div key={row.label} className="watch-community-fact">
                                    <span className="watch-community-fact-label">{row.label}:</span>
                                    <strong>{row.value}</strong>
                                </div>
                            ))}
                        </div>

                        {anime.genres?.length > 0 && (
                            <div className="watch-community-tags-row">
                                <span className="watch-tags-label">Tags:</span>
                                <div className="watch-tags-list">
                                    {anime.genres.map((genre) => (
                                        <span key={genre} className="watch-community-tag-link">#{genre}</span>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            <div className="watch-community-grid">
                <div className="watch-community-comments">
                    <CommentSection
                        animeId={animeId}
                        episode={episode}
                        currentUser={currentUser}
                        onLoginClick={() => setShowAuthModal(true)}
                    />
                </div>

                <aside className="watch-community-trending">
                    <div className="watch-community-trending-header">
                        <h3>Trending</h3>
                    </div>
                    <div className="watch-community-trending-list">
                        {trendingItems.slice(0, visibleTrending).map((item) => (
                            <Link
                                key={item.id}
                                href={`/watch/${item.mal_id || item.id}/1`}
                                className="watch-community-trending-card"
                            >
                                <img
                                    src={item.image_url || item.large_image_url || "/file.svg"}
                                    alt={item.title}
                                    loading="lazy"
                                />
                                <div className="watch-community-trending-meta">
                                    <p className="watch-community-trending-title">{item.title_english || item.title}</p>
                                    <p className="watch-community-trending-sub">
                                        {item.score ? `★ ${item.score}` : "TV"}
                                        {item.type ? ` · ${item.type}` : ""}
                                        {item.year ? ` · ${item.year}` : ""}
                                    </p>
                                </div>
                            </Link>
                        ))}
                    </div>
                    {visibleTrending < trendingItems.length && (
                        <button 
                            className="watch-community-load-more"
                            onClick={() => setVisibleTrending(prev => prev + 5)}
                        >
                            <span>Load More</span>
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M7 13l5 5 5-5M7 6l5 5 5-5" />
                            </svg>
                        </button>
                    )}
                </aside>
            </div>

            {showAuthModal && (
                <AuthModal
                    onClose={() => setShowAuthModal(false)}
                    onAuthSuccess={(user) => {
                        setCurrentUser(user);
                        setFavorited(true);
                        window.location.reload();
                    }}
                />
            )}
        </section>
    );
}
