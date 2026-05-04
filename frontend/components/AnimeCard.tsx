import type { Anime } from "@/lib/types";

interface AnimeCardProps {
    anime: Anime;
    index?: number;
    showNumber?: boolean;
    onClick: (anime: Anime) => void;
}

export default function AnimeCard({ anime, index, showNumber = false, onClick }: AnimeCardProps) {
    return (
        <div className="anime-card" onClick={() => onClick(anime)} id={`anime-card-${anime.id}`}>
            <div className="anime-card-image-wrapper">
                <img
                    className="anime-card-image"
                    src={anime.image_url || anime.large_image_url || "/placeholder.png"}
                    alt={anime.title}
                    loading="lazy"
                />
                {showNumber && index !== undefined && (
                    <span className="anime-card-number">
                        {String(index + 1).padStart(2, "0")}
                    </span>
                )}
                {anime.score && (
                    <span className="anime-card-score">★ {anime.score}</span>
                )}
            </div>
            <p className="anime-card-title">{anime.title_english || anime.title}</p>
        </div>
    );
}

// Skeleton loading card
export function AnimeCardSkeleton() {
    return (
        <div className="skeleton-card">
            <div className="skeleton skeleton-image" />
            <div className="skeleton skeleton-text" />
            <div className="skeleton skeleton-text-short" />
        </div>
    );
}
