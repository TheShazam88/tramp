import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import type { CancelBookingRequest } from "@/api/types";
import {
  Badge,
  Button,
  EmptyState,
  SectionHeading,
  Surface,
} from "@/components/ui/primitives";

export function BookingsPage() {
  const queryClient = useQueryClient();
  const [cancellationBookingId, setCancellationBookingId] = useState<string | null>(null);
  const [cancellationReason, setCancellationReason] = useState("");
  const [cancellationTotpCode, setCancellationTotpCode] = useState("");
  const [cancellationMasterKey, setCancellationMasterKey] = useState("");
  const [cancellationNotice, setCancellationNotice] = useState<{
    tone: "value" | "alert";
    message: string;
  } | null>(null);
  const cancellationRequestRef = useRef<CancelBookingRequest | null>(null);
  const cancellationTokenRef = useRef<{ bookingId: string; token: string } | null>(null);
  const cancellationIdempotencyRef = useRef<{
    bookingId: string;
    key: string;
  } | null>(null);
  const { data } = useQuery({
    queryKey: queryKeys.bookings,
    queryFn: travelWatchApi.getBookings,
  });
  const createDisruptionMutation = useMutation({
    mutationFn: travelWatchApi.triggerBookingDisruption,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings });
    },
  });
  const resolveDisruptionMutation = useMutation({
    mutationFn: travelWatchApi.resolveDisruption,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.bookings });
    },
  });
  const cancellationMutation = useMutation({
    mutationFn: async () => {
      const request = cancellationRequestRef.current;
      if (!request) {
        throw new Error("Secure cancellation details expired. Re-enter them and try again.");
      }
      let token = cancellationTokenRef.current;
      if (!token || token.bookingId !== request.bookingId) {
        const issued = await travelWatchApi.createCancellationApprovalToken(
          request.bookingId,
        );
        if (!issued.token) {
          throw new Error("Unable to create a secure cancellation approval token.");
        }
        token = { bookingId: request.bookingId, token: issued.token };
        cancellationTokenRef.current = token;
      }
      return travelWatchApi.cancelBooking({
        ...request,
        approvalToken: token.token,
      });
    },
    retry: false,
    onSuccess: async (result) => {
      const refund = result.refundAmount ? ` Refund: ${result.refundAmount}.` : "";
      setCancellationNotice({
        tone: "value",
        message: `Cancellation ${result.status.replace(/_/g, " ")}.${refund}`,
      });
      setCancellationBookingId(null);
      setCancellationReason("");
      cancellationTokenRef.current = null;
      cancellationIdempotencyRef.current = null;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.bookings }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }),
      ]);
    },
    onError: (error) => {
      setCancellationNotice({
        tone: "alert",
        message:
          error instanceof Error
            ? error.message
            : "Unable to complete secure cancellation.",
      });
    },
    onSettled: () => {
      cancellationRequestRef.current = null;
      setCancellationTotpCode("");
      setCancellationMasterKey("");
    },
  });

  if (!data) {
    return (
      <div className="stack">
        <Surface>Loading bookings...</Surface>
      </div>
    );
  }

  return (
    <div className="stack">
      <SectionHeading
        eyebrow="Bookings"
        title="Upcoming travel"
        description="Active bookings, ticketing progress, and cancellation or refund follow-up stay visible here without changing the app shell."
      />

      {data.fallbackNote ? <div className="notice notice-value">{data.fallbackNote}</div> : null}
      {cancellationNotice ? (
        <div
          className={`notice ${
            cancellationNotice.tone === "alert" ? "notice-alert" : "notice-value"
          }`}
          role={cancellationNotice.tone === "alert" ? "alert" : "status"}
        >
          {cancellationNotice.message}
        </div>
      ) : null}

      <div className="stack">
        {data.items.map((booking) => {
          const unresolvedDisruption = booking.disruptions?.find(
            (disruption) => disruption.status !== "resolved",
          );
          const cancellationAvailable =
            !booking.cancellationStatus &&
            ["booked", "ticketed"].includes(
              (booking.bookingStatus ?? "").toLowerCase(),
            );

          return (
            <Surface key={booking.id} className="watch-card">
              <div className="watch-topline">
                <div>
                  <h3>{booking.title}</h3>
                  <p className="item-copy">
                    {booking.when} · {booking.provider}
                  </p>
                </div>
                <Badge tone="value">{booking.status}</Badge>
              </div>
              <p className="hero-context">{booking.amount}</p>
              <div className="badge-row">
                {booking.bookingStatus ? (
                  <Badge tone="luxury">{booking.bookingStatus.replace(/_/g, " ")}</Badge>
                ) : null}
                {booking.cancellationStatus ? (
                  <Badge tone="alert">
                    {booking.cancellationStatus.replace(/_/g, " ")} cancellation
                  </Badge>
                ) : null}
                {booking.refundStatus ? <Badge tone="muted">{booking.refundStatus}</Badge> : null}
              </div>
              {booking.refundAmount ? (
                <p className="item-copy">Refund state: {booking.refundAmount}</p>
              ) : null}
              {booking.providerReference ? (
                <p className="item-copy">Provider ref: {booking.providerReference}</p>
              ) : null}
              {booking.statusDetail ? <p className="item-copy">{booking.statusDetail}</p> : null}
              {booking.calendarDetail ? <p className="item-copy">{booking.calendarDetail}</p> : null}
              {booking.notificationStatuses && booking.notificationStatuses.length > 0 ? (
                <ul className="info-list">
                  {booking.notificationStatuses.map((status) => (
                    <li key={status}>{status}</li>
                  ))}
                </ul>
              ) : null}
              {booking.disruptionStatuses && booking.disruptionStatuses.length > 0 ? (
                <ul className="info-list">
                  {booking.disruptionStatuses.map((status) => (
                    <li key={status}>{status}</li>
                  ))}
                </ul>
              ) : null}
              <div className="button-row">
                {booking.dealId ? (
                  <Button
                    variant="secondary"
                    to={`/deals/${booking.dealId}${booking.watchId ? `?watchId=${booking.watchId}` : ""}`}
                  >
                    Open deal review
                  </Button>
                ) : null}
                {booking.actions
                  .filter((action) => action !== "Open deal review")
                  .map((action) => (
                    <Button
                      key={action}
                      variant="ghost"
                      to={booking.dealId ? `/deals/${booking.dealId}` : "/bookings"}
                    >
                      {action}
                    </Button>
                  ))}
                {cancellationAvailable ? (
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => {
                      const opening = cancellationBookingId !== booking.id;
                      setCancellationBookingId(opening ? booking.id : null);
                      setCancellationReason("");
                      setCancellationTotpCode("");
                      setCancellationMasterKey("");
                      setCancellationNotice(null);
                      cancellationRequestRef.current = null;
                      if (
                        opening &&
                        cancellationIdempotencyRef.current?.bookingId !== booking.id
                      ) {
                        cancellationTokenRef.current = null;
                        cancellationIdempotencyRef.current = null;
                      }
                    }}
                    disabled={cancellationMutation.isPending}
                  >
                    {cancellationBookingId === booking.id
                      ? "Hide cancellation"
                      : "Secure cancellation"}
                  </Button>
                ) : null}
              </div>

              {cancellationBookingId === booking.id ? (
                <Surface className="inset-card">
                  <SectionHeading
                    eyebrow="Money-moving action"
                    title="Confirm cancellation"
                    description="Cancellation requires a signed single-use approval, your TOTP code, and the master key when the backend uses master-key mode."
                  />
                  <div className="form-grid">
                    <label className="field-stack field-span-full">
                      <span>Cancellation reason</span>
                      <input
                        className="text-input"
                        value={cancellationReason}
                        maxLength={255}
                        onChange={(event) =>
                          setCancellationReason(event.target.value)
                        }
                        disabled={cancellationMutation.isPending}
                      />
                    </label>
                    <label className="field-stack">
                      <span>Cancellation TOTP code</span>
                      <input
                        className="text-input"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        value={cancellationTotpCode}
                        onChange={(event) =>
                          setCancellationTotpCode(
                            event.target.value.replace(/\D/g, "").slice(0, 6),
                          )
                        }
                        disabled={cancellationMutation.isPending}
                      />
                    </label>
                    <label className="field-stack">
                      <span>Cancellation master-key passphrase</span>
                      <input
                        className="text-input"
                        type="password"
                        autoComplete="new-password"
                        spellCheck={false}
                        value={cancellationMasterKey}
                        onChange={(event) =>
                          setCancellationMasterKey(event.target.value)
                        }
                        disabled={cancellationMutation.isPending}
                      />
                    </label>
                  </div>
                  <div className="button-row">
                    <Button
                      type="button"
                      onClick={() => {
                        let idempotency =
                          cancellationIdempotencyRef.current;
                        if (!idempotency || idempotency.bookingId !== booking.id) {
                          idempotency = {
                            bookingId: booking.id,
                            key: crypto.randomUUID(),
                          };
                          cancellationIdempotencyRef.current = idempotency;
                        }
                        cancellationRequestRef.current = {
                          bookingId: booking.id,
                          reason: cancellationReason,
                          approvalToken: "",
                          totpCode: cancellationTotpCode,
                          masterKeyPassphrase: cancellationMasterKey,
                          idempotencyKey: idempotency.key,
                        };
                        cancellationMutation.mutate();
                      }}
                      disabled={
                        cancellationMutation.isPending ||
                        !/^\d{6}$/.test(cancellationTotpCode)
                      }
                    >
                      {cancellationMutation.isPending
                        ? "Cancelling..."
                        : "Confirm cancellation"}
                    </Button>
                  </div>
                </Surface>
              ) : null}

              <details className="form-disclosure">
                <summary>Local test tools</summary>
                <div className="stack-tight form-grid-gap-top">
                  <p className="helper-copy">
                    Local-only simulation controls. These test endpoints do not represent production
                    provider behavior.
                  </p>
                  <div className="button-row">
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() => createDisruptionMutation.mutate(booking.id)}
                      disabled={createDisruptionMutation.isPending}
                    >
                      {createDisruptionMutation.isPending ? "Injecting..." : "Simulate disruption"}
                    </Button>
                    {unresolvedDisruption ? (
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => resolveDisruptionMutation.mutate(unresolvedDisruption.id)}
                        disabled={resolveDisruptionMutation.isPending}
                      >
                        {resolveDisruptionMutation.isPending
                          ? "Resolving..."
                          : "Resolve disruption"}
                      </Button>
                    ) : null}
                  </div>
                </div>
              </details>
            </Surface>
          );
        })}
      </div>

      <EmptyState
        title="Archived bookings can live here next"
        copy="The route now has room for ticketing, refund, and provider-state follow-up, even when the backend only exposes part of that lifecycle."
      />
    </div>
  );
}
