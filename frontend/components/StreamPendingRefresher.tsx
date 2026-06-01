"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { CatalogStatus } from "@/lib/types";

interface StreamPendingRefresherProps {
    pollIntervalSeconds?: number;
    estimateSeconds?: number;
    fallbackAfterSeconds?: number;
    title?: string;
    thumbnailUrl?: string;
    episodeLabel?: string;
    availableEpisodes?: number;
    catalogStatus?: CatalogStatus;
    provider?: string;
}

function formatAiringCountdown(nextAiringAt?: string | null, nextEpisode?: number | null, nowMs: number = 0) {
    if (!nextAiringAt || !nextEpisode || nowMs === 0) return "";
    const targetMs = new Date(nextAiringAt).getTime();
    if (Number.isNaN(targetMs)) return "";

    const diffMs = targetMs - nowMs;
    if (diffMs <= 0) {
        return `Episode ${nextEpisode} should be out soon`;
    }

    const totalMinutes = Math.floor(diffMs / 60000);
    const days = Math.floor(totalMinutes / (60 * 24));
    const hours = Math.floor((totalMinutes % (60 * 24)) / 60);
    const minutes = totalMinutes % 60;

    if (days > 0) return `Episode ${nextEpisode} airs in ${days}d ${hours}h`;
    if (hours > 0) return `Episode ${nextEpisode} airs in ${hours}h ${minutes}m`;
    return `Episode ${nextEpisode} airs in ${Math.max(minutes, 1)}m`;
}

export default function StreamPendingRefresher({
    pollIntervalSeconds = 10,
    estimateSeconds = 90,
    fallbackAfterSeconds = 90,
    title = "Preparing your stream",
    thumbnailUrl = "/placeholder.png",
    episodeLabel = "Episode",
    availableEpisodes,
    catalogStatus,
    provider = "animepahe",
}: StreamPendingRefresherProps) {
    const router = useRouter();
    const pathname = usePathname();
    const searchParams = useSearchParams();
    const countdownStorageKey = `stream-pending-start:${pathname}`;
    const [secondsLeft, setSecondsLeft] = useState(estimateSeconds);
    const [nowMs, setNowMs] = useState(0);
    const [hasTriggeredFallback, setHasTriggeredFallback] = useState(false);

    useEffect(() => {
        if (typeof window === "undefined") return;

        const now = Date.now();
        setNowMs(now);
        const savedStartAt = window.sessionStorage.getItem(countdownStorageKey);
        const startAt = savedStartAt ? Number(savedStartAt) : now;

        if (!savedStartAt || Number.isNaN(startAt)) {
            window.sessionStorage.setItem(countdownStorageKey, String(now));
        }

        const getRemainingSeconds = () => {
            const elapsedSeconds = Math.floor((Date.now() - startAt) / 1000);
            return Math.max(estimateSeconds - elapsedSeconds, 0);
        };

        const getElapsedSeconds = () => Math.floor((Date.now() - startAt) / 1000);

        const refreshTimer = window.setInterval(() => {
            router.refresh();
        }, pollIntervalSeconds * 1000);

        const countdownTimer = window.setInterval(() => {
            setSecondsLeft(getRemainingSeconds());

            if (
                provider === "animepahe" &&
                !hasTriggeredFallback &&
                getElapsedSeconds() >= fallbackAfterSeconds
            ) {
                // AnimePahe fallback also timed out — nothing more to try
                // Keep polling; the background task may still finish
            }
        }, 1000);

        const airingTimer = window.setInterval(() => {
            setNowMs(Date.now());
        }, 60_000);

        return () => {
            window.clearInterval(refreshTimer);
            window.clearInterval(countdownTimer);
            window.clearInterval(airingTimer);
        };
    }, [
        countdownStorageKey,
        estimateSeconds,
        fallbackAfterSeconds,
        hasTriggeredFallback,
        pathname,
        pollIntervalSeconds,
        provider,
        router,
        searchParams,
    ]);

    const nextAiringCountdown = formatAiringCountdown(
        catalogStatus?.next_airing_at,
        catalogStatus?.next_airing_episode,
        nowMs,
    );

    const providerName = provider.charAt(0).toUpperCase() + provider.slice(1).replace("reanime", "Re:ANIME");

    return (
        <section className="stream-pending-card" aria-live="polite">
            <div className="stream-pending-visual">
                <div className="stream-pending-orbit-wrap">
                    <div className="stream-pending-orbit stream-pending-orbit-one" />
                    <div className="stream-pending-orbit stream-pending-orbit-two" />
                    <div className="stream-pending-portrait-frame">
                        <img
                            src={thumbnailUrl || "/placeholder.png"}
                            alt={title}
                            className="stream-pending-portrait"
                        />
                    </div>
                </div>
                <div className="stream-pending-badge">Loading...</div>
            </div>

            <div className="stream-pending-copy">
                <div className="stream-pending-kicker">
                    <span className="stream-pending-dot" />
                    Connecting to {providerName} server
                </div>
                <h2 className="stream-pending-title">{title}</h2>
                <p className="stream-pending-episode">{episodeLabel}</p>
                <p className="stream-pending-text">
                    We&apos;re getting this episode ready for playback from {providerName}. Please hold on while we prepare the stream.
                </p>

                <div className="stream-pending-stats">
                    <div className="stream-pending-stat">
                        <span className="stream-pending-stat-label">Estimated wait</span>
                        <strong>{secondsLeft > 0 ? `${secondsLeft}s` : "Almost ready"}</strong>
                    </div>
                    <div className="stream-pending-stat">
                        <span className="stream-pending-stat-label">Now doing</span>
                        <strong>Scraping {providerName}</strong>
                    </div>
                    <div className="stream-pending-stat">
                        <span className="stream-pending-stat-label">Episodes found</span>
                        <strong>{availableEpisodes ?? "..."}</strong>
                    </div>
                </div>

                {catalogStatus && (
                    <div className="stream-pending-meta">
                        {catalogStatus.latest_episode ? (
                            <span>Latest known episode: {catalogStatus.latest_episode}</span>
                        ) : null}
                        {nextAiringCountdown ? (
                            <span>{nextAiringCountdown}</span>
                        ) : null}
                        {catalogStatus.last_checked_at ? (
                            <span>Last checked: {new Date(catalogStatus.last_checked_at).toLocaleString()}</span>
                        ) : null}
                        {catalogStatus.next_airing_at ? (
                            <span>Next episode drops on {new Date(catalogStatus.next_airing_at).toLocaleString()}</span>
                        ) : null}
                    </div>
                )}

                <div className="stream-pending-progress" aria-hidden="true">
                    <span />
                </div>

                <p className="stream-pending-hint">
                    We check again every {pollIntervalSeconds}s in the background and will load the player as soon as the stream is ready.
                </p>
            </div>
        </section>
    );
}
