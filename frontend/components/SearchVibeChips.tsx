"use client";

import type { VibePreset } from "@/lib/types";

interface SearchVibeChipsProps {
    vibes: VibePreset[];
    activeVibe: string | null;
    onVibeClick: (vibeId: string) => void;
}

export default function SearchVibeChips({ vibes, activeVibe, onVibeClick }: SearchVibeChipsProps) {
    return (
        <section className="search-vibe-section container-wide" id="search-vibes-section">
            <div className="vibe-chips">
                {vibes.map((vibe) => (
                    <button
                        key={vibe.id}
                        className={`vibe-chip ${activeVibe === vibe.id ? "active" : ""}`}
                        onClick={() => onVibeClick(vibe.id)}
                        title={vibe.description}
                    >
                        <span>{vibe.emoji}</span>
                        <span>{vibe.name}</span>
                    </button>
                ))}
            </div>
        </section>
    );
}
