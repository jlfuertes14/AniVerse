"use client";

import { useState, useEffect, useCallback } from "react";
import Navbar from "@/components/Navbar";
import SpotlightHero from "@/components/SpotlightHero";
import VibeChips from "@/components/VibeChips";
import TrendingCarousel from "@/components/TrendingCarousel";
import AnimeGrid from "@/components/AnimeGrid";
import FilterPanel from "@/components/FilterPanel";
import AnimeDetail from "@/components/AnimeDetail";
import ScreenshotSearch from "@/components/ScreenshotSearch";
import AuthModal from "@/components/AuthModal";
import ProfilePage from "@/components/ProfilePage";
import {
  getSpotlight,
  getTrending,
  getVibes,
  searchAnime,
  getRandomAnime,
  getAnimeDetail,
  aiSearch,
  getWaifuImage,
  getMe,
} from "@/lib/api";
import { getStoredUser, clearAuth, isLoggedIn, setAuth, getToken } from "@/lib/auth";
import type { User } from "@/lib/auth";
import type { Anime, VibePreset, PaginatedResponse } from "@/lib/types";

interface AIFilters {
  genres?: string[];
  tags?: string[];
  mood?: string;
  year_from?: number;
  year_to?: number;
  studios?: string[];
  description?: string;
}

export default function Home() {
  // ─── State ───────────────────────────────────
  const [spotlight, setSpotlight] = useState<Anime[]>([]);
  const [trending, setTrending] = useState<Anime[]>([]);
  const [vibes, setVibes] = useState<VibePreset[]>([]);
  const [searchResults, setSearchResults] = useState<Anime[]>([]);
  const [activeVibe, setActiveVibe] = useState<string | null>(null);
  const [searchTitle, setSearchTitle] = useState<string>("");
  const [isSearching, setIsSearching] = useState(false);

  const [selectedAnime, setSelectedAnime] = useState<Anime | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);

  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [showScreenshot, setShowScreenshot] = useState(false);

  const [loading, setLoading] = useState(true);
  const [searchLoading, setSearchLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [aiFilters, setAiFilters] = useState<AIFilters | null>(null);
  const [isAiSearch, setIsAiSearch] = useState(false);

  // Auth state
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [showProfile, setShowProfile] = useState(false);
  const [mascotUrl, setMascotUrl] = useState("");

  // ─── Initial Data Load ───────────────────────
  useEffect(() => {
    async function loadInitialData() {
      try {
        const [spotlightData, trendingData, vibeData] = await Promise.all([
          getSpotlight(),
          getTrending(),
          getVibes(),
        ]);
        setSpotlight(spotlightData);
        setTrending(trendingData.data || []);
        setVibes(vibeData);
      } catch (err) {
        console.error("Failed to load initial data:", err);
      } finally {
        setLoading(false);
      }
    }
    loadInitialData();

    // Restore auth state
    const stored = getStoredUser();
    if (stored && isLoggedIn()) {
      setCurrentUser(stored);
      // Refresh user data from server
      getMe().then(setCurrentUser).catch(() => {
        clearAuth();
        setCurrentUser(null);
      });
    }

    // Load mascot image
    getWaifuImage("waifu").then(setMascotUrl).catch(() => {});
  }, []);

  // ─── Search (AI-powered for descriptive queries, regular for titles) ─────
  const handleSearch = useCallback(async (query: string) => {
    setIsSearching(true);
    setSearchLoading(true);
    setActiveVibe(null);
    setShowScreenshot(false);
    setAiFilters(null);
    setPage(1);

    // Detect if query is descriptive (AI) vs simple title search
    const isDescriptive = query.split(" ").length >= 4 ||
      /like|similar|vibe|mood|feel|recommend|suggest|something|anime with|anime about/i.test(query);

    if (isDescriptive) {
      // AI-powered search via Gemini
      setIsAiSearch(true);
      setSearchTitle(`🤖 AI Search: "${query}"`);
      try {
        const aiResult = await aiSearch(query);
        if (aiResult.error) {
          console.error("AI search error:", aiResult.error);
          // Fallback to regular search
          const data = await searchAnime({ query, page: 1 });
          setSearchResults(data.data || []);
          setHasMore(data.has_next || false);
          setIsAiSearch(false);
          setSearchTitle(`Search: "${query}"`);
        } else {
          setSearchResults(aiResult.results || []);
          setAiFilters(aiResult.filters);
          setHasMore(false);
        }
      } catch (err) {
        console.error("AI search failed, falling back:", err);
        const data = await searchAnime({ query, page: 1 });
        setSearchResults(data.data || []);
        setHasMore(data.has_next || false);
        setIsAiSearch(false);
        setSearchTitle(`Search: "${query}"`);
      }
    } else {
      // Regular title search
      setIsAiSearch(false);
      setSearchTitle(`Search: "${query}"`);
      try {
        const data = await searchAnime({ query, page: 1 });
        setSearchResults(data.data || []);
        setHasMore(data.has_next || false);
      } catch (err) {
        console.error("Search failed:", err);
      }
    }
    setSearchLoading(false);
  }, []);

  // ─── Vibe Search ─────────────────────────────
  const handleVibeClick = useCallback(async (vibeId: string) => {
    if (activeVibe === vibeId) {
      setActiveVibe(null);
      setIsSearching(false);
      setSearchResults([]);
      return;
    }

    setActiveVibe(vibeId);
    setIsSearching(true);
    setSearchLoading(true);
    setShowScreenshot(false);
    const vibe = vibes.find((v) => v.id === vibeId);
    setSearchTitle(vibe ? `${vibe.emoji} ${vibe.name}` : "Vibe Search");
    setPage(1);

    try {
      const data = await searchAnime({ vibe: vibeId, page: 1 });
      setSearchResults(data.data || []);
      setHasMore(data.has_next || false);
    } catch (err) {
      console.error("Vibe search failed:", err);
    } finally {
      setSearchLoading(false);
    }
  }, [activeVibe, vibes]);

  // ─── Filter Apply ────────────────────────────
  const handleFilterApply = useCallback(async (filters: {
    genres: string;
    year_from?: number;
    year_to?: number;
    status?: string;
    rating?: string;
  }) => {
    setIsSearching(true);
    setSearchLoading(true);
    setActiveVibe(null);
    setShowScreenshot(false);
    setSearchTitle("Filtered Results");
    setPage(1);

    try {
      const data = await searchAnime({ ...filters, page: 1 });
      setSearchResults(data.data || []);
      setHasMore(data.has_next || false);
    } catch (err) {
      console.error("Filter search failed:", err);
    } finally {
      setSearchLoading(false);
    }
  }, []);

  // ─── Load More ───────────────────────────────
  const handleLoadMore = useCallback(async () => {
    const nextPage = page + 1;
    setLoadingMore(true);

    try {
      const params: Record<string, string | number> = { page: nextPage };
      if (activeVibe) params.vibe = activeVibe;

      const data = await searchAnime(params as any);
      setSearchResults((prev) => [...prev, ...(data.data || [])]);
      setHasMore(data.has_next || false);
      setPage(nextPage);
    } catch (err) {
      console.error("Load more failed:", err);
    } finally {
      setLoadingMore(false);
    }
  }, [page, activeVibe]);

  // ─── Detail Modal ────────────────────────────
  const handleAnimeClick = useCallback((anime: Anime) => {
    setSelectedAnime(anime);
    setIsDetailOpen(true);
  }, []);

  // ─── Random ──────────────────────────────────
  const handleRandom = useCallback(async () => {
    try {
      const anime = await getRandomAnime();
      setSelectedAnime(anime);
      setIsDetailOpen(true);
    } catch (err) {
      console.error("Random failed:", err);
    }
  }, []);

  // ─── Logo / Home ─────────────────────────────
  const handleLogoClick = useCallback(() => {
    setIsSearching(false);
    setActiveVibe(null);
    setSearchResults([]);
    setShowScreenshot(false);
  }, []);

  // ─── Screenshot Toggle ──────────────────────
  const handleScreenshotClick = useCallback(() => {
    setShowScreenshot(!showScreenshot);
    setIsSearching(false);
    setActiveVibe(null);
  }, [showScreenshot]);

  // ─── Vibes Scroll ───────────────────────────
  const handleVibesClick = useCallback(() => {
    setShowScreenshot(false);
    const el = document.getElementById("vibes-section");
    if (el) el.scrollIntoView({ behavior: "smooth" });
  }, []);

  return (
    <>
      <Navbar
        onSearch={handleSearch}
        onFilterToggle={() => setIsFilterOpen(true)}
        onScreenshotClick={handleScreenshotClick}
        onRandomClick={handleRandom}
        onVibesClick={handleVibesClick}
        onLogoClick={handleLogoClick}
        onLoginClick={() => setShowAuthModal(true)}
        onProfileClick={() => setShowProfile(true)}
        onLogout={() => { clearAuth(); setCurrentUser(null); }}
        currentUser={currentUser}
        mascotUrl={mascotUrl}
      />

      {/* Spotlight Hero */}
      {!isSearching && !showScreenshot && (
        <SpotlightHero
          spotlightAnime={spotlight}
          onExplore={handleAnimeClick}
          onDetail={handleAnimeClick}
        />
      )}

      {/* Screenshot Search */}
      <ScreenshotSearch isVisible={showScreenshot} />

      {/* Vibe Chips */}
      {!showScreenshot && (
        <VibeChips vibes={vibes} activeVibe={activeVibe} onVibeClick={handleVibeClick} />
      )}

      {/* Trending Carousel (only on home) */}
      {!isSearching && !showScreenshot && (
        <TrendingCarousel anime={trending} loading={loading} onAnimeClick={handleAnimeClick} />
      )}

      {/* Search / Vibe Results */}
      {isSearching && (
        <section className="container" style={{ padding: "1.5rem 1.5rem 0" }}>
          <h2 className="section-heading">{searchTitle}</h2>
          {isAiSearch && aiFilters && (
            <div className="ai-filters-display">
              <span className="ai-filters-label">🧠 AI extracted:</span>
              {(Array.isArray(aiFilters.genres) ? aiFilters.genres : []).map((g) => (
                <span key={String(g)} className="ai-filter-tag ai-filter-genre">{String(g)}</span>
              ))}
              {(Array.isArray(aiFilters.tags) ? aiFilters.tags : []).map((t) => (
                <span key={String(t)} className="ai-filter-tag ai-filter-tag-item">{String(t)}</span>
              ))}
              {aiFilters.mood && (
                <span className="ai-filter-tag ai-filter-mood">🎭 {String(aiFilters.mood)}</span>
              )}
              {aiFilters.year_from && (
                <span className="ai-filter-tag ai-filter-year">
                  📅 {String(aiFilters.year_from)}{aiFilters.year_to ? `–${String(aiFilters.year_to)}` : "+"}
                </span>
              )}
              {aiFilters.description && (
                <p className="ai-filters-desc">{String(aiFilters.description)}</p>
              )}
            </div>
          )}
        </section>
      )}

      {isSearching && (
        <AnimeGrid
          anime={searchResults}
          loading={searchLoading}
          hasMore={hasMore}
          onLoadMore={handleLoadMore}
          onAnimeClick={handleAnimeClick}
          loadingMore={loadingMore}
        />
      )}

      {/* Filter Panel */}
      <FilterPanel
        isOpen={isFilterOpen}
        onClose={() => setIsFilterOpen(false)}
        onApply={handleFilterApply}
      />

      {/* Detail Modal */}
      <AnimeDetail
        anime={selectedAnime}
        isOpen={isDetailOpen}
        onClose={() => setIsDetailOpen(false)}
        onAnimeClick={handleAnimeClick}
        currentUser={currentUser}
        onLoginClick={() => setShowAuthModal(true)}
      />

      {/* Auth Modal */}
      {showAuthModal && (
        <AuthModal
          onClose={() => setShowAuthModal(false)}
          onAuthSuccess={(user) => setCurrentUser(user)}
        />
      )}

      {/* Profile Page */}
      {showProfile && currentUser && (
        <ProfilePage
          user={currentUser}
          onAnimeClick={(animeId) => {
            setShowProfile(false);
            getAnimeDetail(animeId, "anilist")
              .then((d) => {
                setSelectedAnime(d as Anime);
                setIsDetailOpen(true);
              })
              .catch(console.error);
          }}
          onClose={() => setShowProfile(false)}
          onUserUpdate={(updatedUser) => {
            setCurrentUser(updatedUser);
            const token = getToken();
            if (token) setAuth(token, updatedUser);
          }}
        />
      )}

      {/* Footer */}
      <footer className="footer">
        <p className="footer-text">
          AniVerse — Powered by{" "}
          <a href="https://jikan.moe" target="_blank" rel="noopener" className="footer-link">
            Jikan
          </a>
          ,{" "}
          <a href="https://anilist.co" target="_blank" rel="noopener" className="footer-link">
            AniList
          </a>
          ,{" "}
          <a href="https://trace.moe" target="_blank" rel="noopener" className="footer-link">
            trace.moe
          </a>
          {" "}&{" "}
          <a href="https://waifu.im" target="_blank" rel="noopener" className="footer-link">
            waifu.im
          </a>
        </p>
      </footer>
    </>
  );
}
