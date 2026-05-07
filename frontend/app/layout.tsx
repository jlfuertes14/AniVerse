import type { Metadata, Viewport } from "next";
import "./globals.css";
import "./toast.css";

export const metadata: Metadata = {
  title: "AniVerse - Watch Free Anime Online HD Streaming",
  description:
    "AniVerse is your ultimate destination to watch free anime online in high definition. Discover your next favorite series by vibe, genre, or mood with our advanced AI-powered engine.",
  keywords: [
    "watch anime online",
    "free anime streaming",
    "anime HD online",
    "AniVerse",
    "anime discovery",
    "watch free anime",
    "best anime streaming site",
    "anime recommendation engine",
    "cyberpunk anime",
    "90s aesthetic anime",
  ],
  icons: {
    icon: "/favicon.svg",
    apple: "/favicon.svg",
  },
  openGraph: {
    title: "AniVerse - Watch Free Anime Online HD Streaming",
    description: "Watch free anime online in HD and discover your next obsession by vibe.",
    type: "website",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
