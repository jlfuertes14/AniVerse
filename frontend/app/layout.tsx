import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AniVerse | Discover Anime by Vibe",
  description:
    "Discover your next anime obsession by vibe, not just genre. Explore trending, cyberpunk, 90s aesthetic, and more with our AI-powered discovery engine.",
  keywords: [
    "anime",
    "anime discovery",
    "find anime",
    "anime recommendation",
    "anime search",
    "MyAnimeList",
    "AniList",
    "trace.moe",
    "anime screenshot search",
  ],
  openGraph: {
    title: "AniVerse",
    description: "Discover anime by vibe, not just genre.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
