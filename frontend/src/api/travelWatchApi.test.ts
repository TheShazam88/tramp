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

  it("maps a completed booking found during reconciliation", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      items: [
        {
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
      ],
    } as never);

    const booking = await travelWatchApi.getBookingForDeal("deal-1");

    expect(booking).toEqual(
      expect.objectContaining({
        bookingId: "booking-1",
        dealId: "deal-1",
        trampStampsAwarded: 1,
        trampStampBalance: 4,
      }),
    );
  });
});
