import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { travelWatchApi } from "@/api/travelWatchApi";
import type { DashboardData } from "@/api/types";
import { WatchesPage } from "@/pages/WatchesPage";

function renderWatches(data: DashboardData) {
  vi.spyOn(travelWatchApi, "getDashboard").mockResolvedValue(data);
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const router = createMemoryRouter(
    [
      { path: "/watches", element: <WatchesPage /> },
      { path: "/profile", element: <div>Profile</div> },
      { path: "/profile/presets", element: <div>Presets</div> },
      { path: "/admin/integrations", element: <div>Integrations</div> },
    ],
    { initialEntries: ["/watches"] },
  );

  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("WatchesPage readiness guidance", () => {
  it("promotes the first blocker and follows backend resolution metadata", async () => {
    const blocker = "Opaque readiness copy that contains no route hints.";
    renderWatches({
      highlights: [],
      watches: [
        {
          id: "watch-1",
          route: "Tokyo to Singapore",
          dates: "12 to 19 Apr",
          travelers: "2 travelers",
          cabin: "Business",
          status: "active",
          framing: "Best value",
          bestNow: "JPY 118,400",
          insight: "A strong value.",
          cadence: "Daily refresh",
          readiness: {
            score: 20,
            label: "Blocked",
            blockers: [blocker, "A second blocker."],
            warnings: [],
            resolutions: [
              {
                code: "traveler_profile_required",
                label: "Complete traveler profile",
                path: "/profile",
              },
              {
                code: "preset_required",
                label: "Choose traveler preset",
                path: "/profile/presets",
              },
              {
                code: "provider_setup_required",
                label: "Configure integrations",
                path: "/admin/integrations",
              },
            ],
          },
          badges: [],
          ctaActions: [],
        },
      ],
    });

    const blockerCopy = await screen.findByText(blocker);
    expect(blockerCopy.closest(".notice-alert")).not.toBeNull();
    expect(
      screen.getByRole("link", { name: "Complete traveler profile" }),
    ).toHaveAttribute("href", "/profile");
    expect(screen.getByRole("link", { name: "Choose traveler preset" })).toHaveAttribute(
      "href",
      "/profile/presets",
    );
    expect(screen.getByRole("link", { name: "Configure integrations" })).toHaveAttribute(
      "href",
      "/admin/integrations",
    );
  });
});
