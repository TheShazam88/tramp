import { useQuery } from "@tanstack/react-query";
import { Navigate, createBrowserRouter } from "react-router-dom";

import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import { AppLayout } from "@/layouts/AppLayout";
import { AdminIntegrationsPage } from "@/pages/AdminIntegrationsPage";
import { BookingsPage } from "@/pages/BookingsPage";
import { DealReviewPage } from "@/pages/DealReviewPage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { OnboardingPage } from "@/pages/OnboardingPage";
import { ProfileNotificationsPage } from "@/pages/ProfileNotificationsPage";
import { ProfilePresetsPage } from "@/pages/ProfilePresetsPage";
import { ProfileSettingsPage } from "@/pages/ProfileSettingsPage";
import { TwoFactorSetupPage } from "@/pages/TwoFactorSetupPage";
import { WatchEditorPage } from "@/pages/WatchEditorPage";
import { WatchesPage } from "@/pages/WatchesPage";

function AdminOnly() {
  const { data, isLoading, isError } = useQuery({
    queryKey: queryKeys.profile,
    queryFn: travelWatchApi.getProfileWorkspace,
  });

  if (isLoading) {
    return <div className="surface-card">Loading your workspace...</div>;
  }

  if (isError || data?.currentUser?.role !== "admin") {
    return <Navigate to="/watches" replace />;
  }

  return <AdminIntegrationsPage />;
}

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <LoginPage />,
  },
  {
    path: "/setup/2fa",
    element: <TwoFactorSetupPage />,
  },
  {
    path: "/setup/2fa/:stage",
    element: <TwoFactorSetupPage />,
  },
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/watches" replace /> },
      { path: "onboarding", element: <OnboardingPage /> },
      { path: "onboarding/:stepId", element: <OnboardingPage /> },
      { path: "watches", element: <WatchesPage /> },
      { path: "watches/new", element: <WatchEditorPage /> },
      { path: "watches/:watchId/edit", element: <WatchEditorPage /> },
      { path: "deals/:dealId", element: <DealReviewPage /> },
      { path: "bookings", element: <BookingsPage /> },
      { path: "profile", element: <ProfileSettingsPage /> },
      { path: "profile/notifications", element: <ProfileNotificationsPage /> },
      { path: "profile/presets", element: <ProfilePresetsPage /> },
      { path: "admin/integrations", element: <AdminOnly /> },
      { path: "admin/integrations/:categoryId", element: <AdminOnly /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
