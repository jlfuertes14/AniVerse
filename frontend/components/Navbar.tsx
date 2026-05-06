"use client";

import { useState, useEffect, useRef } from "react";
import { searchAnime } from "@/lib/api";
import type { User } from "@/lib/auth";
import type { Anime } from "@/lib/types";

interface NavbarProps {
    onSearch: (query: string) => void;
    onSearchResultSelect?: (anime: Anime) => void;
    onFilterToggle: () => void;
    onScreenshotClick: () => void;
    onRandomClick: () => void;
    onVibesClick: () => void;
    onLogout: () => void;
    onAISearchClick: () => void;
    onLogoClick: () => void;
    onLoginClick: () => void;
    onProfileClick: () => void;
    onCategoryClick: (type: string) => void;
    activeCategory?: string | null;
    isAIActive?: boolean;
    activeVibe?: string | null;
    showScreenshot?: boolean;
    isRandomActive?: boolean;
    showProfileLink?: boolean;
    currentUser: User | null;
    mascotUrl: string;
}

export default function Navbar({
    onSearch,
    onSearchResultSelect,
    onFilterToggle,
    onScreenshotClick,
    onRandomClick,
    onVibesClick,
    onLogout,
    onAISearchClick,
    onLogoClick,
    onLoginClick,
    onProfileClick,
    onCategoryClick,
    activeCategory,
    isAIActive,
    activeVibe,
    showScreenshot,
    isRandomActive,
    showProfileLink = true,
    currentUser,
    mascotUrl,
}: NavbarProps) {
    const [query, setQuery] = useState("");
    const [suggestions, setSuggestions] = useState<Anime[]>([]);
    const [showSuggestions, setShowSuggestions] = useState(false);
    const [isSearchingSuggestions, setIsSearchingSuggestions] = useState(false);
    const [showUserMenu, setShowUserMenu] = useState(false);
    const [theme, setTheme] = useState<"dark" | "light">("dark");
    const debounceRef = useRef<NodeJS.Timeout | null>(null);
    const menuRef = useRef<HTMLDivElement>(null);
    const searchRef = useRef<HTMLDivElement>(null);

    const handleInput = (value: string) => {
        setQuery(value);
        if (debounceRef.current) clearTimeout(debounceRef.current);

        const trimmed = value.trim();
        if (!trimmed) {
            setSuggestions([]);
            setShowSuggestions(false);
            setIsSearchingSuggestions(false);
            return;
        }

        setIsSearchingSuggestions(true);
        debounceRef.current = setTimeout(async () => {
            try {
                const data = await searchAnime({ query: trimmed, page: 1 });
                setSuggestions(data.data?.slice(0, 8) || []);
                setShowSuggestions(true);
            } catch (error) {
                console.error("Suggestion search failed:", error);
                setSuggestions([]);
                setShowSuggestions(false);
            } finally {
                setIsSearchingSuggestions(false);
            }
        }, 250);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && query.trim()) {
            e.preventDefault();
            if (debounceRef.current) clearTimeout(debounceRef.current);
            setShowSuggestions(false);
            onSearch(query.trim());
        } else if (e.key === "Escape") {
            setShowSuggestions(false);
        }
    };

    const handleSuggestionSelect = (anime: Anime) => {
        setQuery(anime.title_english || anime.title);
        setShowSuggestions(false);
        if (onSearchResultSelect) {
            onSearchResultSelect(anime);
            return;
        }
        onSearch(anime.title_english || anime.title);
    };

    // Close menu on outside click
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setShowUserMenu(false);
            }
            if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
                setShowSuggestions(false);
            }
        };
        document.addEventListener("mousedown", handler);
        return () => document.removeEventListener("mousedown", handler);
    }, []);

    useEffect(() => {
        return () => {
            if (debounceRef.current) clearTimeout(debounceRef.current);
        };
    }, []);

    useEffect(() => {
        const savedTheme = typeof window !== "undefined"
            ? window.localStorage.getItem("aniverse-theme")
            : null;
        const nextTheme = savedTheme === "light" ? "light" : "dark";
        setTheme(nextTheme);
        document.documentElement.dataset.theme = nextTheme;
    }, []);

    const handleThemeToggle = () => {
        const nextTheme = theme === "dark" ? "light" : "dark";
        setTheme(nextTheme);
        document.documentElement.dataset.theme = nextTheme;
        window.localStorage.setItem("aniverse-theme", nextTheme);
    };

    return (
        <nav className="navbar">
            <div className="navbar-inner" suppressHydrationWarning>
                <div className="navbar-logo" onClick={onLogoClick}>
                    <img 
                        src="/asuna-yuuki.png" 
                        alt="AniVerse Mascot" 
                        className="navbar-mascot" 
                    />
                    <span className="navbar-brand-text">AniVerse</span>
                </div>

                <div className="navbar-search" ref={searchRef}>
                    <div className="navbar-search-box">
                        <svg className="navbar-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="11" cy="11" r="8" />
                            <line x1="21" y1="21" x2="16.65" y2="16.65" />
                        </svg>
                        <input
                            type="text"
                            placeholder="Search anime..."
                            value={query}
                            onChange={(e) => handleInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            onFocus={() => {
                                if (suggestions.length) setShowSuggestions(true);
                            }}
                            id="search-input"
                        />
                    </div>
                    <button className="filter-btn" onClick={onFilterToggle}>
                        Filter
                    </button>
                    {showSuggestions && (
                        <div className="navbar-search-dropdown">
                            {isSearchingSuggestions && (
                                <div className="navbar-search-empty">Searching...</div>
                            )}
                            {!isSearchingSuggestions && suggestions.length === 0 && (
                                <div className="navbar-search-empty">No matches found.</div>
                            )}
                            {!isSearchingSuggestions && suggestions.map((anime) => (
                                <button
                                    key={anime.id}
                                    type="button"
                                    className="navbar-search-item"
                                    onClick={() => handleSuggestionSelect(anime)}
                                >
                                    <img
                                        src={anime.image_url || anime.large_image_url || "/placeholder.png"}
                                        alt={anime.title}
                                        className="navbar-search-thumb"
                                    />
                                    <div className="navbar-search-meta">
                                        <div className="navbar-search-title">{anime.title_english || anime.title}</div>
                                        <div className="navbar-search-subtitle">
                                            {anime.type || "TV"}
                                            {anime.episodes ? ` - ${anime.episodes} Episodes` : ""}
                                            {anime.status ? ` (${anime.status})` : ""}
                                        </div>
                                        <div className="navbar-search-subtitle">
                                            {anime.season ? `${anime.season} ` : ""}
                                            {anime.year || ""}
                                        </div>
                                    </div>
                                </button>
                            ))}
                        </div>
                    )}
                </div>

                <div className="navbar-quick-actions">
                    <button 
                        className={`navbar-link ai-discovery-btn ${isAIActive ? "active" : ""}`} 
                        onClick={onAISearchClick}
                        title="AI Discovery Search"
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z" />
                            <path d="M5 3v4" />
                            <path d="M3 5h4" />
                            <path d="M21 17v4" />
                            <path d="M19 19h4" />
                        </svg>
                        AI Search
                    </button>
                    <button 
                        className={`navbar-link ${activeCategory === "tv" ? "active" : ""}`} 
                        onClick={() => onCategoryClick("tv")}
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="2" y="7" width="20" height="15" rx="2" ry="2" />
                            <polyline points="17 2 12 7 7 2" />
                        </svg>
                        TV
                    </button>
                    <button 
                        className={`navbar-link ${activeCategory === "movie" ? "active" : ""}`} 
                        onClick={() => onCategoryClick("movie")}
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18" />
                            <line x1="7" y1="2" x2="7" y2="22" />
                            <line x1="17" y1="2" x2="17" y2="22" />
                            <line x1="2" y1="12" x2="22" y2="12" />
                            <line x1="2" y1="7" x2="7" y2="7" />
                            <line x1="2" y1="17" x2="7" y2="17" />
                            <line x1="17" y1="17" x2="22" y2="17" />
                            <line x1="17" y1="7" x2="22" y2="7" />
                        </svg>
                        Movie
                    </button>
                    <button 
                        className={`navbar-link ${showScreenshot ? "active" : ""}`} 
                        onClick={onScreenshotClick}
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="3" y="3" width="18" height="18" rx="2" />
                            <circle cx="8.5" cy="8.5" r="1.5" />
                            <path d="M21 15l-5-5L5 21" />
                        </svg>
                        Screenshot
                    </button>
                    <button 
                        className={`navbar-link ${isRandomActive ? "active" : ""}`} 
                        onClick={onRandomClick}
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M16 3h5v5M4 20L20.2 3.8M21 16v5h-5M15 15l5.1 5.1M4 4l5 5" />
                        </svg>
                        Random
                    </button>
                    <button 
                        className={`navbar-link ${activeVibe ? "active" : ""}`} 
                        onClick={onVibesClick}
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M9 18V5l12-2v13" />
                            <circle cx="6" cy="18" r="3" />
                            <circle cx="18" cy="16" r="3" />
                        </svg>
                        Vibes
                    </button>
                </div>

                <div className="navbar-links">
                    <button className="navbar-link navbar-theme-btn" onClick={handleThemeToggle}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            {theme === "dark" ? (
                                <>
                                    <circle cx="12" cy="12" r="4" />
                                    <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
                                </>
                            ) : (
                                <path d="M21 12.79A9 9 0 1111.21 3c0 0 0 0 0 0A7 7 0 0021 12.79z" />
                            )}
                        </svg>
                        {theme === "dark" ? "Light" : "Dark"}
                    </button>

                    {/* Auth Section */}
                    {currentUser ? (
                        <div className="navbar-user" ref={menuRef}>
                            <button
                                className="navbar-user-btn"
                                onClick={() => setShowUserMenu(!showUserMenu)}
                            >
                                <div className="navbar-user-avatar">
                                    {currentUser.avatar_url ? (
                                        <img src={currentUser.avatar_url} alt={currentUser.username} className="navbar-avatar-img" />
                                    ) : (
                                        currentUser.username[0].toUpperCase()
                                    )}
                                </div>
                                <span className="navbar-user-name">{currentUser.username}</span>
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <polyline points="6 9 12 15 18 9" />
                                </svg>
                            </button>

                            {showUserMenu && (
                                <div className="navbar-dropdown">
                                    {showProfileLink && (
                                        <>
                                            <button className="navbar-dropdown-item" onClick={() => { onProfileClick(); setShowUserMenu(false); }}>
                                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                    <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" /><circle cx="12" cy="7" r="4" />
                                                </svg>
                                                My Profile
                                            </button>
                                            <div className="navbar-dropdown-divider" />
                                        </>
                                    )}
                                    <button className="navbar-dropdown-item navbar-dropdown-logout" onClick={() => { onLogout(); setShowUserMenu(false); }}>
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
                                        </svg>
                                        Logout
                                    </button>
                                </div>
                            )}
                        </div>
                    ) : (
                        <button className="navbar-login-btn" onClick={onLoginClick}>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4M10 17l5-5-5-5M15 12H3" />
                            </svg>
                            Login
                        </button>
                    )}
                </div>
            </div>
        </nav>
    );
}
