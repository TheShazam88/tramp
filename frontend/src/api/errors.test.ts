import { describe, expect, it } from "vitest";

import { ApiError } from "@/api/client";
import { bookingErrorKind, getApiErrorMessage } from "@/api/errors";

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
});

describe("bookingErrorKind", () => {
  it("distinguishes definite 4xx errors from ambiguous network and 5xx outcomes", () => {
    expect(bookingErrorKind(new ApiError("Bad request", 422))).toBe("definite");
    expect(bookingErrorKind(new ApiError("Server error", 503))).toBe("ambiguous");
    expect(bookingErrorKind(new TypeError("Failed to fetch"))).toBe("ambiguous");
  });
});
