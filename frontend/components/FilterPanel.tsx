"use client";

import { useState, useEffect } from "react";
import { getGenres } from "@/lib/api";
import type { Genre } from "@/lib/types";

interface FilterPanelProps {
    isOpen: boolean;
    onClose: () => void;
    onApply: (filters: {
        genres: string;
        year_from?: number;
        year_to?: number;
        status?: string;
        rating?: string;
    }) => void;
}

const STATUS_OPTIONS = [
    { value: "", label: "Any" },
    { value: "airing", label: "Currently Airing" },
    { value: "complete", label: "Completed" },
    { value: "upcoming", label: "Upcoming" },
];

const RATING_OPTIONS = [
    { value: "", label: "Any" },
    { value: "g", label: "G - All Ages" },
    { value: "pg", label: "PG - Children" },
    { value: "pg13", label: "PG-13 - Teens" },
    { value: "r17", label: "R - 17+" },
];

export default function FilterPanel({ isOpen, onClose, onApply }: FilterPanelProps) {
    const [genres, setGenres] = useState<Genre[]>([]);
    const [selectedGenres, setSelectedGenres] = useState<Set<number>>(new Set());
    const [yearFrom, setYearFrom] = useState<string>("");
    const [yearTo, setYearTo] = useState<string>("");
    const [status, setStatus] = useState("");
    const [rating, setRating] = useState("");

    useEffect(() => {
        if (isOpen && genres.length === 0) {
            getGenres().then(setGenres).catch(console.error);
        }
    }, [isOpen, genres.length]);

    const toggleGenre = (id: number) => {
        const next = new Set(selectedGenres);
        next.has(id) ? next.delete(id) : next.add(id);
        setSelectedGenres(next);
    };

    const handleApply = () => {
        onApply({
            genres: Array.from(selectedGenres).join(","),
            year_from: yearFrom ? parseInt(yearFrom) : undefined,
            year_to: yearTo ? parseInt(yearTo) : undefined,
            status: status || undefined,
            rating: rating || undefined,
        });
        onClose();
    };

    const handleReset = () => {
        setSelectedGenres(new Set());
        setYearFrom("");
        setYearTo("");
        setStatus("");
        setRating("");
    };

    return (
        <>
            <div className={`filter-overlay ${isOpen ? "open" : ""}`} onClick={onClose} />
            <div className={`filter-panel ${isOpen ? "open" : ""}`}>
                <div className="filter-panel-header">
                    <h3 className="filter-panel-title">Advanced Filters</h3>
                    <button className="filter-close" onClick={onClose}>✕</button>
                </div>

                {/* Genres */}
                <div className="filter-group">
                    <div className="filter-label">Genres</div>
                    <div className="filter-genre-grid">
                        {genres.map((genre) => (
                            <div
                                key={genre.mal_id}
                                className={`filter-genre-item ${selectedGenres.has(genre.mal_id) ? "selected" : ""}`}
                                onClick={() => toggleGenre(genre.mal_id)}
                            >
                                <div className="filter-genre-checkbox">
                                    {selectedGenres.has(genre.mal_id) && "✓"}
                                </div>
                                {genre.name}
                            </div>
                        ))}
                    </div>
                </div>

                {/* Year Range */}
                <div className="filter-group">
                    <div className="filter-label">Year Range</div>
                    <div className="filter-range">
                        <input
                            type="number"
                            placeholder="1960"
                            min="1960"
                            max="2026"
                            value={yearFrom}
                            onChange={(e) => setYearFrom(e.target.value)}
                        />
                        <span className="filter-range-separator">to</span>
                        <input
                            type="number"
                            placeholder="2026"
                            min="1960"
                            max="2026"
                            value={yearTo}
                            onChange={(e) => setYearTo(e.target.value)}
                        />
                    </div>
                </div>

                {/* Status */}
                <div className="filter-group">
                    <div className="filter-label">Status</div>
                    <select className="filter-select" value={status} onChange={(e) => setStatus(e.target.value)}>
                        {STATUS_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                    </select>
                </div>

                {/* Rating */}
                <div className="filter-group">
                    <div className="filter-label">Rating</div>
                    <select className="filter-select" value={rating} onChange={(e) => setRating(e.target.value)}>
                        {RATING_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                    </select>
                </div>

                <button className="filter-apply" onClick={handleApply}>Apply Filters</button>
                <button className="filter-reset" onClick={handleReset}>Reset All</button>
            </div>
        </>
    );
}
