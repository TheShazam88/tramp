import { describe, expect, it } from "vitest";

import { ApiError } from "@/api/client";
import {
  bookingErrorKind,
  getApiErrorMessage,
  getBookingConflictDetail,
} from "@/api/errors";

describe("getApiErrorMessage", () => {
  it("formats FastAPI validation arrays without echoing request values", () => {
    const error = new ApiError("Request failed", 422, {
      detail: [
        {
          loc: ["body", "totp_code"],
          msg: "String should have at least 6 characters",
          input: "123",
        },
        {
          loc: ["body", "payment_method_id"],
          msg: "Field required",
        },
      ],
    });

    expect(getApiErrorMessage(error, "Booking failed.")).toBe(
      "TOTP code: String should have at least 6 characters Payment method: Field required",
    );
    expect(getApiErrorMessage(error, "Booking failed.")).not.toContain("123");
  });

  it("uses FastAPI string details for definite request errors", () => {
    const error = new ApiError("Request failed", 400, { detail: "A valid TOTP code is required." });

    expect(getApiErrorMessage(error, "Booking failed.")).toBe("A valid TOTP code is required.");
  });

  it("parses structured booking conflicts without exposing raw fields", () => {
    const error = new ApiError("Request failed", 409, {
      detail: {
        code: "provider_failed",
        message: "The provider could not confirm this booking.",
        safe_to_retry: false,
        provider_error: "provider-secret",
      },
    });

    expect(getBookingConflictDetail(error)).toEqual({
      code: "provider_failed",
      message: "The provider could not confirm this booking.",
      safeToRetry: false,
    });
    expect(getApiErrorMessage(error, "Booking failed.")).not.toContain("provider-secret");
  });
});

describe("bookingErrorKind", () => {
  it("keeps stateful 409, network, and 5xx outcomes for reconciliation", () => {
    expect(bookingErrorKind(new ApiError("Bad request", 422))).toBe("definite");
    expect(
      bookingErrorKind(
        new ApiError("Conflict", 409, {
          detail: {
            code: "attempt_in_progress",
            message: "Still processing.",
            safe_to_retry: false,
          },
        }),
      ),
    ).toBe("ambiguous");
    expect(
      bookingErrorKind(
        new ApiError("Conflict", 409, {
          detail: {
            code: "deal_expired",
            message: "Start a new attempt.",
            safe_to_retry: true,
          },
        }),
      ),
    ).toBe("definite");
    expect(bookingErrorKind(new ApiError("Server error", 503))).toBe("ambiguous");
    expect(bookingErrorKind(new TypeError("Failed to fetch"))).toBe("ambiguous");
  });
});
