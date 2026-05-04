import type { VibePreset } from "@/lib/types";

interface VibeChipsProps {
    vibes: VibePreset[];
    activeVibe: string | null;
    onVibeClick: (vibeId: string) => void;
}

export default function VibeChips({ vibes, activeVibe, onVibeClick }: VibeChipsProps) {
    return (
        <section className="vibe-section container-wide" id="vibes-section">
            <h2 className="section-heading">Discover by Vibe</h2>
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
