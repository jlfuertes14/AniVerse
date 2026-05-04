"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Navbar from "@/components/Navbar";
import SpotlightHero from "@/components/SpotlightHero";
import VibeChips from "@/components/VibeChips";
import TrendingCarousel from "@/components/TrendingCarousel";
import AnimeGrid from "@/components/AnimeGrid";
import FilterPanel from "@/components/FilterPanel";
import AnimeDetail from "@/components/AnimeDetail";
import ScreenshotSearch from "@/components/ScreenshotSearch";
import AuthModal from "@/components/AuthModal";
import SearchVibeChips from "@/components/SearchVibeChips";
import EstimatedSchedule from "@/components/EstimatedSchedule";
import SiteFooter from "@/components/SiteFooter";
import {
  getBanners,
  getMe,
  getRandomAnime,
  getTrending,
  getVibes,
  getWaifuImage,
  searchAnime,
} from "@/lib/api";
import { clearAuth, getStoredUser, isLoggedIn } from "@/lib/auth";
import type { User } from "@/lib/auth";
import type { Anime, SearchFilters, VibePreset } from "@/lib/types";

interface HomeClientProps {
  initialTrending: Anime[];
  initialVibes: VibePreset[];
  initialSpotlight: Anime[];
  latestReleases: React.ReactNode;
}

export default function HomeClient({ 
  initialTrending, 
  initialVibes, 
  initialSpotlight,
  latestReleases 
}: HomeClientProps) {
  const searchParams = useSearchParams();
  const router = useRouter();
  const handledParamsRef = useRef<string>("");

  const [spotlight, setSpotlight] = useState<Anime[]>(initialSpotlight);
  const [trending, setTrending] = useState<Anime[]>(initialTrending);
  const [vibes, setVibes] = useState<VibePreset[]>(initialVibes);
  const [searchResults, setSearchResults] = useState<Anime[]>([]);
  const [activeVibe, setActiveVibe] = useState<string | null>(null);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [searchTitle, setSearchTitle] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [selectedAnime, setSelectedAnime] = useState<Anime | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [showScreenshot, setShowScreenshot] = useState(false);
  const [loading, setLoading] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [mascotUrl, setMascotUrl] = useState("");
  const [banners, setBanners] = useState<string[]>([]);

  useEffect(() => {
    const stored = getStoredUser();
    if (stored && isLoggedIn()) {
      setCurrentUser(stored);
      getMe().then(setCurrentUser).catch(() => {
        clearAuth();
        setCurrentUser(null);
      });
    }

    getWaifuImage("waifu").then(setMascotUrl).catch(() => {});
    getBanners().then(setBanners).catch(() => {});
  }, []);

  const handleSearch = useCallback(async (query: string) => {
    setIsSearching(true);
    setSearchLoading(true);
    setActiveVibe(null);
    setShowScreenshot(false);
    setSearchTitle(`Search: "${query}"`);
    setPage(1);

    try {
      const data = await searchAnime({ query, page: 1 });
      const results = data.data || [];
      const uniqueResults = Array.from(new Map(results.map(a => [`${a.source}-${a.id}`, a])).values());
      setSearchResults(uniqueResults);
      setHasMore(data.has_next || false);
      setActiveCategory(null);
    } catch (err) {
      console.error("Search failed:", err);
    } finally {
      setSearchLoading(false);
    }
  }, []);

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
    const vibe = vibes.find((item) => item.id === vibeId);
    setSearchTitle(vibe ? `${vibe.emoji} ${vibe.name}` : "Vibe Search");
    setPage(1);

    try {
      const data = await searchAnime({ vibe: vibeId, page: 1 });
      const results = data.data || [];
      const uniqueResults = Array.from(new Map(results.map(a => [`${a.source}-${a.id}`, a])).values());
      setSearchResults(uniqueResults);
      setHasMore(data.has_next || false);
      setActiveCategory(null);
    } catch (err) {
      console.error("Vibe search failed:", err);
    } finally {
      setSearchLoading(false);
    }
  }, [activeVibe, vibes]);

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
      const results = data.data || [];
      const uniqueResults = Array.from(new Map(results.map(a => [`${a.source}-${a.id}`, a])).values());
      setSearchResults(uniqueResults);
      setHasMore(data.has_next || false);
      setActiveCategory(null);
    } catch (err) {
      console.error("Filter search failed:", err);
    } finally {
      setSearchLoading(false);
    }
  }, []);

  const handleCategoryClick = useCallback(async (type: string) => {
    if (activeCategory === type) {
      setActiveCategory(null);
      setIsSearching(false);
      setSearchResults([]);
      return;
    }

    setActiveCategory(type);
    setIsSearching(true);
    setSearchLoading(true);
    setActiveVibe(null);
    setShowScreenshot(false);
    setSearchTitle(type === "tv" ? "TV Series" : "Anime Movies");
    setPage(1);

    try {
      const data = await searchAnime({ type, page: 1 });
      const results = data.data || [];
      const uniqueResults = Array.from(new Map(results.map(a => [`${a.source}-${a.id}`, a])).values());
      setSearchResults(uniqueResults);
      setHasMore(data.has_next || false);
    } catch (err) {
      console.error("Category search failed:", err);
    } finally {
      setSearchLoading(false);
    }
  }, [activeCategory]);

  const handleLoadMore = useCallback(async () => {
    const nextPage = page + 1;
    setLoadingMore(true);

    try {
      const params: SearchFilters = { page: nextPage };
      if (activeVibe) params.vibe = activeVibe;
      if (activeCategory) params.type = activeCategory;

      const data = await searchAnime(params);
      const newItems = data.data || [];
      
      setSearchResults((prev) => {
        const combined = [...prev, ...newItems];
        return Array.from(new Map(combined.map(a => [`${a.source}-${a.id}`, a])).values());
      });
      
      setHasMore(data.has_next || false);
      setPage(nextPage);
    } catch (err) {
      console.error("Load more failed:", err);
    } finally {
      setLoadingMore(false);
    }
  }, [activeVibe, activeCategory, page]);

  const handleAnimeClick = useCallback((anime: Anime) => {
    setSelectedAnime(anime);
    setIsDetailOpen(true);
  }, []);

  const handleRandom = useCallback(async () => {
    try {
      const anime = await getRandomAnime();
      setSelectedAnime(anime);
      setIsDetailOpen(true);
    } catch (err) {
      console.error("Random failed:", err);
    }
  }, []);

  const handleLogoClick = useCallback(() => {
    setIsSearching(false);
    setActiveVibe(null);
    setActiveCategory(null);
    setSearchResults([]);
    setShowScreenshot(false);
  }, []);

  const handleScreenshotClick = useCallback(() => {
    setShowScreenshot((prev) => !prev);
    setIsSearching(false);
    setActiveVibe(null);
    setActiveCategory(null);
  }, []);

  const handleVibesClick = useCallback(() => {
    setShowScreenshot(false);
    const el = document.getElementById("vibes-section");
    if (el) el.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    const rawParams = searchParams.toString();
    if (!rawParams || rawParams === handledParamsRef.current) return;

    handledParamsRef.current = rawParams;

    const q = searchParams.get("q");
    const screenshot = searchParams.get("screenshot");
    const filter = searchParams.get("filter");
    const genres = searchParams.get("genres");
    const yearFrom = searchParams.get("year_from");
    const yearTo = searchParams.get("year_to");
    const status = searchParams.get("status");
    const rating = searchParams.get("rating");
    const vibesParam = searchParams.get("vibes");
    const random = searchParams.get("random");
    const typeParam = searchParams.get("type");
    const hasFilterParams = Boolean(genres || yearFrom || yearTo || status || rating);

    if (q) {
      handleSearch(q);
    } else if (typeParam) {
      handleCategoryClick(typeParam);
    } else if (hasFilterParams) {
      handleFilterApply({
        genres: genres || "",
        year_from: yearFrom ? Number(yearFrom) : undefined,
        year_to: yearTo ? Number(yearTo) : undefined,
        status: status || undefined,
        rating: rating || undefined,
      });
    } else if (random === "1") {
      handleRandom();
    } else if (screenshot === "1") {
      setShowScreenshot(true);
      setIsSearching(false);
      setActiveVibe(null);
    } else if (filter === "1") {
      setIsFilterOpen(true);
    } else if (vibesParam === "1") {
      handleVibesClick();
    }

    router.replace("/", { scroll: screenshot !== "1" });
  }, [searchParams, handleSearch, handleFilterApply, handleRandom, handleVibesClick, handleCategoryClick, router]);

  return (
    <>
      <Navbar
        onSearch={handleSearch}
        onSearchResultSelect={handleAnimeClick}
        onFilterToggle={() => setIsFilterOpen(true)}
        onScreenshotClick={handleScreenshotClick}
        onRandomClick={handleRandom}
        onVibesClick={handleVibesClick}
        onLogoClick={handleLogoClick}
        onLoginClick={() => setShowAuthModal(true)}
        onProfileClick={() => router.push("/profile")}
        onLogout={() => {
          clearAuth();
          setCurrentUser(null);
        }}
        onCategoryClick={handleCategoryClick}
        activeCategory={activeCategory}
        activeVibe={activeVibe}
        showScreenshot={showScreenshot}
        isRandomActive={searchTitle === "Surprise Me!"}
        currentUser={currentUser}
        mascotUrl={mascotUrl}
      />

      {!isSearching && !showScreenshot && (
        <SpotlightHero
          spotlightAnime={spotlight}
          onExplore={handleAnimeClick}
          onDetail={handleAnimeClick}
        />
      )}

      <ScreenshotSearch isVisible={showScreenshot} />

      {!showScreenshot && !isSearching && !activeCategory && (
        <VibeChips vibes={vibes} activeVibe={activeVibe} onVibeClick={handleVibeClick} />
      )}

      {!showScreenshot && isSearching && !activeCategory && (
        <SearchVibeChips vibes={vibes} activeVibe={activeVibe} onVibeClick={handleVibeClick} />
      )}

      {!isSearching && !showScreenshot && (
        <>
          <TrendingCarousel anime={trending} loading={loading} onAnimeClick={handleAnimeClick} />
          {latestReleases}
          <EstimatedSchedule />
        </>
      )}

      {isSearching && (
        <section className="container-wide" style={{ paddingTop: "1.5rem" }}>
          <h2 className="section-heading">{searchTitle}</h2>
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

      <FilterPanel
        isOpen={isFilterOpen}
        onClose={() => setIsFilterOpen(false)}
        onApply={handleFilterApply}
      />

      <AnimeDetail
        anime={selectedAnime}
        isOpen={isDetailOpen}
        onClose={() => setIsDetailOpen(false)}
        onAnimeClick={handleAnimeClick}
        currentUser={currentUser}
        onLoginClick={() => setShowAuthModal(true)}
      />

      {showAuthModal && (
        <AuthModal
          onClose={() => setShowAuthModal(false)}
          onAuthSuccess={(user) => setCurrentUser(user)}
          prefetchedBanners={banners}
        />
      )}

      <SiteFooter backgroundImage={mascotUrl} />
    </>
  );
}
