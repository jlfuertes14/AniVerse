"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import type { Anime } from "@/lib/types";

interface SpotlightHeroProps {
    spotlightAnime: Anime[];
    onExplore: (anime: Anime) => void;
    onDetail: (anime: Anime) => void;
}

export default function SpotlightHero({ spotlightAnime, onExplore, onDetail }: SpotlightHeroProps) {
    const [activeIndex, setActiveIndex] = useState(0);

    const goToNext = useCallback(() => {
        setActiveIndex((prev) => (prev + 1) % spotlightAnime.length);
    }, [spotlightAnime.length]);

    const goToPrev = useCallback(() => {
        setActiveIndex((prev) => (prev - 1 + spotlightAnime.length) % spotlightAnime.length);
    }, [spotlightAnime.length]);

    // Auto-rotate every 6 seconds
    useEffect(() => {
        if (spotlightAnime.length <= 1) return;
        const interval = setInterval(goToNext, 6000);
        return () => clearInterval(interval);
    }, [goToNext, spotlightAnime.length]);

    if (!spotlightAnime.length) {
        return (
            <div className="spotlight">
                <div className="skeleton" style={{ width: "100%", height: "100%" }} />
            </div>
        );
    }

    return (
        <div className="spotlight">
            {spotlightAnime.map((anime, index) => (
                <div key={anime.id} className={`spotlight-slide ${index === activeIndex ? "active" : ""}`}>
                    <div
                        className="spotlight-bg"
                        style={{
                            backgroundImage: `url(${anime.banner_image || anime.large_image_url || anime.image_url})`,
                        }}
                    />
                    <div className="spotlight-gradient" />

                    <div className="spotlight-content">
                        <span className="spotlight-label">#{index + 1} Spotlight</span>
                        <h1 className="spotlight-title">
                            {anime.title_english || anime.title}
                        </h1>

                        <div className="spotlight-meta">
                            {anime.type && (
                                <span className="spotlight-badge">
                                    ◉ {anime.type}
                                </span>
                            )}
                            {anime.episodes && (
                                <span className="spotlight-badge">
                                    ⏱ {anime.episodes} ep
                                </span>
                            )}
                            {anime.year && (
                                <span className="spotlight-badge">
                                    📅 {anime.season ? `${anime.season} ` : ""}{anime.year}
                                </span>
                            )}
                            {anime.score && (
                                <span className="spotlight-badge-score">
                                    ★ {anime.score}
                                </span>
                            )}
                            {anime.rating && (
                                <span className="spotlight-badge-highlight">
                                    {anime.rating}
                                </span>
                            )}
                        </div>

                        <p className="spotlight-synopsis">
                            {anime.synopsis
                                ? anime.synopsis.replace(/<[^>]*>/g, "").substring(0, 250) + "..."
                                : "No synopsis available."}
                        </p>

                        <div className="spotlight-actions">
                            <Link 
                                href={`/watch/${anime.mal_id || anime.id}/1`} 
                                className="btn-explore"
                            >
                                <span className="btn-explore-icon">▶</span>
                                Watch Now
                            </Link>
                            <button className="btn-detail" onClick={() => onDetail(anime)}>
                                Detail ▸
                            </button>
                        </div>
                    </div>
                </div>
            ))}

            {/* Navigation Arrows */}
            <div className="spotlight-arrows">
                <button className="spotlight-arrow" onClick={goToPrev} aria-label="Previous">
                    ▲
                </button>
                <button className="spotlight-arrow" onClick={goToNext} aria-label="Next">
                    ▼
                </button>
            </div>

            {/* Dot Indicators */}
            <div className="spotlight-dots">
                {spotlightAnime.map((_, index) => (
                    <button
                        key={index}
                        className={`spotlight-dot ${index === activeIndex ? "active" : ""}`}
                        onClick={() => setActiveIndex(index)}
                        aria-label={`Go to slide ${index + 1}`}
                    />
                ))}
            </div>
        </div>
    );
}
