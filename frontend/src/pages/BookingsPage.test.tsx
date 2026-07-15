import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { travelWatchApi } from "@/api/travelWatchApi";
import type { BookingsViewData } from "@/api/types";
import { BookingsPage } from "@/pages/BookingsPage";

const bookings: BookingsViewData = {
  source: "live",
  items: [
    {
      id: "booking-1",
      title: "Tokyo to Singapore",
      when: "12 to 19 Apr",
      status: "Ticketed",
      amount: "JPY 118,400",
      provider: "Duffel",
      actions: ["View itinerary"],
      bookingStatus: "ticketed",
      dealId: "deal-1",
      watchId: "watch-1",
      disruptions: [
        { id: "disruption-resolved", status: "resolved", type: "delay" },
        { id: "disruption-open", status: "open", type: "cancellation" },
      ],
    },
  ],
};

function renderBookings() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const router = createMemoryRouter(
    [
      { path: "/bookings", element: <BookingsPage /> },
      { path: "/deals/:dealId", element: <div>Deal review</div> },
    ],
    { initialEntries: ["/bookings"] },
  );
  const user = userEvent.setup();

  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );

  return { user };
}

describe("BookingsPage local test tools", () => {
  beforeEach(() => {
    vi.spyOn(travelWatchApi, "getBookings").mockResolvedValue(
      structuredClone(bookings),
    );
    vi.spyOn(travelWatchApi, "triggerBookingDisruption").mockResolvedValue();
    vi.spyOn(travelWatchApi, "resolveDisruption").mockResolvedValue();
    vi.spyOn(travelWatchApi, "createCancellationApprovalToken").mockResolvedValue({
      token: "signed-cancellation-token",
      expiresAt: "2030-01-01T00:00:00Z",
    });
    vi.spyOn(travelWatchApi, "cancelBooking").mockResolvedValue({
      bookingId: "booking-1",
      status: "refunded",
      refundAmount: "JPY 118,400",
      idempotentReplay: false,
    });
  });

  it("keeps normal actions visible and runs disruption tools only after disclosure", async () => {
    const { user } = renderBookings();

    expect(await screen.findByRole("link", { name: "Open deal review" })).toBeVisible();
    expect(screen.getByRole("link", { name: "View itinerary" })).toBeVisible();

    const summary = screen.getByText("Local test tools");
    const details = summary.closest("details");
    expect(details).not.toHaveAttribute("open");
    expect(
      screen.getByRole("button", { name: "Simulate disruption" }),
    ).not.toBeVisible();

    await user.click(summary);

    expect(details).toHaveAttribute("open");
    expect(
      screen.getByText(
        "Local-only simulation controls. These test endpoints do not represent production provider behavior.",
      ),
    ).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Simulate disruption" }));
    await waitFor(() => {
      expect(
        vi.mocked(travelWatchApi.triggerBookingDisruption).mock.calls[0]?.[0],
      ).toBe("booking-1");
    });

    await user.click(screen.getByRole("button", { name: "Resolve disruption" }));
    await waitFor(() => {
      expect(vi.mocked(travelWatchApi.resolveDisruption).mock.calls[0]?.[0]).toBe(
        "disruption-open",
      );
    });
  });

  it("requires signed token, TOTP, master key, and stable idempotency for cancellation", async () => {
    const { user } = renderBookings();

    await user.click(
      await screen.findByRole("button", { name: "Secure cancellation" }),
    );
    await user.type(screen.getByLabelText("Cancellation reason"), "Changed plans");
    await user.type(screen.getByLabelText("Cancellation TOTP code"), "123456");
    await user.type(
      screen.getByLabelText("Cancellation master-key passphrase"),
      "master-secret",
    );
    await user.click(screen.getByRole("button", { name: "Confirm cancellation" }));

    await waitFor(() => {
      expect(travelWatchApi.createCancellationApprovalToken).toHaveBeenCalledWith(
        "booking-1",
      );
      expect(travelWatchApi.cancelBooking).toHaveBeenCalledWith({
        bookingId: "booking-1",
        reason: "Changed plans",
        approvalToken: "signed-cancellation-token",
        totpCode: "123456",
        masterKeyPassphrase: "master-secret",
        idempotencyKey: expect.any(String),
      });
    });
    expect(await screen.findByRole("status")).toHaveTextContent(
      "Cancellation refunded",
    );
  });

  it("reuses the cancellation token and key after an ambiguous response", async () => {
    vi.mocked(travelWatchApi.cancelBooking)
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce({
        bookingId: "booking-1",
        status: "refunded",
        refundAmount: "JPY 118,400",
        idempotentReplay: true,
      });
    const { user } = renderBookings();

    await user.click(
      await screen.findByRole("button", { name: "Secure cancellation" }),
    );
    await user.type(screen.getByLabelText("Cancellation TOTP code"), "123456");
    await user.type(
      screen.getByLabelText("Cancellation master-key passphrase"),
      "master-secret",
    );
    await user.click(screen.getByRole("button", { name: "Confirm cancellation" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Failed to fetch");

    await user.type(screen.getByLabelText("Cancellation TOTP code"), "654321");
    await user.type(
      screen.getByLabelText("Cancellation master-key passphrase"),
      "retry-secret",
    );
    await user.click(screen.getByRole("button", { name: "Confirm cancellation" }));
    await screen.findByRole("status");

    const requests = vi.mocked(travelWatchApi.cancelBooking).mock.calls.map(
      ([request]) => request,
    );
    expect(travelWatchApi.createCancellationApprovalToken).toHaveBeenCalledTimes(1);
    expect(requests[1]?.idempotencyKey).toBe(requests[0]?.idempotencyKey);
    expect(requests[1]?.approvalToken).toBe(requests[0]?.approvalToken);
  });
});
