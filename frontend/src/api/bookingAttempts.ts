export type StoredBookingAttemptState =
  | "starting"
  | "submitted"
  | "reconciling"
  | "manual_recovery";

export interface StoredBookingAttempt {
  version: 1;
  dealId: string;
  idempotencyKey: string;
  paymentMethodId: string;
  state: StoredBookingAttemptState;
  code?: string;
  message?: string;
}

function storageKey(dealId: string) {
  return `tramp.booking-attempt.${dealId}`;
}

export function saveStoredBookingAttempt(attempt: StoredBookingAttempt) {
  const sanitized: StoredBookingAttempt = {
    version: 1,
    dealId: attempt.dealId,
    idempotencyKey: attempt.idempotencyKey,
    paymentMethodId: attempt.paymentMethodId,
    state: attempt.state,
    ...(attempt.code ? { code: attempt.code } : {}),
    ...(attempt.message ? { message: attempt.message } : {}),
  };
  sessionStorage.setItem(storageKey(attempt.dealId), JSON.stringify(sanitized));
}

export function loadStoredBookingAttempt(dealId: string): StoredBookingAttempt | null {
  const key = storageKey(dealId);
  const raw = sessionStorage.getItem(key);
  if (!raw) {
    return null;
  }

  try {
    const value = JSON.parse(raw) as Partial<StoredBookingAttempt>;
    const validState = ["starting", "submitted", "reconciling", "manual_recovery"].includes(
      value.state ?? "",
    );
    if (
      value.version !== 1 ||
      value.dealId !== dealId ||
      typeof value.idempotencyKey !== "string" ||
      !value.idempotencyKey ||
      typeof value.paymentMethodId !== "string" ||
      !value.paymentMethodId ||
      !validState
    ) {
      sessionStorage.removeItem(key);
      return null;
    }
    return {
      version: 1,
      dealId,
      idempotencyKey: value.idempotencyKey,
      paymentMethodId: value.paymentMethodId,
      state: value.state as StoredBookingAttemptState,
      ...(typeof value.code === "string" && value.code ? { code: value.code } : {}),
      ...(typeof value.message === "string" && value.message
        ? { message: value.message }
        : {}),
    };
  } catch {
    sessionStorage.removeItem(key);
    return null;
  }
}

export function clearStoredBookingAttempt(dealId: string) {
  sessionStorage.removeItem(storageKey(dealId));
}
