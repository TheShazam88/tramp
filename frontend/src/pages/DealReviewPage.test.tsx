import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { saveStoredBookingAttempt } from "@/api/bookingAttempts";
import { ApiError } from "@/api/client";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import type {
  BookDealRequest,
  BookingAttemptReconciliation,
  DealApprovalResult,
  DealData,
  DealViewData,
  ProfileWorkspace,
} from "@/api/types";
import { DealReviewPage } from "@/pages/DealReviewPage";

const approvalResult: DealApprovalResult = {
  dealId: "deal-1",
  bookingId: "booking-1",
  bookingStatus: "ticketed",
  provider: "Duffel",
  amount: "$640",
  confirmationNote: "Booking confirmed.",
  trampStampsAwarded: 0,
  trampStampBalance: 3,
};

const awardedApprovalResult: DealApprovalResult = {
  ...approvalResult,
  trampStampsAwarded: 1,
  trampStampBalance: 4,
};

const baseDeal: DealData = {
  id: "deal-1",
  watchId: "watch-1",
  route: "Tokyo -> Singapore",
  cabin: "Business",
  price: "$640",
  wasPrice: "",
  context: "Live deal",
  breakdown: "Taxes included",
  score: 92,
  details: [],
  loyaltyPlan: [],
  warnings: [],
  coverage: [],
  dealStatus: "proposed",
  readiness: {
    score: 100,
    label: "Ready",
    blockers: [],
    warnings: [],
    resolutions: [],
  },
  badges: [],
  ctaActions: [
    { key: "book_now", label: "Book now", tone: "primary", enabled: true },
    { key: "ignore", label: "Ignore", tone: "secondary", enabled: true },
  ],
};

const profileWorkspace: ProfileWorkspace = {
  currentUser: {
    id: "user-1",
    email: "traveler@example.com",
    role: "user",
    onboardingCompleted: true,
    defaultNotifyChannel: "email",
    telegramChatId: null,
    totpEnabled: true,
  },
  trampStampBalance: 3,
  travelers: [],
  travelerGroups: [],
  travelerGroupOptions: [],
  preferences: {
    homeAirports: [],
    defaultCabin: "business",
    defaultLuxuryVsSavings: 0.5,
    preferredAlliances: [],
    preferredAirlines: [],
    avoidedAirlines: [],
    preferredHotelBrands: [],
    avoidedHotelBrands: [],
    quietHoursStart: "",
    quietHoursEnd: "",
    defaultNotifyChannel: "email",
    avoidRedeye: false,
    preferRefundable: true,
    seatAutoSelect: false,
    defaultHotelMinRating: "",
    maxLayoverMinutes: "",
    minConnectionMinutes: "",
  },
  paymentMethods: [
    {
      id: "payment-1",
      label: "Primary",
      brand: "Visa",
      cardholderName: "",
      cardNumber: "",
      last4: "4242",
      expMonth: "12",
      expYear: "2030",
      providerToken: "",
      billingAddressLine1: "",
      billingAddressCity: "",
      billingAddressPostalCode: "",
      billingCountry: "US",
    },
  ],
  templates: [],
  householdSummary: {
    travelerCount: 1,
    travelerGroupCount: 0,
    paymentMethodCount: 1,
    templateCount: 0,
    passportGapCount: 0,
    hasSelfTraveler: true,
    hasPaymentMethod: true,
    totpEnabled: true,
    setupWarnings: [],
    readinessLabel: "Ready",
  },
};

function reconciliation(
  overrides: Partial<BookingAttemptReconciliation> = {},
): BookingAttemptReconciliation {
  return {
    idempotencyKey: "attempt-key-123",
    dealId: "deal-1",
    paymentMethodId: "payment-1",
    status: "started",
    code: "attempt_in_progress",
    message: "This booking attempt is still processing.",
    safeToRetry: false,
    recoveryRequired: false,
    booking: null,
    startedAt: "2030-01-01T00:00:00Z",
    ...overrides,
  };
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-search">{location.search}</div>;
}

function renderDealReview(initialEntry = "/deals/deal-1?watchId=watch-1") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const router = createMemoryRouter(
    [
      {
        path: "/deals/:dealId",
        element: (
          <>
            <DealReviewPage />
            <LocationProbe />
          </>
        ),
      },
      { path: "/bookings", element: <div>Bookings destination</div> },
    ],
    { initialEntries: [initialEntry] },
  );
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...rendered, queryClient, router, user: userEvent.setup() };
}

async function openAndFillSecureForm(
  user: ReturnType<typeof userEvent.setup>,
  masterKey = "master-secret",
) {
  await user.click(await screen.findByRole("button", { name: "Book now" }));
  await user.selectOptions(screen.getByLabelText("Saved payment method"), "payment-1");
  await user.type(screen.getByLabelText("Six-digit TOTP code"), "123456");
  await user.type(screen.getByLabelText("Master-key passphrase (optional)"), masterKey);
}

describe("DealReviewPage booking execution", () => {
  let reconcileAttempt: ReturnType<
    typeof vi.fn<(idempotencyKey: string) => Promise<BookingAttemptReconciliation>>
  >;

  beforeEach(() => {
    sessionStorage.clear();
    vi.spyOn(travelWatchApi, "getDealReview").mockResolvedValue({
      deal: structuredClone(baseDeal),
      source: "live",
      approvalAvailable: true,
    } satisfies DealViewData);
    vi.spyOn(travelWatchApi, "getProfileWorkspace").mockResolvedValue(
      structuredClone(profileWorkspace),
    );
    vi.spyOn(travelWatchApi, "verifyApprovalToken").mockResolvedValue({
      valid: true,
      expiresAt: "2030-01-01T00:00:00Z",
    });
    vi.spyOn(travelWatchApi, "createApprovalToken").mockResolvedValue({
      token: "minted-approval-token",
      expiresAt: "2030-01-01T00:00:00Z",
    });
    vi.spyOn(travelWatchApi, "bookDeal").mockResolvedValue(approvalResult);
    vi.spyOn(travelWatchApi, "rejectDeal").mockResolvedValue({
      dealId: "deal-1",
      status: "rejected",
      detail: "Rejected.",
    });
    reconcileAttempt = vi
      .fn<(idempotencyKey: string) => Promise<BookingAttemptReconciliation>>()
      .mockRejectedValue(new ApiError("Not found", 404, { detail: "Booking attempt not found." }));
    vi.spyOn(travelWatchApi, "reconcileBookingAttempt").mockImplementation(reconcileAttempt);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("disables submit, hide, and cancel controls while booking is pending", async () => {
    let resolveBooking: (result: DealApprovalResult) => void = () => undefined;
    vi.mocked(travelWatchApi.bookDeal).mockReturnValue(
      new Promise((resolve) => {
        resolveBooking = resolve;
      }),
    );
    const { user } = renderDealReview();
    await openAndFillSecureForm(user);

    await user.click(screen.getByRole("button", { name: "Book now" }));
    await waitFor(() => expect(travelWatchApi.bookDeal).toHaveBeenCalledTimes(1));

    expect(screen.getByRole("button", { name: "Booking..." })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Hide booking form" })).toBeDisabled();

    resolveBooking(approvalResult);
    await screen.findByRole("status");
  });

  it("triggers one stamp butterfly and updates the balance", async () => {
    vi.mocked(travelWatchApi.bookDeal).mockResolvedValueOnce(awardedApprovalResult);
    const { queryClient, user } = renderDealReview();
    await openAndFillSecureForm(user);

    await user.click(screen.getByRole("button", { name: "Book now" }));

    expect(
      await screen.findByRole("status", {
        name: "One TRAMP-Stamp awarded. Balance: 4 TRAMP-Stamps.",
      }),
    ).toBeVisible();
    expect(screen.getAllByText("+1 TRAMP-Stamp")).toHaveLength(1);
    await waitFor(() => {
      expect(
        queryClient.getQueryData<ProfileWorkspace>(queryKeys.profile)?.trampStampBalance,
      ).toBe(4);
    });
  });

  it("does not trigger the butterfly for a replay that awards zero stamps", async () => {
    vi.mocked(travelWatchApi.bookDeal).mockResolvedValueOnce({
      ...approvalResult,
      trampStampsAwarded: 0,
      trampStampBalance: 4,
    });
    const { user } = renderDealReview();
    await openAndFillSecureForm(user);

    await user.click(screen.getByRole("button", { name: "Book now" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Booking confirmed.");
    expect(screen.queryByText("+1 TRAMP-Stamp")).not.toBeInTheDocument();
  });

  it("reuses a verified linked token, consumes its cache, and invalidates every deal variant", async () => {
    const { queryClient, user } = renderDealReview(
      "/deals/deal-1?watchId=watch-1&approvalToken=linked-token",
    );
    const linkedTokenKey = ["deal-approval-token", "deal-1", "linked-token"] as const;
    queryClient.setQueryData(["deal", "deal-1", "other-watch"], {
      stale: "variant",
    });

    await screen.findByText(/Opened from a secure notification link\./);
    await openAndFillSecureForm(user);
    await user.click(screen.getByRole("button", { name: "Book now" }));

    await screen.findByRole("status");
    expect(travelWatchApi.createApprovalToken).not.toHaveBeenCalled();
    expect(vi.mocked(travelWatchApi.bookDeal).mock.calls[0]?.[0]).toEqual(
      expect.objectContaining({
        approvalToken: "linked-token",
        idempotencyKey: expect.any(String),
      }),
    );
    expect(screen.getByTestId("location-search")).not.toHaveTextContent("approvalToken");
    expect(queryClient.getQueryData(linkedTokenKey)).toBeUndefined();
    expect(queryClient.getQueryState(["deal", "deal-1", "other-watch"])?.isInvalidated).toBe(
      true,
    );
  });

  it("reconciles a lost booking response before reporting success", async () => {
    vi.mocked(travelWatchApi.bookDeal).mockRejectedValueOnce(new TypeError("Failed to fetch"));
    reconcileAttempt.mockResolvedValueOnce(
      reconciliation({
        status: "booked",
        code: "booked",
        message: "Booking confirmed from the saved booking record.",
        recoveryRequired: true,
        booking: approvalResult,
      }),
    );
    const { user } = renderDealReview();
    await openAndFillSecureForm(user);

    await user.click(screen.getByRole("button", { name: "Book now" }));

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Booking confirmed.");
    expect(status).toHaveFocus();
    expect(reconcileAttempt).toHaveBeenCalledWith(expect.any(String), {
      dealId: "deal-1",
      paymentMethodId: "payment-1",
    });
    expect(screen.queryByLabelText("Six-digit TOTP code")).not.toBeInTheDocument();
  });

  it("retains the logical attempt key when an ambiguous outcome cannot be reconciled", async () => {
    vi.mocked(travelWatchApi.bookDeal)
      .mockRejectedValueOnce(new TypeError("Failed to fetch"))
      .mockResolvedValueOnce(approvalResult);
    const { user } = renderDealReview();
    await openAndFillSecureForm(user);

    await user.click(screen.getByRole("button", { name: "Book now" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("No server booking record was found");
    expect(alert).toHaveFocus();
    expect(screen.getByLabelText("Six-digit TOTP code")).toHaveValue("");
    expect(screen.getByLabelText("Master-key passphrase (optional)")).toHaveValue("");

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await user.click(screen.getByRole("button", { name: "Book now" }));
    expect(screen.getByLabelText("Saved payment method")).toHaveValue("payment-1");
    await user.type(screen.getByLabelText("Six-digit TOTP code"), "654321");
    await user.type(screen.getByLabelText("Master-key passphrase (optional)"), "retry-secret");
    await user.click(screen.getByRole("button", { name: "Book now" }));
    await screen.findByRole("status");

    const requests = vi.mocked(travelWatchApi.bookDeal).mock.calls.map(([request]) => request);
    expect(requests[1]?.idempotencyKey).toBe(requests[0]?.idempotencyKey);
    expect(requests[1]?.approvalToken).toBe(requests[0]?.approvalToken);
    expect(travelWatchApi.createApprovalToken).toHaveBeenCalledTimes(1);
  });

  it("clears secrets and mutation variables after a definite FastAPI error", async () => {
    vi.mocked(travelWatchApi.bookDeal).mockRejectedValueOnce(
      new ApiError("Request failed", 422, {
        detail: [{ loc: ["body", "totp_code"], msg: "Invalid code", input: "123456" }],
      }),
    );
    const { queryClient, user } = renderDealReview();
    await openAndFillSecureForm(user);

    await user.click(screen.getByRole("button", { name: "Book now" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("TOTP code: Invalid code");
    expect(alert).not.toHaveTextContent("123456");
    expect(alert).toHaveFocus();
    expect(screen.getByLabelText("Six-digit TOTP code")).toHaveValue("");
    expect(screen.getByLabelText("Master-key passphrase (optional)")).toHaveValue("");
    expect(screen.queryByText("+1 TRAMP-Stamp")).not.toBeInTheDocument();
    expect(
      queryClient
        .getMutationCache()
        .getAll()
        .some((mutation) => mutation.state.variables !== undefined),
    ).toBe(false);
  });

  it("does not cache booking secrets and clears the mutation observer on unmount", async () => {
    vi.mocked(travelWatchApi.bookDeal).mockReturnValue(new Promise(() => undefined));
    const { queryClient, unmount, user } = renderDealReview();
    await openAndFillSecureForm(user);
    await user.click(screen.getByRole("button", { name: "Book now" }));
    await waitFor(() => expect(travelWatchApi.bookDeal).toHaveBeenCalledTimes(1));

    expect(JSON.stringify(queryClient.getMutationCache().getAll())).not.toContain(
      "master-secret",
    );
    unmount();
    expect(JSON.stringify(queryClient.getMutationCache().getAll())).not.toContain(
      "master-secret",
    );
  });

  it("restores a stored attempt after reload and reconciles its booking", async () => {
    saveStoredBookingAttempt({
      version: 1,
      dealId: "deal-1",
      idempotencyKey: "restored-attempt-key",
      paymentMethodId: "payment-1",
      state: "reconciling",
    });
    reconcileAttempt.mockResolvedValueOnce(
      reconciliation({
        idempotencyKey: "restored-attempt-key",
        status: "booked",
        code: "booked",
        message: "Booking confirmed from the saved booking record.",
        booking: approvalResult,
      }),
    );

    renderDealReview();

    await screen.findByText("Booking confirmed. Provider: Duffel. Amount: $640. Status: ticketed.");
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent("Booking confirmed.");
    expect(reconcileAttempt).toHaveBeenCalledWith("restored-attempt-key", {
      dealId: "deal-1",
      paymentMethodId: "payment-1",
    });
    expect(sessionStorage.getItem("tramp.booking-attempt.deal-1")).toBeNull();
    expect(travelWatchApi.createApprovalToken).not.toHaveBeenCalled();
  });

  it("polls an in-progress attempt until the booking completes", async () => {
    vi.useFakeTimers();
    saveStoredBookingAttempt({
      version: 1,
      dealId: "deal-1",
      idempotencyKey: "polling-attempt-key",
      paymentMethodId: "payment-1",
      state: "reconciling",
    });
    reconcileAttempt
      .mockResolvedValueOnce(
        reconciliation({
          idempotencyKey: "polling-attempt-key",
          status: "revalidated",
          code: "attempt_in_progress",
          recoveryRequired: true,
        }),
      )
      .mockResolvedValueOnce(
        reconciliation({
          idempotencyKey: "polling-attempt-key",
          status: "booked",
          code: "booked",
          message: "Booking confirmed from the saved booking record.",
          booking: approvalResult,
        }),
      );

    renderDealReview();
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(reconcileAttempt).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });

    expect(reconcileAttempt).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("status")).toHaveTextContent("Booking confirmed.");
    expect(sessionStorage.getItem("tramp.booking-attempt.deal-1")).toBeNull();
  });

  it("bounds automatic polling and keeps a manual Check again action", async () => {
    vi.useFakeTimers();
    saveStoredBookingAttempt({
      version: 1,
      dealId: "deal-1",
      idempotencyKey: "bounded-attempt-key",
      paymentMethodId: "payment-1",
      state: "reconciling",
    });
    reconcileAttempt.mockResolvedValue(
      reconciliation({
        idempotencyKey: "bounded-attempt-key",
        status: "revalidated",
        code: "attempt_in_progress",
        recoveryRequired: true,
      }),
    );

    renderDealReview();
    for (let check = 0; check < 3; check += 1) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(1000);
      });
    }

    expect(reconcileAttempt).toHaveBeenCalledTimes(4);
    expect(screen.getByRole("status")).toHaveTextContent("Automatic checks stopped");
    const checkAgain = screen.getByRole("button", { name: "Check again" });
    fireEvent.click(checkAgain);
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(reconcileAttempt).toHaveBeenCalledTimes(5);
  });

  it("shows recovery and navigation actions when deal loading fails", async () => {
    saveStoredBookingAttempt({
      version: 1,
      dealId: "deal-1",
      idempotencyKey: "error-branch-attempt-key",
      paymentMethodId: "payment-1",
      state: "manual_recovery",
    });
    vi.mocked(travelWatchApi.getDealReview).mockRejectedValueOnce(
      new Error("Deal loading failed."),
    );
    reconcileAttempt.mockResolvedValueOnce(
      reconciliation({
        idempotencyKey: "error-branch-attempt-key",
        status: "failed",
        code: "provider_failed",
        message: "Manual booking recovery is required.",
      }),
    );

    const { router, user } = renderDealReview();

    await screen.findByText("Manual booking recovery is required.");
    expect(screen.getByRole("status")).toHaveTextContent(
      "Manual booking recovery is required.",
    );
    expect(screen.getByRole("button", { name: "Check again" })).toBeVisible();
    expect(screen.getByText("Deal loading failed.")).toBeVisible();

    const navigation = router.navigate("/bookings");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Booking recovery is still pending",
    );
    await user.click(screen.getByRole("button", { name: "Stay on this page" }));
    await navigation;
  });

  it("reconciles stateful 409 conflicts and locks payment, rejection, and navigation", async () => {
    vi.mocked(travelWatchApi.bookDeal).mockRejectedValueOnce(
      new ApiError("Conflict", 409, {
        detail: {
          code: "attempt_in_progress",
          message: "This booking attempt is still processing.",
          safe_to_retry: false,
        },
      }),
    );
    reconcileAttempt.mockResolvedValueOnce(
      reconciliation({ recoveryRequired: true }),
    );
    const { router, user } = renderDealReview();
    await openAndFillSecureForm(user);

    await user.click(screen.getByRole("button", { name: "Book now" }));

    const recoveryStatus = await screen.findByRole("status");
    expect(recoveryStatus).toHaveTextContent("still processing");
    expect(reconcileAttempt).toHaveBeenCalledWith(expect.any(String), {
      dealId: "deal-1",
      paymentMethodId: "payment-1",
    });
    expect(screen.getByLabelText("Saved payment method")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Too pricey" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Ignore" })).toBeDisabled();
    const stored = sessionStorage.getItem("tramp.booking-attempt.deal-1") ?? "";
    expect(stored).toContain("payment-1");
    expect(stored).not.toMatch(/123456|master-secret|approval.?token/i);

    const navigation = router.navigate("/bookings");
    const navigationAlert = await screen.findByRole("alert");
    expect(navigationAlert).toHaveTextContent("Booking recovery is still pending");
    expect(router.state.location.pathname).toBe("/deals/deal-1");
    await user.click(screen.getByRole("button", { name: "Stay on this page" }));
    await navigation;

    const beforeUnload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(beforeUnload);
    expect(beforeUnload.defaultPrevented).toBe(true);
  });

  it("clears a definitive safe-to-retry conflict before generating a new key", async () => {
    let storedDuringRequest = "";
    vi.mocked(travelWatchApi.bookDeal).mockImplementationOnce(async () => {
      storedDuringRequest =
        sessionStorage.getItem("tramp.booking-attempt.deal-1") ?? "";
      throw new ApiError("Conflict", 409, {
        detail: {
          code: "deal_expired",
          message: "Start a new booking attempt.",
          safe_to_retry: true,
        },
      });
    });
    const { user } = renderDealReview();
    await openAndFillSecureForm(user);

    await user.click(screen.getByRole("button", { name: "Book now" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Start a new booking attempt.");
    expect(storedDuringRequest).toContain("payment-1");
    expect(sessionStorage.getItem("tramp.booking-attempt.deal-1")).toBeNull();
    expect(screen.getByLabelText("Saved payment method")).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "Too pricey" })).not.toBeDisabled();

    await user.type(screen.getByLabelText("Six-digit TOTP code"), "654321");
    await user.type(screen.getByLabelText("Master-key passphrase (optional)"), "retry-secret");
    await user.click(screen.getByRole("button", { name: "Book now" }));
    await screen.findByRole("status");

    const requests = vi.mocked(travelWatchApi.bookDeal).mock.calls.map(([request]) => request);
    expect(requests[1]?.idempotencyKey).not.toBe(requests[0]?.idempotencyKey);
  });

  it("renders backend-provided readiness resolutions without parsing blocker prose", async () => {
    vi.mocked(travelWatchApi.getDealReview).mockResolvedValueOnce({
      deal: {
        ...structuredClone(baseDeal),
        readiness: {
          score: 20,
          label: "Blocked",
          blockers: ["Opaque blocker text that may be localized later."],
          warnings: [],
          resolutions: [
            {
              code: "provider_setup_required",
              label: "Open exact setup",
              path: "/admin/integrations",
            },
          ],
        },
        ctaActions: [
          { key: "book_now", label: "Book now", tone: "primary", enabled: false },
        ],
      },
      source: "live",
      approvalAvailable: true,
    });

    renderDealReview();

    const resolution = await screen.findByRole("link", { name: "Open exact setup" });
    expect(resolution).toHaveAttribute("href", "/admin/integrations");
    expect(
      screen.getAllByText("Opaque blocker text that may be localized later.").length,
    ).toBeGreaterThan(0);
  });
});
