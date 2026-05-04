"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Navbar from "@/components/Navbar";
import AuthModal from "@/components/AuthModal";
import FilterPanel from "@/components/FilterPanel";
import { clearAuth, getStoredUser, isLoggedIn } from "@/lib/auth";
import type { User } from "@/lib/auth";
import { getMe, getWaifuImage } from "@/lib/api";

export default function WatchNavbar() {
    const router = useRouter();
    const [currentUser, setCurrentUser] = useState<User | null>(null);
    const [showAuthModal, setShowAuthModal] = useState(false);
    const [mascotUrl, setMascotUrl] = useState("");
    const [isFilterOpen, setIsFilterOpen] = useState(false);

    useEffect(() => {
        const stored = getStoredUser();
        if (stored && isLoggedIn()) {
            setCurrentUser(stored);
            getMe().then(setCurrentUser).catch(() => {
                clearAuth();
                setCurrentUser(null);
            });
        } else {
            setCurrentUser(null);
        }

        getWaifuImage("waifu").then(setMascotUrl).catch(() => {});
    }, []);

    const navigateHomeWithParams = (params: Record<string, string>) => {
        const query = new URLSearchParams(params);
        router.push(`/?${query.toString()}`);
    };

    const handleFilterApply = useCallback((filters: {
        genres: string;
        year_from?: number;
        year_to?: number;
        status?: string;
        rating?: string;
    }) => {
        const query = new URLSearchParams();
        if (filters.genres) query.set("genres", filters.genres);
        if (filters.year_from) query.set("year_from", String(filters.year_from));
        if (filters.year_to) query.set("year_to", String(filters.year_to));
        if (filters.status) query.set("status", filters.status);
        if (filters.rating) query.set("rating", filters.rating);
        router.push(`/?${query.toString()}`);
    }, [router]);

    return (
        <>
            <Navbar
                onSearch={(query) => navigateHomeWithParams({ q: query })}
                onSearchResultSelect={(anime) => router.push(`/watch/${anime.mal_id || anime.id}/1`)}
                onFilterToggle={() => setIsFilterOpen(true)}
                onScreenshotClick={() => navigateHomeWithParams({ screenshot: "1" })}
                onRandomClick={() => navigateHomeWithParams({ random: "1" })}
                onVibesClick={() => navigateHomeWithParams({ vibes: "1" })}
                onLogoClick={() => router.push("/")}
                onLoginClick={() => setShowAuthModal(true)}
                onProfileClick={() => router.push("/profile")}
                onLogout={() => {
                    clearAuth();
                    setCurrentUser(null);
                    window.location.reload();
                }}
                onCategoryClick={(type) => navigateHomeWithParams({ type })}
                currentUser={currentUser}
                mascotUrl={mascotUrl}
            />

            <FilterPanel
                isOpen={isFilterOpen}
                onClose={() => setIsFilterOpen(false)}
                onApply={handleFilterApply}
            />

            {showAuthModal && (
                <AuthModal
                    onClose={() => setShowAuthModal(false)}
                    onAuthSuccess={(user) => {
                        setCurrentUser(user);
                        window.location.reload();
                    }}
                />
            )}
        </>
    );
}
