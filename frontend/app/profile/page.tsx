import { Suspense } from "react";
import ProfilePage from "@/components/ProfilePage";

export default function ProfileRoute() {
  return (
    <Suspense fallback={null}>
      <ProfilePage />
    </Suspense>
  );
}
