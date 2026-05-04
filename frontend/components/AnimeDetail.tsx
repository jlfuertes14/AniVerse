"use client";

import { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { getAnimeDetail, getSimilarAnime, addToWatchlist, toggleFavorite, isFavorited, getWatchlistStatus } from "@/lib/api";
import AnimeCard from "./AnimeCard";
import CommentSection from "./CommentSection";
import type { Anime, AnimeDetail as AnimeDetailType } from "@/lib/types";
import type { User } from "@/lib/auth";

interface AnimeDetailProps {
    anime: Anime | null;
    isOpen: boolean;
    onClose: () => void;
    onAnimeClick: (anime: Anime) => void;
    currentUser: User | null;
    onLoginClick: () => void;
}

const WATCHLIST_STATUSES = [
    { value: "watching", label: "Watching", icon: "▶" },
    { value: "completed", label: "Completed", icon: "✓" },
    { value: "plan_to_watch", label: "Plan to Watch", icon: "📋" },
    { value: "on_hold", label: "On Hold", icon: "⏸" },
    { value: "dropped", label: "Dropped", icon: "✕" },
];

export default function AnimeDetail({ anime, isOpen, onClose, onAnimeClick, currentUser, onLoginClick }: AnimeDetailProps) {
    const [detail, setDetail] = useState<AnimeDetailType | null>(null);
    const [loading, setLoading] = useState(false);
    const [similarAnime, setSimilarAnime] = useState<Anime[]>([]);
    const [favorited, setFavorited] = useState(false);
    const [watchlistStatus, setWatchlistStatus] = useState<string | null>(null);
    const [showWatchlistMenu, setShowWatchlistMenu] = useState(false);
    const charactersRef = useRef<HTMLDivElement | null>(null);
    const recommendationsRef = useRef<HTMLDivElement | null>(null);
    const similarRef = useRef<HTMLDivElement | null>(null);

    useEffect(() => {
        if (!anime || !isOpen) return;
        setLoading(true);
        setDetail(null);
        setFavorited(false);
        setWatchlistStatus(null);

        const id = anime.anilist_id || anime.id;
        const source = anime.anilist_id ? "anilist" : anime.mal_id ? "jikan" : "anilist";

        getAnimeDetail(id, source)
            .then((d) => setDetail(d as AnimeDetailType))
            .catch(console.error)
            .finally(() => setLoading(false));

        // Fetch ML-based similar anime
        getSimilarAnime(id)
            .then((res) => setSimilarAnime(res.results || []))
            .catch(() => setSimilarAnime([]));

        // Fetch user-specific state
        if (currentUser) {
            isFavorited(id).then((r) => setFavorited(r.favorited)).catch(() => {});
            getWatchlistStatus(id).then((r) => setWatchlistStatus(r.status)).catch(() => {});
        }
    }, [anime, isOpen]);

    // Close on Escape
    useEffect(() => {
        const handleEscape = (e: KeyboardEvent) => {
            if (e.key === "Escape") onClose();
        };
        if (isOpen) window.addEventListener("keydown", handleEscape);
        return () => window.removeEventListener("keydown", handleEscape);
    }, [isOpen, onClose]);

    const data = detail || anime;
    if (!data) return null;

    const animeId = data.mal_id || data.anilist_id || data.id;

    const trailerUrl = detail?.trailer_url;
    const youtubeEmbedUrl = trailerUrl?.includes("youtube.com/watch")
        ? trailerUrl.replace("watch?v=", "embed/")
        : trailerUrl?.includes("youtu.be/")
            ? `https://www.youtube.com/embed/${trailerUrl.split("youtu.be/")[1]}`
            : null;

    const handleFavoriteToggle = async () => {
        if (!currentUser) { onLoginClick(); return; }
        try {
            const result = await toggleFavorite(animeId, data.title, data.image_url);
            setFavorited(result.favorited);
        } catch (err) {
            console.error("Failed to toggle favorite:", err);
        }
    };

    const handleWatchlistAdd = async (status: string) => {
        if (!currentUser) { onLoginClick(); return; }
        try {
            await addToWatchlist(animeId, data.title, data.image_url, status);
            setWatchlistStatus(status);
            setShowWatchlistMenu(false);
        } catch (err) {
            console.error("Failed to add to watchlist:", err);
        }
    };

    const scrollRail = (ref: { current: HTMLDivElement | null }, direction: "left" | "right") => {
        const node = ref.current;
        if (!node) return;
        const amount = Math.max(280, Math.floor(node.clientWidth * 0.75));
        node.scrollBy({
            left: direction === "left" ? -amount : amount,
            behavior: "smooth",
        });
    };

    return (
        <div className={`detail-overlay ${isOpen ? "open" : ""}`} onClick={(e) => {
            if (e.target === e.currentTarget) onClose();
        }}>
            <div className="detail-modal">
                {/* Banner */}
                <div
                    className="detail-banner"
                    style={{
                        backgroundImage: `url(${(detail as AnimeDetailType)?.banner_image || data.large_image_url || data.image_url})`,
                    }}
                >
                    <div className="detail-banner-gradient" />
                    <button className="detail-close" onClick={onClose}>✕</button>
                </div>

                {/* Body */}
                <div className="detail-body">
                    <div className="detail-main">
                        <div className="detail-poster">
                            <img src={data.image_url || data.large_image_url || ""} alt={data.title} />
                        </div>

                        <div className="detail-info">
                            <h2 className="detail-title">{data.title_english || data.title}</h2>
                            {data.title_japanese && (
                                <p className="detail-subtitle">{data.title_japanese}</p>
                            )}

                            <div className="detail-meta">
                                {data.score && <span className="detail-meta-item detail-meta-score">★ {data.score}</span>}
                                {data.type && <span className="detail-meta-item">{data.type}</span>}
                                {data.episodes && <span className="detail-meta-item">{data.episodes} episodes</span>}
                                {data.status && <span className="detail-meta-item">{data.status}</span>}
                                {detail?.duration && <span className="detail-meta-item">{detail.duration}</span>}
                                {detail?.aired && <span className="detail-meta-item">{detail.aired}</span>}
                                {data.rating && <span className="detail-meta-item">{data.rating}</span>}
                            </div>

                            <div className="detail-actions-primary" style={{ 
                                marginBottom: "1.5rem",
                                display: "flex",
                                gap: "1rem"
                            }}>
                                <Link
                                    href={`/watch/${animeId}/1`}
                                    className="btn-watch-now"
                                    style={{
                                        display: "flex",
                                        alignItems: "center",
                                        gap: "0.75rem",
                                        padding: "0.8rem 2.5rem",
                                        background: "linear-gradient(135deg, var(--gold) 0%, #ffcc00 100%)",
                                        color: "#000",
                                        borderRadius: "var(--radius-full)",
                                        fontWeight: "800",
                                        fontSize: "1.05rem",
                                        textTransform: "uppercase",
                                        letterSpacing: "0.05em",
                                        boxShadow: "0 8px 24px rgba(212, 175, 55, 0.3)",
                                        transition: "all 0.3s cubic-bezier(0.4, 0, 0.2, 1)",
                                        border: "none",
                                        cursor: "pointer"
                                    }}
                                >
                                    <span style={{ 
                                        background: "rgba(0,0,0,0.1)", 
                                        width: "28px", 
                                        height: "28px", 
                                        display: "flex", 
                                        alignItems: "center", 
                                        justifyContent: "center",
                                        borderRadius: "50%",
                                        fontSize: "0.9rem"
                                    }}>▶</span>
                                    Watch Now
                                </Link>
                            </div>

                            <div className="detail-actions">
                                <button
                                    className={`detail-action-btn detail-favorite-btn ${favorited ? "active" : ""}`}
                                    onClick={handleFavoriteToggle}
                                >
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill={favorited ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
                                        <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" />
                                    </svg>
                                    {favorited ? "Favorited" : "Favorite"}
                                </button>

                                <div className="detail-watchlist-wrapper">
                                    <button
                                        className={`detail-action-btn detail-watchlist-btn ${watchlistStatus ? "active" : ""}`}
                                        onClick={() => {
                                            if (!currentUser) { onLoginClick(); return; }
                                            setShowWatchlistMenu(!showWatchlistMenu);
                                        }}
                                    >
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <path d="M19 21l-7-5-7 5V5a2 2 0 012-2h10a2 2 0 012 2z" />
                                        </svg>
                                        {watchlistStatus
                                            ? WATCHLIST_STATUSES.find((s) => s.value === watchlistStatus)?.label || "In List"
                                            : "Add to List"
                                        }
                                    </button>

                                    {showWatchlistMenu && (
                                        <div className="detail-watchlist-menu">
                                            {WATCHLIST_STATUSES.map((s) => (
                                                <button
                                                    key={s.value}
                                                    className={`detail-watchlist-option ${watchlistStatus === s.value ? "active" : ""}`}
                                                    onClick={() => handleWatchlistAdd(s.value)}
                                                >
                                                    <span>{s.icon}</span>
                                                    {s.label}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </div>
                            </div>

                            <div className="detail-genres">
                                {data.genres?.map((g) => (
                                    <span key={g} className="detail-genre-tag">{g}</span>
                                ))}
                            </div>
                        </div>
                    </div>

                    <div className="detail-secondary">
                        <p className="detail-synopsis">
                            {(data.synopsis || "No synopsis available.").replace(/<[^>]*>/g, "")}
                        </p>

                        {data.studios && data.studios.length > 0 && (
                            <div className="detail-studios">
                                <span className="detail-studios-label">Studios: </span>
                                <span className="detail-studios-value">{data.studios.join(", ")}</span>
                            </div>
                        )}

                        {detail?.characters && detail.characters.length > 0 && (
                            <>
                                <div className="detail-section-header">
                                    <h3 className="detail-section-title">Characters</h3>
                                    <div className="detail-rail-controls">
                                        <button type="button" className="detail-rail-btn" aria-label="Previous characters" onClick={() => scrollRail(charactersRef, "left")}>
                                            &lt;
                                        </button>
                                        <button type="button" className="detail-rail-btn" aria-label="Next characters" onClick={() => scrollRail(charactersRef, "right")}>
                                            &gt;
                                        </button>
                                    </div>
                                </div>
                                <div className="detail-characters" ref={charactersRef}>
                                    {detail.characters.map((char, i) => (
                                        <div key={i} className="detail-character">
                                            {char.image_url && (
                                                <img className="detail-character-img" src={char.image_url} alt={char.name} loading="lazy" />
                                            )}
                                            <p className="detail-character-name">{char.name}</p>
                                        </div>
                                    ))}
                                </div>
                            </>
                        )}

                        {detail?.recommendations && detail.recommendations.length > 0 && (
                            <>
                                <div className="detail-section-header" style={{ marginTop: "1.5rem" }}>
                                    <h3 className="detail-section-title">You Might Also Like</h3>
                                    <div className="detail-rail-controls">
                                        <button type="button" className="detail-rail-btn" aria-label="Previous recommendations" onClick={() => scrollRail(recommendationsRef, "left")}>
                                            &lt;
                                        </button>
                                        <button type="button" className="detail-rail-btn" aria-label="Next recommendations" onClick={() => scrollRail(recommendationsRef, "right")}>
                                            &gt;
                                        </button>
                                    </div>
                                </div>
                                <div className="detail-recommendations" ref={recommendationsRef}>
                                    {detail.recommendations.map((rec) => (
                                        <AnimeCard
                                            key={rec.id}
                                            anime={rec}
                                            onClick={(a) => {
                                                onAnimeClick(a);
                                            }}
                                        />
                                    ))}
                                </div>
                            </>
                        )}

                        {similarAnime.length > 0 && (
                            <div className="similar-anime-section">
                                <div className="detail-section-header">
                                    <h3 className="detail-section-title">🧠 AI Recommends (ML-powered)</h3>
                                    <div className="detail-rail-controls">
                                        <button type="button" className="detail-rail-btn" aria-label="Previous AI recommendations" onClick={() => scrollRail(similarRef, "left")}>
                                            &lt;
                                        </button>
                                        <button type="button" className="detail-rail-btn" aria-label="Next AI recommendations" onClick={() => scrollRail(similarRef, "right")}>
                                            &gt;
                                        </button>
                                    </div>
                                </div>
                                <div className="similar-anime-grid" ref={similarRef}>
                                    {similarAnime.map((sim: any) => (
                                        <AnimeCard
                                            key={sim.id}
                                            anime={sim}
                                            onClick={onAnimeClick}
                                        />
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                </div>

                {/* Trailer — full-width, outside the grid */}
                {isOpen && youtubeEmbedUrl && (
                    <div className="detail-trailer">
                        <iframe
                            src={youtubeEmbedUrl}
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                            allowFullScreen
                            title="Trailer"
                        />
                    </div>
                )}

                {/* Comments Section */}
                {!loading && isOpen && (
                    <div className="detail-comments-wrapper">
                        <CommentSection
                            animeId={animeId}
                            currentUser={currentUser}
                            onLoginClick={onLoginClick}
                        />
                    </div>
                )}

                {loading && (
                    <div style={{ textAlign: "center", padding: "2rem" }}>
                        <div className="spinner" />
                        <p style={{ color: "var(--text-muted)", fontSize: "0.8rem", marginTop: "0.5rem" }}>Loading details...</p>
                    </div>
                )}
            </div>
        </div>
    );
}
