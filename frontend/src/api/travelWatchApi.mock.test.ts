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
    const workspace = await travelWatchApi.getProfileWorkspace();

    expect(workspace.paymentMethods).toEqual([
      expect.objectContaining({
        id: expect.any(String),
        last4: expect.stringMatching(/^\d{4}$/),
      }),
    ]);

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
      approvalToken: "mock-approval-token",
      paymentMethodId: workspace.paymentMethods[0].id,
      totpCode: "123456",
      masterKeyPassphrase: "",
      idempotencyKey: "00000000-0000-4000-8000-000000000001",
    });

    expect(booking.trampStampsAwarded).toBe(0);
    expect(fetch).not.toHaveBeenCalled();
  });
});
