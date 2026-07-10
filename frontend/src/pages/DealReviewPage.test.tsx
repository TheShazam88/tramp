import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PropsWithChildren } from "react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { travelWatchApi } from "@/api/travelWatchApi";
import type {
  BookDealRequest,
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

type ReconcileBooking = (dealId: string) => Promise<DealApprovalResult | null>;

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-search">{location.search}</div>;
}

function createWrapper(queryClient: QueryClient, initialEntry: string) {
  return function Wrapper({ children }: PropsWithChildren) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route
              path="/deals/:dealId"
              element={
                <>
                  {children}
                  <LocationProbe />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    );
  };
}

function renderDealReview(initialEntry = "/deals/deal-1?watchId=watch-1") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const rendered = render(<DealReviewPage />, {
    wrapper: createWrapper(queryClient, initialEntry),
  });
  return { ...rendered, queryClient, user: userEvent.setup() };
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
  let reconcileBooking: ReturnType<typeof vi.fn<ReconcileBooking>>;

  beforeEach(() => {
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
    reconcileBooking = vi.fn<ReconcileBooking>().mockResolvedValue(null);
    Object.defineProperty(travelWatchApi, "getBookingForDeal", {
      configurable: true,
      value: reconcileBooking,
      writable: true,
    });
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
    reconcileBooking.mockResolvedValueOnce(approvalResult);
    const { user } = renderDealReview();
    await openAndFillSecureForm(user);

    await user.click(screen.getByRole("button", { name: "Book now" }));

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Booking confirmed.");
    expect(status).toHaveFocus();
    expect(reconcileBooking).toHaveBeenCalledWith("deal-1");
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
    expect(alert).toHaveTextContent("could not be confirmed");
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
