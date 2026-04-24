"use client";

import { useState, useCallback, useRef } from "react";
import { searchByScreenshot } from "@/lib/api";
import type { ScreenshotResult } from "@/lib/types";

interface ScreenshotSearchProps {
    isVisible: boolean;
}

export default function ScreenshotSearch({ isVisible }: ScreenshotSearchProps) {
    const [results, setResults] = useState<ScreenshotResult[]>([]);
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [preview, setPreview] = useState<string | null>(null);
    const [dragOver, setDragOver] = useState(false);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFile = useCallback(async (file: File) => {
        if (!file.type.startsWith("image/")) {
            setError("Please upload an image file (PNG, JPG, etc.)");
            return;
        }

        setPreview(URL.createObjectURL(file));
        setLoading(true);
        setError(null);
        setResults([]);

        try {
            const data = await searchByScreenshot(file);
            setResults(data.results || []);
            if (!data.results?.length) {
                setError("No matches found. Try a clearer screenshot!");
            }
        } catch (err) {
            setError("Search failed. Please try again.");
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, []);

    const handleDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            setDragOver(false);
            const file = e.dataTransfer.files[0];
            if (file) handleFile(file);
        },
        [handleFile]
    );

    const handleBrowse = () => fileInputRef.current?.click();

    const getSimilarityClass = (sim: number) => {
        if (sim >= 85) return "high";
        if (sim >= 60) return "medium";
        return "low";
    };

    const formatTimestamp = (seconds: number | null | undefined) => {
        if (!seconds) return "N/A";
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, "0")}`;
    };

    if (!isVisible) return null;

    return (
        <section className="screenshot-section container" id="screenshot-section">
            <h2 className="section-heading">📸 Screenshot Search</h2>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginBottom: "1.5rem" }}>
                Upload an anime screenshot and we&apos;ll identify the exact anime, episode, and timestamp using trace.moe
            </p>

            <div
                className={`screenshot-dropzone ${dragOver ? "dragover" : ""}`}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={handleBrowse}
            >
                <div className="screenshot-dropzone-icon">🖼️</div>
                <p className="screenshot-dropzone-text">
                    Drag & drop an anime screenshot here
                </p>
                <p className="screenshot-dropzone-hint">
                    or click to browse • Supports PNG, JPG, WebP
                </p>
                <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    style={{ display: "none" }}
                    onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) handleFile(file);
                    }}
                />
            </div>

            {preview && (
                <img className="screenshot-preview" src={preview} alt="Preview" />
            )}

            {loading && (
                <div style={{ textAlign: "center", padding: "2rem" }}>
                    <div className="spinner" />
                    <p style={{ color: "var(--text-muted)", marginTop: "0.5rem", fontSize: "0.85rem" }}>
                        Searching across anime databases...
                    </p>
                </div>
            )}

            {error && !loading && (
                <div className="empty-state" style={{ padding: "2rem" }}>
                    <div className="empty-state-icon">😿</div>
                    <p className="empty-state-text">{error}</p>
                </div>
            )}

            {results.length > 0 && (
                <div className="screenshot-results">
                    <h3 className="section-heading">Results</h3>
                    {results.map((result, i) => (
                        <div key={i} className="screenshot-result-card">
                            <div className="screenshot-result-info">
                                <h4 className="screenshot-result-title">
                                    {result.title || `AniList ID: ${result.anilist_id}`}
                                </h4>
                                <div className="screenshot-result-details">
                                    {result.episode && <span>Episode {result.episode}</span>}
                                    <span>Timestamp: {formatTimestamp(result.timestamp_from)}</span>
                                </div>
                                <span className={`screenshot-similarity ${getSimilarityClass(result.similarity)}`}>
                                    {result.similarity}% match
                                </span>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </section>
    );
}
