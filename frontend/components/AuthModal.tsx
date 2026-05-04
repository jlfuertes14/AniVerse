"use client";

import { useState, useEffect } from "react";
import { registerUser, loginUser, getWaifuImage } from "@/lib/api";
import { setAuth } from "@/lib/auth";
import type { User } from "@/lib/auth";

interface AuthModalProps {
    onClose: () => void;
    onAuthSuccess: (user: User) => void;
    prefetchedBanners?: string[];
}

export default function AuthModal({ onClose, onAuthSuccess, prefetchedBanners = [] }: AuthModalProps) {
    const [mode, setMode] = useState<"login" | "register">("login");
    const [username, setUsername] = useState("");
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [loading, setLoading] = useState(false);
    const [bannerUrl, setBannerUrl] = useState("");

    useEffect(() => {
        if (prefetchedBanners.length > 0) {
            const randomBanner = prefetchedBanners[Math.floor(Math.random() * prefetchedBanners.length)];
            setBannerUrl(randomBanner);
        } else {
            getWaifuImage("waifu").then(setBannerUrl).catch(() => {});
        }
    }, [prefetchedBanners]);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError("");
        setLoading(true);

        try {
            let result;
            if (mode === "register") {
                result = await registerUser(username, email, password);
            } else {
                result = await loginUser(email, password);
            }
            setAuth(result.token, result.user);
            onAuthSuccess(result.user);
            onClose();
        } catch (err: any) {
            setError(err.message || "Something went wrong");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="auth-overlay" onClick={onClose}>
            <div className="auth-modal" onClick={(e) => e.stopPropagation()}>
                <div 
                    className="auth-modal-banner" 
                    style={bannerUrl ? { backgroundImage: `url(${bannerUrl})` } : {}}
                ></div>
                <button className="auth-close" onClick={onClose}>
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                    </svg>
                </button>

                <div className="auth-header">
                    <div className="auth-brand">
                        <img 
                            src="/asuna-yuuki.png" 
                            alt="Mascot" 
                            className="auth-mascot"
                        />
                        <span>AniVerse</span>
                    </div>
                    <p className="auth-subtitle">
                        {mode === "login" ? "Welcome back, otaku!" : "Join the community"}
                    </p>
                </div>

                <div className="auth-tabs">
                    <button
                        className={`auth-tab ${mode === "login" ? "active" : ""}`}
                        onClick={() => { setMode("login"); setError(""); }}
                    >
                        Login
                    </button>
                    <button
                        className={`auth-tab ${mode === "register" ? "active" : ""}`}
                        onClick={() => { setMode("register"); setError(""); }}
                    >
                        Register
                    </button>
                </div>

                {error && (
                    <div className="auth-error">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
                        </svg>
                        {error}
                    </div>
                )}

                <form onSubmit={handleSubmit} className="auth-form">
                    {mode === "register" && (
                        <div className="auth-field">
                            <label htmlFor="auth-username">Username</label>
                            <input
                                id="auth-username"
                                type="text"
                                placeholder="Choose a username"
                                value={username}
                                onChange={(e) => setUsername(e.target.value)}
                                required
                                minLength={3}
                                autoComplete="username"
                            />
                        </div>
                    )}

                    <div className="auth-field">
                        <label htmlFor="auth-email">Email</label>
                        <input
                            id="auth-email"
                            type="email"
                            placeholder="your@email.com"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            required
                            autoComplete="email"
                        />
                    </div>

                    <div className="auth-field">
                        <label htmlFor="auth-password">Password</label>
                        <input
                            id="auth-password"
                            type="password"
                            placeholder="••••••••"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            required
                            minLength={6}
                            autoComplete={mode === "register" ? "new-password" : "current-password"}
                        />
                    </div>

                    <button type="submit" className="auth-submit" disabled={loading}>
                        {loading ? (
                            <div className="spinner" style={{ width: 18, height: 18 }} />
                        ) : mode === "login" ? (
                            "Sign In"
                        ) : (
                            "Create Account"
                        )}
                    </button>
                </form>
            </div>
        </div>
    );
}
