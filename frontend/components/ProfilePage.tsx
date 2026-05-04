"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Navbar from "@/components/Navbar";

import {
    getFavorites,
    getMe,
    getWatchlist,
    removeFromWatchlist,
    updateMe,
    updateWatchlistStatus,
    uploadAvatar,
} from "@/lib/api";
import type { WatchlistItem } from "@/lib/api";
import { clearAuth, getStoredUser, getToken, setAuth } from "@/lib/auth";
import type { User } from "@/lib/auth";

const STATUS_LABELS: Record<string, string> = {
    watching: "Watching",
    completed: "Completed",
    plan_to_watch: "Plan to Watch",
    on_hold: "On Hold",
    dropped: "Dropped",
};

const STATUS_COLORS: Record<string, string> = {
    watching: "#3db67a",
    completed: "#5f7cff",
    plan_to_watch: "#d4a843",
    on_hold: "#f59e0b",
    dropped: "#ef4444",
};

type ProfileTab = "watchlist" | "favorites" | "settings";

async function compressAvatarImage(file: File, maxWidth = 720, quality = 0.82): Promise<File> {
    if (typeof window === "undefined") return file;
    if (!file.type.startsWith("image/")) return file;

    const imageUrl = URL.createObjectURL(file);
    try {
        const bitmap = await createImageBitmap(file);
        const ratio = Math.min(1, maxWidth / Math.max(bitmap.width, bitmap.height));
        const canvas = document.createElement("canvas");
        canvas.width = Math.max(1, Math.round(bitmap.width * ratio));
        canvas.height = Math.max(1, Math.round(bitmap.height * ratio));
        const ctx = canvas.getContext("2d");
        if (!ctx) return file;
        ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        bitmap.close();

        const blob = await new Promise<Blob | null>((resolve) => {
            canvas.toBlob(resolve, "image/webp", quality);
        });
        if (!blob) return file;

        return new File([blob], `${file.name.replace(/\.[^.]+$/, "")}.webp`, {
            type: "image/webp",
            lastModified: Date.now(),
        });
    } finally {
        URL.revokeObjectURL(imageUrl);
    }
}

function formatJoinedDate(dateValue?: string) {
    if (!dateValue) return "Recently joined";
    const parsed = new Date(dateValue);
    if (Number.isNaN(parsed.getTime())) return "Recently joined";
    return parsed.toLocaleDateString(undefined, {
        month: "long",
        year: "numeric",
    });
}

export default function ProfilePage() {
    const router = useRouter();
    const searchParams = useSearchParams();
    const tabParam = searchParams.get("tab");
    const initialTab = (tabParam as ProfileTab) || "watchlist";

    const [activeTab, setActiveTab] = useState<ProfileTab>(
        ["watchlist", "favorites", "settings"].includes(initialTab) ? initialTab : "watchlist"
    );
    const [statusFilter, setStatusFilter] = useState<string>("");
    const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
    const [favorites, setFavorites] = useState<WatchlistItem[]>([]);
    const [currentUser, setCurrentUser] = useState<User | null>(getStoredUser());
    const [loading, setLoading] = useState(true);
    const [pageMessage, setPageMessage] = useState("");
    const [avatarUrl, setAvatarUrl] = useState(currentUser?.avatar_url || "");
    const [uploading, setUploading] = useState(false);
    const [savingSettings, setSavingSettings] = useState(false);
    const [settingsMessage, setSettingsMessage] = useState("");
    const [settingsError, setSettingsError] = useState("");
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [settingsForm, setSettingsForm] = useState({
        username: currentUser?.username || "",
        email: currentUser?.email || "",
    });

    useEffect(() => {
        const token = getToken();
        if (!token) {
            setLoading(false);
            return;
        }

        let cancelled = false;
        async function bootstrap() {
            try {
                const me = await getMe();
                if (cancelled) return;
                setCurrentUser(me);
                setAvatarUrl(me.avatar_url || "");
                setSettingsForm({ username: me.username, email: me.email });
            } catch (error) {
                if (cancelled) return;
                clearAuth();
                setCurrentUser(null);
                setPageMessage(error instanceof Error ? error.message : "Unable to load profile.");
            } finally {
                if (!cancelled) {
                    setLoading(false);
                }
            }
        }

        bootstrap();
        return () => {
            cancelled = true;
        };
    }, []);

    useEffect(() => {
        const params = new URLSearchParams(searchParams.toString());
        params.set("tab", activeTab);
        const nextQuery = params.toString();
        if (nextQuery === searchParams.toString()) return;
        router.replace(`/profile?${nextQuery}`, { scroll: false });
    }, [activeTab, router, searchParams]);

    const handleNavSearch = useCallback((value: string) => {
        const params = new URLSearchParams();
        params.set("q", value);
        router.push(`/?${params.toString()}`);
    }, [router]);

    const handleNavFilterToggle = useCallback(() => {
        router.push("/?filter=1");
    }, [router]);

    const handleNavScreenshot = useCallback(() => {
        router.push("/?screenshot=1");
    }, [router]);

    const handleNavRandom = useCallback(() => {
        router.push("/?random=1");
    }, [router]);

    const handleNavVibes = useCallback(() => {
        router.push("/?vibes=1");
    }, [router]);

    const handleNavCategory = useCallback((type: string) => {
        const params = new URLSearchParams();
        params.set("type", type);
        router.push(`/?${params.toString()}`);
    }, [router]);

    useEffect(() => {
        if (!currentUser || activeTab === "settings") {
            setLoading(false);
            return;
        }

        let cancelled = false;
        async function loadCollection() {
            setLoading(true);
            try {
                if (activeTab === "watchlist") {
                    const data = await getWatchlist(statusFilter || undefined);
                    if (!cancelled) setWatchlist(data);
                } else {
                    const data = await getFavorites();
                    if (!cancelled) setFavorites(data);
                }
            } catch (error) {
                if (!cancelled) {
                    setPageMessage(error instanceof Error ? error.message : "Failed to load collection.");
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        }

        loadCollection();
        return () => {
            cancelled = true;
        };
    }, [activeTab, statusFilter, currentUser]);

    const items = activeTab === "favorites" ? favorites : watchlist;
    const joinedLabel = useMemo(() => formatJoinedDate(currentUser?.created_at), [currentUser?.created_at]);

    const handleStatusChange = async (animeId: number, newStatus: string) => {
        try {
            await updateWatchlistStatus(animeId, newStatus);
            setWatchlist((prev) => prev.map((item) => (
                item.anime_id === animeId ? { ...item, status: newStatus } : item
            )));
        } catch (error) {
            setPageMessage(error instanceof Error ? error.message : "Failed to update watch status.");
        }
    };

    const handleRemove = async (animeId: number) => {
        try {
            await removeFromWatchlist(animeId);
            setWatchlist((prev) => prev.filter((item) => item.anime_id !== animeId));
        } catch (error) {
            setPageMessage(error instanceof Error ? error.message : "Failed to remove title.");
        }
    };

    const handleAvatarChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file || !currentUser) return;

        setUploading(true);
        setPageMessage("");
        try {
            const processed = await compressAvatarImage(file);
            const response = await uploadAvatar(processed);
            const updatedUser = { ...currentUser, avatar_url: response.avatar_url };
            setCurrentUser(updatedUser);
            setAvatarUrl(response.avatar_url);
            const token = getToken();
            if (token) setAuth(token, updatedUser);
        } catch (error) {
            setPageMessage(error instanceof Error ? error.message : "Avatar upload failed.");
        } finally {
            setUploading(false);
            event.target.value = "";
        }
    };

    const handleSettingsSave = async (event: React.FormEvent<HTMLFormElement>) => {
        event.preventDefault();
        if (!currentUser) return;

        setSavingSettings(true);
        setSettingsMessage("");
        setSettingsError("");
        try {
            const updated = await updateMe(settingsForm);
            setCurrentUser(updated);
            const token = getToken();
            if (token) setAuth(token, updated);
            setSettingsMessage("Profile settings updated.");
        } catch (error) {
            setSettingsError(error instanceof Error ? error.message : "Failed to save settings.");
        } finally {
            setSavingSettings(false);
        }
    };

    const navbar = (
        <Navbar
            onSearch={handleNavSearch}
            onFilterToggle={handleNavFilterToggle}
            onScreenshotClick={handleNavScreenshot}
            onRandomClick={handleNavRandom}
            onVibesClick={handleNavVibes}
            onLogoClick={() => router.push("/")}
            onLoginClick={() => router.push("/")}
            onProfileClick={() => router.push("/profile")}
            onLogout={() => {
                clearAuth();
                setCurrentUser(null);
            }}
            onCategoryClick={handleNavCategory}
            activeCategory={null}
            activeVibe={null}
            showScreenshot={false}
            isRandomActive={false}
            showProfileLink={false}
            currentUser={currentUser}
            mascotUrl=""
        />
    );

    if (!currentUser && !loading) {
        return (
            <>
                {navbar}
                <section className="profile-route-shell">
                    <div className="profile-route-empty">
                        <h1>Sign in to view your profile</h1>
                        <p>{pageMessage || "Your watchlist, favorites, and account settings live here."}</p>
                        <button className="profile-primary-btn" onClick={() => router.push("/")}>
                            Back to Home
                        </button>
                    </div>
                </section>
            </>
        );
    }

    return (
        <>
            {navbar}
            <section className="profile-route-shell">
                <div className="profile-route-hero">
                    <div className="profile-route-identity">
                        <button
                            type="button"
                            className="profile-avatar-hero"
                            onClick={() => fileInputRef.current?.click()}
                            title="Upload a new avatar"
                        >
                            {avatarUrl ? (
                                <img src={avatarUrl} alt={currentUser?.username || "Profile"} className="profile-avatar-img" />
                            ) : (
                                currentUser?.username?.[0]?.toUpperCase()
                            )}
                            <span className="profile-avatar-badge">{uploading ? "Saving..." : "Edit"}</span>
                        </button>
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept="image/jpeg,image/png,image/gif,image/webp"
                            style={{ display: "none" }}
                            onChange={handleAvatarChange}
                        />

                        <div className="profile-route-copy">
                            <p className="profile-route-eyebrow">Profile</p>
                            <h1 className="profile-route-title">{currentUser?.username || "Loading..."}</h1>
                            <p className="profile-route-subtitle">{currentUser?.email}</p>
                            <p className="profile-route-meta">Member since {joinedLabel}</p>
                        </div>
                    </div>

                    <div className="profile-route-stats">
                        <div className="profile-route-stat">
                            <strong>{currentUser?.stats?.watchlist ?? watchlist.length}</strong>
                            <span>Watchlist</span>
                        </div>
                        <div className="profile-route-stat">
                            <strong>{currentUser?.stats?.favorites ?? favorites.length}</strong>
                            <span>Favorites</span>
                        </div>
                        <div className="profile-route-stat">
                            <strong>{currentUser?.stats?.comments ?? 0}</strong>
                            <span>Comments</span>
                        </div>
                    </div>
                </div>

                <div className="profile-route-tabs">
                    {(["watchlist", "favorites", "settings"] as ProfileTab[]).map((tab) => (
                        <button
                            key={tab}
                            className={`profile-route-tab ${activeTab === tab ? "active" : ""}`}
                            onClick={() => setActiveTab(tab)}
                        >
                            {tab === "watchlist" ? "Watchlist" : tab === "favorites" ? "Favorites" : "Settings"}
                        </button>
                    ))}
                </div>

                {pageMessage && <div className="profile-route-banner">{pageMessage}</div>}

                {activeTab === "watchlist" && (
                    <div className="profile-route-filters">
                        <button className={`status-chip ${!statusFilter ? "active" : ""}`} onClick={() => setStatusFilter("")}>All</button>
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

                {activeTab === "settings" ? (
                    <div className="profile-settings-panel">
                        <form className="profile-settings-form" onSubmit={handleSettingsSave}>
                            <div className="profile-settings-heading">
                                <h2>Account Settings</h2>
                                <p>Update your profile details and keep uploads lightweight through automatic compression.</p>
                            </div>

                            <label className="profile-settings-field">
                                <span>Username</span>
                                <input
                                    value={settingsForm.username}
                                    onChange={(e) => setSettingsForm((prev) => ({ ...prev, username: e.target.value }))}
                                    placeholder="Your username"
                                />
                            </label>

                            <label className="profile-settings-field">
                                <span>Email</span>
                                <input
                                    type="email"
                                    value={settingsForm.email}
                                    onChange={(e) => setSettingsForm((prev) => ({ ...prev, email: e.target.value }))}
                                    placeholder="you@example.com"
                                />
                            </label>

                            <div className="profile-settings-note">
                                <strong>Avatar uploads</strong>
                                <p>You can choose a larger image file now. We compress it client-side before upload to keep storage lighter.</p>
                            </div>

                            {settingsError && <p className="profile-settings-error">{settingsError}</p>}
                            {settingsMessage && <p className="profile-settings-success">{settingsMessage}</p>}

                            <button className="profile-primary-btn" type="submit" disabled={savingSettings}>
                                {savingSettings ? "Saving..." : "Save Settings"}
                            </button>
                        </form>
                    </div>
                ) : loading ? (
                    <div className="profile-route-loading">Loading your collection...</div>
                ) : items.length === 0 ? (
                    <div className="profile-route-empty">
                        <h2>{activeTab === "watchlist" ? "Your watchlist is empty" : "No favorites yet"}</h2>
                        <p>Start exploring anime and your collection will show up here.</p>
                        <button className="profile-primary-btn" onClick={() => router.push("/")}>
                            Discover Anime
                        </button>
                    </div>
                ) : (
                    <div className="profile-route-grid">
                        {items.map((item) => (
                            <article key={item.id} className="profile-route-card">
                                <button
                                    className="profile-route-card-cover"
                                    style={{ backgroundImage: `url(${item.anime_image})` }}
                                    onClick={() => router.push(`/watch/${item.anime_id}/1`)}
                                />
                                <div className="profile-route-card-body">
                                    <button className="profile-route-card-title" onClick={() => router.push(`/watch/${item.anime_id}/1`)}>
                                        {item.anime_title}
                                    </button>
                                    {activeTab === "watchlist" ? (
                                        <div className="profile-route-card-actions">
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
                                            <button className="profile-card-remove" onClick={() => handleRemove(item.anime_id)} title="Remove">
                                                Remove
                                            </button>
                                        </div>
                                    ) : (
                                        <span className="profile-route-favorite-tag">Favorite</span>
                                    )}
                                </div>
                            </article>
                        ))}
                    </div>
                )}
            </section>
        </>
    );
}
