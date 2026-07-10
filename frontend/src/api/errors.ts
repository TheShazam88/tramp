import { ApiError } from "@/api/client";

const fieldLabels: Record<string, string> = {
  approval_token: "Approval token",
  deal_id: "Deal",
  idempotency_key: "Booking attempt",
  master_key_passphrase: "Master-key passphrase",
  payment_method_id: "Payment method",
  totp_code: "TOTP code",
};

function validationDetailMessage(detail: unknown) {
  if (typeof detail === "string") {
    return detail.trim();
  }
  if (!detail || typeof detail !== "object") {
    return "";
  }

  const item = detail as { loc?: unknown; msg?: unknown };
  if (typeof item.msg !== "string" || !item.msg.trim()) {
    return "";
  }
  const location = Array.isArray(item.loc)
    ? item.loc.filter((part): part is string => typeof part === "string").at(-1)
    : undefined;
  const label = location
    ? fieldLabels[location] ??
      location
        .replace(/_/g, " ")
        .replace(/^\w/, (character) => character.toUpperCase())
    : "";
  return label ? `${label}: ${item.msg.trim()}` : item.msg.trim();
}

export function getApiErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError && error.payload && typeof error.payload === "object") {
    const detail = (error.payload as { detail?: unknown }).detail;
    if (Array.isArray(detail)) {
      const messages = detail.map(validationDetailMessage).filter(Boolean);
      if (messages.length > 0) {
        return messages.join(" ");
      }
    }

    const message = validationDetailMessage(detail);
    if (message) {
      return message;
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message.trim();
  }
  return fallback;
}

export function bookingErrorKind(error: unknown): "definite" | "ambiguous" {
  return error instanceof ApiError && error.status >= 400 && error.status < 500
    ? "definite"
    : "ambiguous";
}
