import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import {
  Badge,
  Button,
  EmptyState,
  SectionHeading,
  Surface,
} from "@/components/ui/primitives";

export function BookingsPage() {
  const queryClient = useQueryClient();
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

      <div className="stack">
        {data.items.map((booking) => (
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
              {booking.bookingStatus ? <Badge tone="luxury">{booking.bookingStatus.replace(/_/g, " ")}</Badge> : null}
              {booking.cancellationStatus ? (
                <Badge tone="alert">{booking.cancellationStatus.replace(/_/g, " ")} cancellation</Badge>
              ) : null}
              {booking.refundStatus ? <Badge tone="muted">{booking.refundStatus}</Badge> : null}
            </div>
            {booking.refundAmount ? <p className="item-copy">Refund state: {booking.refundAmount}</p> : null}
            {booking.providerReference ? <p className="item-copy">Provider ref: {booking.providerReference}</p> : null}
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
                <Button variant="secondary" to={`/deals/${booking.dealId}${booking.watchId ? `?watchId=${booking.watchId}` : ""}`}>
                  Open deal review
                </Button>
              ) : null}
              {booking.actions
                .filter((action) => action !== "Open deal review")
                .map((action) => (
                  <Button key={action} variant="ghost" to={booking.dealId ? `/deals/${booking.dealId}` : "/bookings"}>
                    {action}
                  </Button>
                ))}
              <Button
                type="button"
                variant="secondary"
                onClick={() => createDisruptionMutation.mutate(booking.id)}
                disabled={createDisruptionMutation.isPending}
              >
                {createDisruptionMutation.isPending ? "Injecting..." : "Simulate disruption"}
              </Button>
              {booking.disruptions?.some((disruption) => disruption.status !== "resolved") ? (
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => {
                    const unresolved = booking.disruptions?.find((disruption) => disruption.status !== "resolved");
                    if (unresolved) {
                      resolveDisruptionMutation.mutate(unresolved.id);
                    }
                  }}
                  disabled={resolveDisruptionMutation.isPending}
                >
                  {resolveDisruptionMutation.isPending ? "Resolving..." : "Resolve disruption"}
                </Button>
              ) : null}
            </div>
          </Surface>
        ))}
      </div>

      <EmptyState
        title="Archived bookings can live here next"
        copy="The route now has room for ticketing, refund, and provider-state follow-up, even when the backend only exposes part of that lifecycle."
      />
    </div>
  );
}
