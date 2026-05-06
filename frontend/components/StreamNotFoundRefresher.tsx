"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

interface StreamNotFoundRefresherProps {
    malId: string;
    pollIntervalSeconds?: number;
    maxWaitSeconds?: number;
}

export default function StreamNotFoundRefresher({
    malId,
    pollIntervalSeconds = 20,
    maxWaitSeconds = 120,
}: StreamNotFoundRefresherProps) {
    const router = useRouter();
    const pathname = usePathname();
    const countdownStorageKey = `stream-notfound-start:${pathname}`;
    const [secondsLeft, setSecondsLeft] = useState(maxWaitSeconds);
    const [isRefreshing, setIsRefreshing] = useState(true);

    useEffect(() => {
        if (typeof window === "undefined") return;

        const now = Date.now();
        const savedStartAt = window.sessionStorage.getItem(countdownStorageKey);
        const startAt = savedStartAt ? Number(savedStartAt) : now;

        if (!savedStartAt || Number.isNaN(startAt)) {
            window.sessionStorage.setItem(countdownStorageKey, String(now));
        }

        const getRemainingSeconds = () => {
            const elapsedSeconds = Math.floor((Date.now() - startAt) / 1000);
            return Math.max(maxWaitSeconds - elapsedSeconds, 0);
        };

        setSecondsLeft(getRemainingSeconds());

        const refreshTimer = window.setInterval(() => {
            if (getRemainingSeconds() <= 0) {
                window.clearInterval(refreshTimer);
                setIsRefreshing(false);
                window.sessionStorage.removeItem(countdownStorageKey);
                return;
            }
            router.refresh();
        }, pollIntervalSeconds * 1000);

        const countdownTimer = window.setInterval(() => {
            const remaining = getRemainingSeconds();
            setSecondsLeft(remaining);
            if (remaining <= 0) {
                setIsRefreshing(false);
                window.sessionStorage.removeItem(countdownStorageKey);
            }
        }, 1000);

        return () => {
            window.clearInterval(refreshTimer);
            window.clearInterval(countdownTimer);
        };
    }, [countdownStorageKey, maxWaitSeconds, pollIntervalSeconds, router]);

    return (
        <div className="watch-empty-container">
            <div className="watch-empty-icon">
                <svg viewBox="0 0 24 24" width="48" height="48" fill="currentColor">
                    <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z" />
                </svg>
            </div>
            <h2 className="watch-empty-title">Episode Not Found</h2>
            <p className="watch-empty-text">
                This episode hasn&apos;t been uploaded to our servers yet. Please check back later or try a different source.
            </p>
            {isRefreshing ? (
                <p className="watch-empty-text">
                    Auto-refreshing while the stream prepares ({secondsLeft}s remaining).
                </p>
            ) : (
                <p className="watch-empty-text">
                    Auto-refresh paused. Please try again in a moment.
                </p>
            )}
            <Link href={`/watch/${malId}/1`} className="watch-empty-btn">
                Go to Episode 1
            </Link>
        </div>
    );
}
