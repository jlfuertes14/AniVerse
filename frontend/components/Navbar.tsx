"use client";

import { useState, useEffect, useRef } from "react";
import type { User } from "@/lib/auth";

interface NavbarProps {
    onSearch: (query: string) => void;
    onFilterToggle: () => void;
    onScreenshotClick: () => void;
    onRandomClick: () => void;
    onVibesClick: () => void;
    onLogoClick: () => void;
    onLoginClick: () => void;
    onProfileClick: () => void;
    onLogout: () => void;
    currentUser: User | null;
    mascotUrl: string;
}

export default function Navbar({
    onSearch,
    onFilterToggle,
    onScreenshotClick,
    onRandomClick,
    onVibesClick,
    onLogoClick,
    onLoginClick,
    onProfileClick,
    onLogout,
    currentUser,
    mascotUrl,
}: NavbarProps) {
    const [query, setQuery] = useState("");
    const [showUserMenu, setShowUserMenu] = useState(false);
    const debounceRef = useRef<NodeJS.Timeout | null>(null);
    const menuRef = useRef<HTMLDivElement>(null);

    const handleInput = (value: string) => {
        setQuery(value);
        if (debounceRef.current) clearTimeout(debounceRef.current);
        debounceRef.current = setTimeout(() => {
            if (value.trim()) onSearch(value.trim());
        }, 300);
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === "Enter" && query.trim()) {
            if (debounceRef.current) clearTimeout(debounceRef.current);
            onSearch(query.trim());
        }
    };

    // Close menu on outside click
    useEffect(() => {
        const handler = (e: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
                setShowUserMenu(false);
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

    return (
        <nav className="navbar">
            <div className="navbar-inner">
                <div className="navbar-logo" onClick={onLogoClick}>
                    {mascotUrl ? (
                        <img src={mascotUrl} alt="AniVerse Mascot" className="navbar-mascot" />
                    ) : (
                        <svg viewBox="0 0 24 24" fill="currentColor">
                            <path d="M12 2L1 21h22L12 2zm0 4l7.53 13H4.47L12 6z" opacity="0.3" />
                            <path d="M12 2L1 21h22L12 2zm0 4l7.53 13H4.47L12 6z" />
                        </svg>
                    )}
                    <span className="navbar-brand-text">AniVerse</span>
                </div>

                <div className="navbar-search">
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
                        id="search-input"
                    />
                    <button className="filter-btn" onClick={onFilterToggle}>
                        Filter
                    </button>
                </div>

                <div className="navbar-links">
                    <button className="navbar-link" onClick={onScreenshotClick}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <rect x="3" y="3" width="18" height="18" rx="2" />
                            <circle cx="8.5" cy="8.5" r="1.5" />
                            <path d="M21 15l-5-5L5 21" />
                        </svg>
                        Screenshot
                    </button>
                    <button className="navbar-link" onClick={onRandomClick}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M16 3h5v5M4 20L20.2 3.8M21 16v5h-5M15 15l5.1 5.1M4 4l5 5" />
                        </svg>
                        Random
                    </button>
                    <button className="navbar-link" onClick={onVibesClick}>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M9 18V5l12-2v13" />
                            <circle cx="6" cy="18" r="3" />
                            <circle cx="18" cy="16" r="3" />
                        </svg>
                        Vibes
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
                                    <button className="navbar-dropdown-item" onClick={() => { onProfileClick(); setShowUserMenu(false); }}>
                                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                            <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" /><circle cx="12" cy="7" r="4" />
                                        </svg>
                                        My Profile
                                    </button>
                                    <div className="navbar-dropdown-divider" />
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
