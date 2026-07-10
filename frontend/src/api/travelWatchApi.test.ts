import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { travelWatchApi } from "@/api/travelWatchApi";

describe("travelWatchApi booking execution", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("posts the caller-owned approval token and idempotency key unchanged", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      id: "booking-1",
      deal_id: "deal-1",
      provider: "duffel",
      status: "ticketed",
      amount_charged: "640.00",
      currency: "USD",
      cancellation: null,
      tramp_stamps_awarded: 1,
      tramp_stamp_balance: 4,
    } as never);

    await travelWatchApi.bookDeal({
      dealId: "deal-1",
      approvalToken: "linked-or-minted-token",
      paymentMethodId: "payment-1",
      totpCode: "123456",
      masterKeyPassphrase: "",
      idempotencyKey: "00000000-0000-4000-8000-000000000001",
    });

    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith("/bookings/approve", {
      deal_id: "deal-1",
      approval_token: "linked-or-minted-token",
      totp_code: "123456",
      master_key_passphrase: undefined,
      payment_method_id: "payment-1",
      idempotency_key: "00000000-0000-4000-8000-000000000001",
    });
  });

  it("maps the authenticated attempt reconciliation response", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      idempotency_key: "attempt-key-123",
      deal_id: "deal-1",
      payment_method_id: "payment-1",
      status: "booked",
      code: "booked",
      message: "Booking confirmed from the saved booking record.",
      safe_to_retry: false,
      started_at: "2030-01-01T00:00:00Z",
      finished_at: "2030-01-01T00:01:00Z",
      booking: {
          id: "booking-1",
          deal_id: "deal-1",
          provider: "duffel",
          status: "ticketed",
          amount_charged: "640.00",
          currency: "USD",
          cancellation: null,
          tramp_stamps_awarded: 1,
          tramp_stamp_balance: 4,
      },
    } as never);

    const attempt = await travelWatchApi.reconcileBookingAttempt("attempt-key-123");

    expect(get).toHaveBeenCalledWith("/bookings/attempts/attempt-key-123");
    expect(attempt).toEqual(
      expect.objectContaining({
        idempotencyKey: "attempt-key-123",
        dealId: "deal-1",
        paymentMethodId: "payment-1",
        code: "booked",
        safeToRetry: false,
        booking: expect.objectContaining({
          bookingId: "booking-1",
          trampStampsAwarded: 1,
          trampStampBalance: 4,
        }),
      }),
    );
  });
});
