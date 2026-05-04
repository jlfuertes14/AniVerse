"use client";

import { useRouter } from "next/navigation";

const AZ_ITEMS = ["All", "#", "0-9", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L", "M", "N", "O", "P", "Q", "R", "S", "T", "U", "V", "W", "X", "Y", "Z"];

interface SiteFooterProps {
    backgroundImage?: string;
}

export default function SiteFooter({ backgroundImage }: SiteFooterProps) {
    const router = useRouter();

    const handleAzClick = (item: string) => {
        if (item === "All") {
            router.push("/");
            return;
        }

        if (item === "#") {
            router.push("/?q=%23");
            return;
        }

        if (item === "0-9") {
            router.push("/?q=0");
            return;
        }

        router.push(`/?q=${encodeURIComponent(item)}`);
    };

    return (
        <footer
            className="site-footer"
            style={backgroundImage ? { ["--site-footer-bg" as string]: `url(${backgroundImage})` } : undefined}
        >
            <div className="site-footer-inner container-wide">
                <div className="site-footer-copy">
                    <h2 className="site-footer-title">A-Z List</h2>
                    <p className="site-footer-subtitle">Browse anime order by alphabet name A to Z.</p>
                </div>

                <div className="site-footer-az">
                    {AZ_ITEMS.map((item) => (
                        <button
                            type="button"
                            key={item}
                            className="site-footer-az-chip"
                            onClick={() => handleAzClick(item)}
                        >
                            {item}
                        </button>
                    ))}
                </div>

                <div className="site-footer-brand-row">
                    <div className="site-footer-brand">
                        <span className="site-footer-brand-ani">Ani</span>
                        <span className="site-footer-brand-verse">Verse</span>
                    </div>
                </div>

                <div className="site-footer-legal">
                    <p>Copyright © AniVerse. All Rights Reserved.</p>
                    <p>
                        Metadata is powered by Jikan, AniList, trace.moe, and waifu.im. Streaming availability depends on third-party providers.
                    </p>
                </div>
            </div>
        </footer>
    );
}
