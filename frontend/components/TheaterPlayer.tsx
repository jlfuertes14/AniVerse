"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type Hls from "hls.js";
import type { SubtitleTrack } from "@/lib/types";

interface TheaterPlayerProps {
    embedUrl?: string;
    streamUrl?: string;
    refererUrl?: string;
    subtitles?: SubtitleTrack[];
    thumbnailUrl?: string;
    title?: string;
    provider?: string;
    episodeNumber?: number;
    isFromLatest?: boolean;
    forceDirectPlayback?: boolean;
}

function getSiteReferer(url?: string) {
    if (!url) return "";

    try {
        const parsed = new URL(url);
        return `${parsed.protocol}//${parsed.host}/`;
    } catch {
        return "";
    }
}

function buildProxyUrl(url: string, referer?: string) {
    const params = new URLSearchParams({ url });
    if (referer) {
        params.set("referer", referer);
    }
    const apiBase = process.env.NEXT_PUBLIC_API_URL || "";
    if (apiBase) {
        return `${apiBase.replace(/\/$/, "")}/proxy?${params.toString()}`;
    }
    return `/api/proxy?${params.toString()}`;
}

function isHlsStream(url?: string) {
    if (!url) return false;
    const lower = url.toLowerCase();
    return lower.includes(".m3u8") || lower.includes("mpegurl");
}

function isKwikUrl(url?: string) {
    return Boolean(url && url.toLowerCase().includes("kwik."));
}

function isValidEmbedUrl(url?: string) {
    if (!url) return false;
    const lower = url.toLowerCase();
    if (lower.includes("kwik.")) return false;
    if (lower.includes("theanimecommunity.com/embed-widget")) return false;
    return true;
}

export default function TheaterPlayer({
    embedUrl,
    streamUrl,
    subtitles = [],
    refererUrl,
    thumbnailUrl,
    title,
    provider,
    episodeNumber,
    isFromLatest = false,
    forceDirectPlayback = false,
}: TheaterPlayerProps) {
    const videoRef = useRef<HTMLVideoElement | null>(null);
    const hlsRef = useRef<Hls | null>(null);
    const hasStartedPlaybackRef = useRef(false);
    const [playerActive, setPlayerActive] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [errorMessage, setErrorMessage] = useState("");
    const [playbackMode, setPlaybackMode] = useState<"embed" | "direct">("direct");

    const streamReferer = useMemo(() => {
        if (refererUrl) {
            return refererUrl;
        }
        if (provider === "animepahe" || streamUrl?.includes("owocdn.top") || isKwikUrl(streamUrl)) {
            return "https://kwik.cx/";
        }
        if (provider === "reanime") {
            return "https://reanime.to/";
        }
        return getSiteReferer(embedUrl) || getSiteReferer(streamUrl);
    }, [embedUrl, refererUrl, streamUrl, provider]);

    const resolvedStreamUrl = useMemo(() => {
        if (!streamUrl) return "";
        if (forceDirectPlayback) return streamUrl;
        return buildProxyUrl(streamUrl, streamReferer);
    }, [forceDirectPlayback, streamReferer, streamUrl]);

    const proxiedSubtitles = useMemo(() => {
        return subtitles.map((subtitle) => ({
            ...subtitle,
            proxiedUrl: subtitle.url
                ? (forceDirectPlayback ? subtitle.url : buildProxyUrl(subtitle.url, streamReferer))
                : subtitle.url,
        }));
    }, [forceDirectPlayback, streamReferer, subtitles]);

    const useHlsPlayback = useMemo(() => isHlsStream(streamUrl), [streamUrl]);
    const hasEmbedPlayback = isValidEmbedUrl(embedUrl);
    const hasDirectPlayback = Boolean(resolvedStreamUrl);
    const preferEmbedPlayback = provider === "reanime" && hasEmbedPlayback;
    const resolvedEmbedUrl = useMemo(() => {
        return embedUrl || "";
    }, [embedUrl]);
    const activePlaybackMode =
        playbackMode === "embed" && hasEmbedPlayback
            ? "embed"
            : hasDirectPlayback
                ? "direct"
                : hasEmbedPlayback
                    ? "embed"
                    : "direct";

    useEffect(() => {
        if (preferEmbedPlayback) {
            setPlaybackMode("embed");
            return;
        }

        if (hasDirectPlayback) {
            setPlaybackMode("direct");
            return;
        }

        if (hasEmbedPlayback) {
            setPlaybackMode("embed");
        }
    }, [hasDirectPlayback, hasEmbedPlayback, preferEmbedPlayback]);

    useEffect(() => {
        return () => {
            hlsRef.current?.destroy();
            hlsRef.current = null;
        };
    }, []);

    useEffect(() => {
        setErrorMessage("");
        setIsLoading(false);
        hasStartedPlaybackRef.current = false;
        hlsRef.current?.destroy();
        hlsRef.current = null;
    }, [embedUrl, streamUrl]);

    useEffect(() => {
        if (!playerActive || activePlaybackMode !== "direct" || !resolvedStreamUrl) return;
        const video = videoRef.current;
        if (!video) return;

        let cancelled = false;

        const cleanupVideo = () => {
            video.pause();
            video.removeAttribute("src");
            video.load();
        };

        const handlePlaying = () => {
            if (!cancelled) {
                hasStartedPlaybackRef.current = true;
                setIsLoading(false);
                setErrorMessage("");
            }
        };

        const handleWaiting = () => {
            if (!cancelled && !hasStartedPlaybackRef.current) {
                setIsLoading(true);
            }
        };

        const handleCanPlay = () => {
            if (!cancelled) {
                setIsLoading(false);
            }
        };

        const handleLoadedData = () => {
            if (!cancelled) {
                hasStartedPlaybackRef.current = true;
                setIsLoading(false);
            }
        };

        const handleError = () => {
            if (!cancelled) {
                setIsLoading(false);
                setErrorMessage("We couldn't load this stream. Try reloading or use the backup server.");
            }
        };

        video.addEventListener("playing", handlePlaying);
        video.addEventListener("waiting", handleWaiting);
        video.addEventListener("canplay", handleCanPlay);
        video.addEventListener("loadeddata", handleLoadedData);
        video.addEventListener("error", handleError);

        const loadStream = async () => {
            setIsLoading(true);
            setErrorMessage("");
            cleanupVideo();

            if (!useHlsPlayback) {
                video.src = resolvedStreamUrl;
                try {
                    await video.play();
                } catch {
                    // Ignore autoplay rejections after user activation changes.
                }
                return;
            }

            if (video.canPlayType("application/vnd.apple.mpegurl")) {
                video.src = resolvedStreamUrl;
                try {
                    await video.play();
                } catch {
                    // Ignore autoplay rejections after user activation changes.
                }
                return;
            }

            try {
                const hlsModule = await import("hls.js");
                const HlsCtor = hlsModule.default;

                if (!HlsCtor.isSupported()) {
                    setIsLoading(false);
                    setErrorMessage("Your browser doesn't support this video format.");
                    return;
                }

                const hls = new HlsCtor({
                    enableWorker: true,
                    lowLatencyMode: false,
                });

                hlsRef.current = hls;
                hls.attachMedia(video);

                hls.on(HlsCtor.Events.MEDIA_ATTACHED, () => {
                    if (cancelled) return;
                    hls.loadSource(resolvedStreamUrl);
                });

                hls.on(HlsCtor.Events.MANIFEST_PARSED, async () => {
                    if (cancelled) return;
                    try {
                        await video.play();
                    } catch {
                        // Ignore autoplay rejections after user activation changes.
                    }
                });

                hls.on(HlsCtor.Events.ERROR, (_event, data) => {
                    if (!data?.fatal || cancelled) return;

                    if (data.type === HlsCtor.ErrorTypes.NETWORK_ERROR) {
                        hls.startLoad();
                        return;
                    }

                    if (data.type === HlsCtor.ErrorTypes.MEDIA_ERROR) {
                        hls.recoverMediaError();
                        return;
                    }

                    setIsLoading(false);
                    setErrorMessage("This source failed to load. Try refreshing or switching to the backup server.");
                    hls.destroy();
                    hlsRef.current = null;
                });
            } catch {
                setIsLoading(false);
                setErrorMessage("The player couldn't initialize this stream.");
            }
        };

        void loadStream();

        return () => {
            cancelled = true;
            video.removeEventListener("playing", handlePlaying);
            video.removeEventListener("waiting", handleWaiting);
            video.removeEventListener("canplay", handleCanPlay);
            video.removeEventListener("loadeddata", handleLoadedData);
            video.removeEventListener("error", handleError);
            hlsRef.current?.destroy();
            hlsRef.current = null;
            cleanupVideo();
        };
    }, [activePlaybackMode, playerActive, resolvedStreamUrl, useHlsPlayback]);

    if (!playerActive) {
        return (
            <div className="theater-player">
                <button
                    type="button"
                    className="theater-overlay"
                    onClick={() => setPlayerActive(true)}
                    aria-label={`Play ${title || "video"}`}
                >
                    <div
                        className="theater-backdrop"
                        style={thumbnailUrl ? { backgroundImage: `url(${thumbnailUrl})` } : undefined}
                    />
                    <div className="theater-play">
                        <svg viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
                            <path d="M8 5v14l11-7z" />
                        </svg>
                    </div>
                </button>
            </div>
        );
    }

    if (activePlaybackMode === "direct" && resolvedStreamUrl) {
        return (
            <div className="theater-player hls-mode">
                <video
                    ref={videoRef}
                    className="theater-video"
                    poster={thumbnailUrl}
                    controls
                    playsInline
                    preload="metadata"
                    crossOrigin="anonymous"
                    title={title}
                >
                    {proxiedSubtitles.map((sub, idx) => (
                        <track
                            key={sub.proxiedUrl || `${sub.label}-${idx}`}
                            src={sub.proxiedUrl}
                            label={sub.label}
                            srcLang={sub.lang}
                            kind="subtitles"
                            default={sub.lang === "en" || idx === 0}
                        />
                    ))}
                </video>

                {isLoading && (
                    <div className="theater-status">
                        <span>Loading stream...</span>
                    </div>
                )}
                
                {isFromLatest && episodeNumber && (
                    <div className="theater-ep-badge">
                        Episode {episodeNumber}
                    </div>
                )}

                {errorMessage && (
                    <div className="theater-error">
                        <p>{errorMessage}</p>
                        {hasEmbedPlayback && (
                            <button
                                type="button"
                                className="theater-error-link"
                                onClick={() => {
                                    hlsRef.current?.destroy();
                                    hlsRef.current = null;
                                    setIsLoading(false);
                                    setErrorMessage("");
                                    setPlaybackMode("embed");
                                }}
                            >
                                Open backup server
                            </button>
                        )}
                    </div>
                )}
            </div>
        );
    }

    if (!hasDirectPlayback && !hasEmbedPlayback) {
        return (
            <div className="theater-player hls-mode">
                <div className="theater-status">
                    <span>Refreshing direct stream...</span>
                </div>
                <div className="theater-error">
                    <p>This AnimePahe link needs a fresh HLS stream. Try again in a few seconds or switch server.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="theater-player iframe-mode">
            {hasDirectPlayback && (
                <div className="watch-controls" style={{ marginBottom: "0.75rem" }}>
                    <div className="watch-control-group">
                        {hasEmbedPlayback && (
                            <button
                                type="button"
                                className={`watch-control-btn ${activePlaybackMode === "embed" ? "active" : ""}`}
                                onClick={() => setPlaybackMode("embed")}
                            >
                                {provider === "reanime" ? "FlixCloud Embed" : "Kwik Embed"}
                            </button>
                        )}
                        <button
                            type="button"
                            className={`watch-control-btn ${activePlaybackMode === "direct" ? "active" : ""}`}
                            onClick={() => setPlaybackMode("direct")}
                        >
                            Direct Stream
                        </button>
                    </div>
                </div>
            )}
            <iframe
                src={resolvedEmbedUrl || embedUrl}
                className="theater-iframe"
                allowFullScreen
                sandbox="allow-forms allow-pointer-lock allow-same-origin allow-scripts"
                title={title}
            />
        </div>
    );
}
