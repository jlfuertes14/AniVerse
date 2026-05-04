import { Suspense } from "react";
import HomeClient from "@/components/HomeClient";
import LatestReleases from "@/components/LatestReleases";
import { getSpotlight, getTrending, getVibes } from "@/lib/api";
import type { Anime, VibePreset } from "@/lib/types";

export default async function Home() {
  // Server-side data fetching
  let initialTrending: Anime[] = [];
  let initialVibes: VibePreset[] = [];
  let initialSpotlight: Anime[] = [];

  try {
    const [trendingData, vibesData, spotlightData] = await Promise.all([
      getTrending(),
      getVibes(),
      getSpotlight(),
    ]);
    initialTrending = trendingData.data || [];
    initialVibes = vibesData || [];
    initialSpotlight = spotlightData || [];
  } catch (error) {
    console.error("Initial data fetch failed:", error);
  }

  return (
    <Suspense fallback={null}>
      <HomeClient 
        initialTrending={initialTrending}
        initialVibes={initialVibes}
        initialSpotlight={initialSpotlight}
        latestReleases={<LatestReleases />}
      />
    </Suspense>
  );
}
