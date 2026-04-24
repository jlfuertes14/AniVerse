"use client";

import { useState, useEffect, useRef } from "react";
import { getWatchlist, getFavorites, removeFromWatchlist, updateWatchlistStatus, getMe, uploadAvatar } from "@/lib/api";
import type { WatchlistItem } from "@/lib/api";
import type { User } from "@/lib/auth";

interface ProfilePageProps {
    user: User;
    onAnimeClick: (animeId: number) => void;
    onClose: () => void;
    onUserUpdate?: (user: User) => void;
}

const STATUS_LABELS: Record<string, string> = {
    watching: "Watching",
    completed: "Completed",
    plan_to_watch: "Plan to Watch",
    on_hold: "On Hold",
    dropped: "Dropped",
};

const STATUS_COLORS: Record<string, string> = {
    watching: "#3db67a",
    completed: "#6366f1",
    plan_to_watch: "#d4a843",
    on_hold: "#f59e0b",
    dropped: "#ef4444",
};

export default function ProfilePage({ user, onAnimeClick, onClose, onUserUpdate }: ProfilePageProps) {
    const [activeTab, setActiveTab] = useState<"watchlist" | "favorites">("watchlist");
    const [statusFilter, setStatusFilter] = useState<string>("");
    const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
    const [favorites, setFavorites] = useState<WatchlistItem[]>([]);
    const [loading, setLoading] = useState(true);
    const [stats, setStats] = useState(user.stats || { watchlist: 0, favorites: 0, comments: 0 });
    const [avatarUrl, setAvatarUrl] = useState(user.avatar_url || "");
    const [uploading, setUploading] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    // Fetch live stats + avatar on mount
    useEffect(() => {
        const fetchStats = async () => {
            try {
                const me = await getMe();
                if (me.stats) setStats(me.stats);
                if (me.avatar_url) setAvatarUrl(me.avatar_url);
            } catch { /* use cached stats */ }
        };
        fetchStats();
    }, []);

    useEffect(() => {
        loadData();
    }, [activeTab, statusFilter]);

    const loadData = async () => {
        setLoading(true);
        try {
            if (activeTab === "watchlist") {
                const data = await getWatchlist(statusFilter || undefined);
                setWatchlist(data);
                // Update live watchlist count when viewing all
                if (!statusFilter) setStats(prev => ({ ...prev, watchlist: data.length }));
            } else {
                const data = await getFavorites();
                setFavorites(data);
                // Update live favorites count
                setStats(prev => ({ ...prev, favorites: data.length }));
            }
        } catch (err) {
            console.error("Failed to load data:", err);
        } finally {
            setLoading(false);
        }
    };

    const handleRemove = async (animeId: number) => {
        try {
            if (activeTab === "watchlist") {
                await removeFromWatchlist(animeId);
                setWatchlist(watchlist.filter((w) => w.anime_id !== animeId));
            }
        } catch (err) {
            console.error("Failed to remove:", err);
        }
    };

    const handleStatusChange = async (animeId: number, newStatus: string) => {
        try {
            await updateWatchlistStatus(animeId, newStatus);
            setWatchlist(watchlist.map((w) =>
                w.anime_id === animeId ? { ...w, status: newStatus } : w
            ));
        } catch (err) {
            console.error("Failed to update status:", err);
        }
    };

    const items = activeTab === "watchlist" ? watchlist : favorites;

    return (
        <div className="profile-overlay" onClick={onClose}>
            <div className="profile-page" onClick={(e) => e.stopPropagation()}>
                <button className="profile-close" onClick={onClose}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                </button>

                {/* Profile Header */}
                <div className="profile-header">
                    <div
                        className="profile-avatar-large clickable"
                        onClick={() => fileInputRef.current?.click()}
                        title="Click to change avatar"
                    >
                        {avatarUrl ? (
                            <img src={avatarUrl} alt={user.username} className="profile-avatar-img" />
                        ) : (
                            user.username[0].toUpperCase()
                        )}
                        <div className="avatar-upload-overlay">
                            {uploading ? (
                                <div className="spinner" style={{ width: 20, height: 20 }} />
                            ) : (
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z" />
                                    <circle cx="12" cy="13" r="4" />
                                </svg>
                            )}
                        </div>
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept="image/jpeg,image/png,image/gif,image/webp"
                            style={{ display: 'none' }}
                            onChange={async (e) => {
                                const file = e.target.files?.[0];
                                if (!file) return;
                                if (file.size > 500 * 1024) {
                                    alert("Image must be under 500KB");
                                    return;
                                }
                                setUploading(true);
                                try {
                                    const res = await uploadAvatar(file);
                                    setAvatarUrl(res.avatar_url);
                                    // Update parent state so navbar reflects new avatar
                                    if (onUserUpdate) {
                                        onUserUpdate({ ...user, avatar_url: res.avatar_url });
                                    }
                                } catch (err) {
                                    console.error("Upload failed:", err);
                                    alert("Failed to upload avatar. Make sure the image is under 500KB.");
                                } finally {
                                    setUploading(false);
                                    e.target.value = "";
                                }
                            }}
                        />
                    </div>
                    <div className="profile-info">
                        <h2 className="profile-username">{user.username}</h2>
                        <p className="profile-email">{user.email}</p>
                        <div className="profile-stats">
                            <div className="profile-stat">
                                <span className="profile-stat-value">{stats.watchlist}</span>
                                <span className="profile-stat-label">Watchlist</span>
                            </div>
                            <div className="profile-stat">
                                <span className="profile-stat-value">{stats.favorites}</span>
                                <span className="profile-stat-label">Favorites</span>
                            </div>
                            <div className="profile-stat">
                                <span className="profile-stat-value">{stats.comments}</span>
                                <span className="profile-stat-label">Comments</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Tabs */}
                <div className="profile-tabs">
                    <button
                        className={`profile-tab ${activeTab === "watchlist" ? "active" : ""}`}
                        onClick={() => setActiveTab("watchlist")}
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="3" y="3" width="7" height="7" /><rect x="14" y="3" width="7" height="7" />
                            <rect x="14" y="14" width="7" height="7" /><rect x="3" y="14" width="7" height="7" />
                        </svg>
                        Watchlist
                    </button>
                    <button
                        className={`profile-tab ${activeTab === "favorites" ? "active" : ""}`}
                        onClick={() => setActiveTab("favorites")}
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" />
                        </svg>
                        Favorites
                    </button>
                </div>

                {/* Status Filters (watchlist only) */}
                {activeTab === "watchlist" && (
                    <div className="profile-status-filters">
                        <button
                            className={`status-chip ${!statusFilter ? "active" : ""}`}
                            onClick={() => setStatusFilter("")}
                        >
                            All
                        </button>
                        {Object.entries(STATUS_LABELS).map(([key, label]) => (
                            <button
                                key={key}
                                className={`status-chip ${statusFilter === key ? "active" : ""}`}
                                style={statusFilter === key ? { borderColor: STATUS_COLORS[key], color: STATUS_COLORS[key] } : {}}
                                onClick={() => setStatusFilter(key)}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                )}

                {/* Content */}
                <div className="profile-content">
                    {loading ? (
                        <div className="profile-loading">
                            <div className="spinner" />
                        </div>
                    ) : items.length === 0 ? (
                        <div className="profile-empty">
                            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1">
                                <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" />
                            </svg>
                            <p>{activeTab === "watchlist" ? "Your watchlist is empty" : "No favorites yet"}</p>
                            <span>Start exploring anime to build your collection!</span>
                        </div>
                    ) : (
                        <div className="profile-grid">
                            {items.map((item) => (
                                <div key={item.id} className="profile-card">
                                    <div
                                        className="profile-card-image"
                                        style={{ backgroundImage: `url(${item.anime_image})` }}
                                        onClick={() => onAnimeClick(item.anime_id)}
                                    />
                                    <div className="profile-card-info">
                                        <h4
                                            className="profile-card-title"
                                            onClick={() => onAnimeClick(item.anime_id)}
                                        >
                                            {item.anime_title}
                                        </h4>
                                        {activeTab === "watchlist" && (
                                            <div className="profile-card-actions">
                                                <select
                                                    value={item.status}
                                                    onChange={(e) => handleStatusChange(item.anime_id, e.target.value)}
                                                    className="profile-status-select"
                                                    style={{ color: STATUS_COLORS[item.status] || "#8a8a8a" }}
                                                >
                                                    {Object.entries(STATUS_LABELS).map(([key, label]) => (
                                                        <option key={key} value={key}>{label}</option>
                                                    ))}
                                                </select>
                                                <button
                                                    className="profile-card-remove"
                                                    onClick={() => handleRemove(item.anime_id)}
                                                    title="Remove"
                                                >
                                                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                                                    </svg>
                                                </button>
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
