export interface MockBookingAttemptMetadata {
  idempotencyKey: string;
  dealId: string;
  paymentMethodId: string;
  status: "booked";
  bookingId: string;
  bookingStatus: string;
  trampStampsAwarded: number;
  trampStampBalance: number;
}

const mockBookingAttempts = new Map<string, Readonly<MockBookingAttemptMetadata>>();

export function storeMockBookingAttempt(metadata: MockBookingAttemptMetadata) {
  const safeMetadata: Readonly<MockBookingAttemptMetadata> = Object.freeze({
    idempotencyKey: metadata.idempotencyKey,
    dealId: metadata.dealId,
    paymentMethodId: metadata.paymentMethodId,
    status: metadata.status,
    bookingId: metadata.bookingId,
    bookingStatus: metadata.bookingStatus,
    trampStampsAwarded: metadata.trampStampsAwarded,
    trampStampBalance: metadata.trampStampBalance,
  });
  mockBookingAttempts.set(safeMetadata.idempotencyKey, safeMetadata);
}

export function getMockBookingAttempt(idempotencyKey: string) {
  return mockBookingAttempts.get(idempotencyKey);
}

export function inspectMockBookingAttempts() {
  return Array.from(mockBookingAttempts.values(), (attempt) => ({ ...attempt }));
}
