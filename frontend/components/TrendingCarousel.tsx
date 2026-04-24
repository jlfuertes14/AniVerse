"use client";

import { useRef } from "react";
import AnimeCard, { AnimeCardSkeleton } from "./AnimeCard";
import type { Anime } from "@/lib/types";

interface TrendingCarouselProps {
    anime: Anime[];
    loading?: boolean;
    onAnimeClick: (anime: Anime) => void;
}

export default function TrendingCarousel({ anime, loading = false, onAnimeClick }: TrendingCarouselProps) {
    const trackRef = useRef<HTMLDivElement>(null);

    const scroll = (direction: "left" | "right") => {
        if (!trackRef.current) return;
        const scrollAmount = 600;
        trackRef.current.scrollBy({
            left: direction === "left" ? -scrollAmount : scrollAmount,
            behavior: "smooth",
        });
    };

    return (
        <section className="trending-section container">
            <div className="carousel-header">
                <h2 className="section-heading" style={{ marginBottom: 0 }}>Trending</h2>
                <div className="carousel-nav">
                    <button className="carousel-arrow" onClick={() => scroll("left")} aria-label="Scroll left">
                        ◀
                    </button>
                    <button className="carousel-arrow" onClick={() => scroll("right")} aria-label="Scroll right">
                        ▶
                    </button>
                </div>
            </div>

            <div className="carousel-track" ref={trackRef}>
                {loading
                    ? Array.from({ length: 8 }).map((_, i) => <AnimeCardSkeleton key={i} />)
                    : anime.map((a, i) => (
                        <AnimeCard
                            key={a.id}
                            anime={a}
                            index={i}
                            showNumber={true}
                            onClick={onAnimeClick}
                        />
                    ))
                }
            </div>
        </section>
    );
}
