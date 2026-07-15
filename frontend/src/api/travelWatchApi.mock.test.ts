import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

describe("travelWatchApi mock payment and booking isolation", () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubEnv("VITE_API_MODE", "mock");
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("keeps payment mutations and booking execution off the backend", async () => {
    const { travelWatchApi } = await import("@/api/travelWatchApi");
    const { inspectMockBookingAttempts } = await import("@/api/mockBookingAttempts");
    const workspace = await travelWatchApi.getProfileWorkspace();

    expect(workspace.trampStampBalance).toBe(0);
    expect(workspace.paymentMethods).toEqual([
      expect.objectContaining({
        id: expect.any(String),
        last4: expect.stringMatching(/^\d{4}$/),
      }),
    ]);
    expect(workspace.travelers).toEqual([
      expect.objectContaining({
        id: "mock-traveler-self",
        displayName: "Demo Traveler",
        relationship: "self",
      }),
      expect.objectContaining({
        id: "mock-traveler-partner",
        displayName: "Demo Partner",
        relationship: "partner",
      }),
    ]);
    expect(workspace.travelerGroupOptions).toEqual([
      {
        id: "mock-group-partners",
        name: "Demo travelers",
        travelerIds: ["mock-traveler-self", "mock-traveler-partner"],
      },
    ]);
    expect(workspace.householdSummary).toEqual(
      expect.objectContaining({
        travelerCount: 2,
        travelerGroupCount: 1,
        hasSelfTraveler: true,
      }),
    );

    await travelWatchApi.savePaymentMethod({
      label: "Demo backup",
      brand: "Visa",
      cardholderName: "Demo Traveler",
      cardNumber: "4242424242424242",
      last4: "4242",
      expMonth: "12",
      expYear: "2030",
      providerToken: "",
      billingAddressLine1: "",
      billingAddressCity: "",
      billingAddressPostalCode: "",
      billingCountry: "US",
    });
    await travelWatchApi.deletePaymentMethod(workspace.paymentMethods[0].id);
    const booking = await travelWatchApi.bookDeal({
      dealId: "deal-1",
      approvalToken: "approval-secret-value",
      paymentMethodId: workspace.paymentMethods[0].id,
      totpCode: "987654",
      masterKeyPassphrase: "master-secret-value",
      idempotencyKey: "00000000-0000-4000-8000-000000000001",
    });

    expect(booking.trampStampsAwarded).toBe(0);
    expect(inspectMockBookingAttempts()).toEqual([
      {
        idempotencyKey: "00000000-0000-4000-8000-000000000001",
        dealId: "deal-1",
        paymentMethodId: workspace.paymentMethods[0].id,
        status: "booked",
        bookingId: "booking-ana",
        bookingStatus: "ticketed",
        trampStampsAwarded: 0,
        trampStampBalance: 0,
      },
    ]);
    const storedAttemptJson = JSON.stringify(inspectMockBookingAttempts());
    expect(storedAttemptJson).not.toMatch(
      /approval-secret-value|987654|master-secret-value|approvalToken|totpCode|masterKeyPassphrase/,
    );

    vi.resetModules();
    const { travelWatchApi: reloadedApi } = await import("@/api/travelWatchApi");
    const interrupted = await reloadedApi.reconcileBookingAttempt(
      "00000000-0000-4000-8000-000000000001",
      {
        dealId: "deal-1",
        paymentMethodId: workspace.paymentMethods[0].id,
      },
    );
    expect(interrupted).toEqual(
      expect.objectContaining({
        code: "mock_interrupted",
        safeToRetry: true,
        booking: null,
      }),
    );
    expect(fetch).not.toHaveBeenCalled();
  });
});
