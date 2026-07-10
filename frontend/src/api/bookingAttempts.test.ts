import { beforeEach, describe, expect, it } from "vitest";

import {
  clearStoredBookingAttempt,
  loadStoredBookingAttempt,
  saveStoredBookingAttempt,
} from "@/api/bookingAttempts";

describe("booking attempt session persistence", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("persists only non-secret logical attempt metadata per deal", () => {
    saveStoredBookingAttempt({
      version: 1,
      dealId: "deal-1",
      idempotencyKey: "attempt-key-123",
      paymentMethodId: "payment-1",
      state: "submitted",
    });

    const raw = sessionStorage.getItem("tramp.booking-attempt.deal-1") ?? "";
    expect(raw).toContain("attempt-key-123");
    expect(raw).toContain("payment-1");
    expect(raw).not.toMatch(/totp|passphrase|approval.?token/i);
    expect(loadStoredBookingAttempt("deal-1")).toEqual({
      version: 1,
      dealId: "deal-1",
      idempotencyKey: "attempt-key-123",
      paymentMethodId: "payment-1",
      state: "submitted",
    });

    clearStoredBookingAttempt("deal-1");
    expect(loadStoredBookingAttempt("deal-1")).toBeNull();
  });

  it("rejects malformed or cross-deal session data", () => {
    sessionStorage.setItem(
      "tramp.booking-attempt.deal-1",
      JSON.stringify({
        version: 1,
        dealId: "another-deal",
        idempotencyKey: "attempt-key-123",
        paymentMethodId: "payment-1",
        state: "submitted",
      }),
    );

    expect(loadStoredBookingAttempt("deal-1")).toBeNull();
    expect(sessionStorage.getItem("tramp.booking-attempt.deal-1")).toBeNull();
  });
});
