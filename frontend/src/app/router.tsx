import { Navigate, createBrowserRouter } from "react-router-dom";

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
      { path: "admin/integrations", element: <AdminIntegrationsPage /> },
      { path: "admin/integrations/:categoryId", element: <AdminIntegrationsPage /> },
      { path: "*", element: <NotFoundPage /> },
    ],
  },
]);
