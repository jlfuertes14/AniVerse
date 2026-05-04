import { getLatestReleases } from "@/lib/api";
import LatestReleasesGrid from "./LatestReleasesGrid";
import type { LatestRelease } from "@/lib/types";

export default async function LatestReleases() {
    let releases: LatestRelease[] = [];
    try {
        // This runs on the server
        releases = await getLatestReleases();
    } catch (error) {
        console.error("Failed to fetch latest releases:", error);
    }

    if (!releases || releases.length === 0) return null;

    // Pass the data to the client component for interactive pagination
    return <LatestReleasesGrid initialReleases={releases} />;
}
