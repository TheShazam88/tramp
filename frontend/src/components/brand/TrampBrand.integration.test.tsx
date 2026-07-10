import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { travelWatchApi } from "@/api/travelWatchApi";
import type { ProfileWorkspace } from "@/api/types";
import { AppLayout } from "@/layouts/AppLayout";
import { LoginPage } from "@/pages/LoginPage";

const authenticatedWorkspace = {
  currentUser: {
    id: "user-1",
    email: "traveler@example.com",
    role: "user",
    onboardingCompleted: true,
    defaultNotifyChannel: "email",
    telegramChatId: null,
    totpEnabled: true,
  },
  trampStampBalance: 0,
} as ProfileWorkspace;

function renderRoute(path: string, workspace: ProfileWorkspace) {
  vi.spyOn(travelWatchApi, "getProfileWorkspace").mockResolvedValue(workspace);
  vi.spyOn(travelWatchApi, "getSystemStatus").mockResolvedValue({
    mockDataEnabled: false,
    liveInventoryAvailable: true,
    currentInventoryMode: "live",
  });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(
    [
      { path: "/login", element: <LoginPage /> },
      {
        path: "/",
        element: <AppLayout />,
        children: [
          { path: "watches", element: <div>Workspace</div> },
          { path: "onboarding", element: <div>Onboarding</div> },
        ],
      },
    ],
    { initialEntries: [path] },
  );

  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("shared TRAMP branding", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("uses the text-only wordmark and stamp badge in the authenticated header", async () => {
    renderRoute("/watches", authenticatedWorkspace);

    const wordmark = await screen.findByText("TRAMP");
    const heading = screen.getByRole("heading", { level: 1 });
    expect(heading).toContainElement(wordmark);
    expect(heading).not.toHaveAttribute("aria-label");
    expect(screen.getByText("TRAVEL AMPLIFIER")).toBeVisible();
    expect(screen.getByText("Autonomous travel booking")).toBeVisible();
    expect(screen.getByText("Operator console")).toBeVisible();
    const badge = screen.getByLabelText("0 TRAMP-Stamps in your balance");
    expect(badge).toBeVisible();
    expect(badge.querySelector(".tramp-stamp-artwork-static")).toBeInTheDocument();
    expect(badge.querySelector(".tramp-stamp-wing")).not.toBeInTheDocument();
    expect(screen.queryByRole("img", { name: "TRAMP" })).not.toBeInTheDocument();
  });

  it("keeps the onboarding header context around the shared wordmark", async () => {
    renderRoute("/onboarding", authenticatedWorkspace);

    expect(await screen.findByText("Autonomous travel booking")).toBeVisible();
    expect(screen.getByText("Security and onboarding")).toBeVisible();
    expect(screen.getByText("TRAVEL AMPLIFIER")).toBeVisible();
  });

  it("uses the same shared wordmark on login", async () => {
    renderRoute("/login", {
      ...authenticatedWorkspace,
      currentUser: null,
      trampStampBalance: 0,
    });

    const wordmark = await screen.findByText("TRAMP");
    expect(screen.getByRole("heading", { level: 1 })).toContainElement(wordmark);
    expect(screen.getByText("TRAVEL AMPLIFIER")).toBeVisible();
  });
});
