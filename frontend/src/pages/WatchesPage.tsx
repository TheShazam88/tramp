import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import type { WatchSummary } from "@/api/types";
import {
  Badge,
  Button,
  EmptyState,
  SectionHeading,
  StatGrid,
  Surface,
} from "@/components/ui/primitives";
import { ApiError } from "@/api/client";

function formatSearchTime(value: string) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

function getErrorMessage(error: unknown, fallback: string) {
  if (error instanceof ApiError && typeof error.payload === "object" && error.payload) {
    const detail = (error.payload as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      return detail;
    }
  }

  if (error instanceof Error && error.message) {
    return error.message;
  }

  return fallback;
}

export function WatchesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data, error } = useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: travelWatchApi.getDashboard,
  });

  const searchNowMutation = useMutation({
    mutationFn: (watch: WatchSummary) => travelWatchApi.searchWatchNow(watch.id),
    onSuccess: async (result, watch) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });

      if (result.dealId) {
        navigate(`/deals/${result.dealId}?watchId=${watch.id}`, {
          state: {
            reviewSeed: {
              ...result.deal,
              id: result.dealId,
              watchId: watch.id,
              route: result.deal?.route || watch.route,
              cabin: result.deal?.cabin || watch.cabin,
              context: result.deal?.context || watch.insight,
              price: result.deal?.price || watch.bestNow,
            },
          },
        });
      }
    },
  });

  const watchActionMutation = useMutation({
    mutationFn: async (payload: { watch: WatchSummary; action: "pause" | "resume" | "ignore" }) => {
      if (payload.action === "ignore") {
        if (!payload.watch.currentDealId) {
          throw new Error("There is no active deal to ignore on this watch.");
        }
        return travelWatchApi.rejectDeal({ dealId: payload.watch.currentDealId, reason: "other" });
      }
      await travelWatchApi.updateWatchStatus(payload.watch.id, payload.action);
      return null;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
    },
  });

  if (!data) {
    return (
      <div className="stack">
        <Surface>{error ? getErrorMessage(error, "Unable to load watches.") : "Loading watches..."}</Surface>
      </div>
    );
  }

  return (
    <div className="stack">
      <SectionHeading
        eyebrow="Trips"
        title="Your trips"
        description="A mobile-first dashboard for active watches, live pricing context, and quick actions."
        action={<Button to="/watches/new">Create watch</Button>}
      />

      <StatGrid items={data.highlights} />

      {error ? <div className="notice notice-alert">{getErrorMessage(error, "Unable to load watches.")}</div> : null}

      {searchNowMutation.isError ? (
        <div className="notice notice-alert">
          {getErrorMessage(searchNowMutation.error, "Unable to run Search now for this watch.")}
        </div>
      ) : null}

      {searchNowMutation.data?.queued ? (
        <div className="notice notice-value">
          Live search requested. Refresh the dashboard in a moment if the deal does not appear immediately.
        </div>
      ) : null}
      {watchActionMutation.isError ? (
        <div className="notice notice-alert">
          {getErrorMessage(watchActionMutation.error, "Unable to update this watch action.")}
        </div>
      ) : null}
      {watchActionMutation.data?.detail ? (
        <div className="notice notice-value">{watchActionMutation.data.detail}</div>
      ) : null}

      {data.watches.length === 0 ? (
        <EmptyState
          title="No watches yet"
          copy="Create the first watch to start loading real dashboard data from the backend."
          action={<Button to="/watches/new">Create watch</Button>}
        />
      ) : null}

      <div className="stack">
        {data.watches.map((watch) => {
          const firstReadinessBlocker = watch.readiness?.blockers[0];
          const readinessResolutions = watch.readiness?.resolutions ?? [];

          return (
            <Surface key={watch.id} className="watch-card">
              <div className="watch-topline">
                <div>
                  <div className="badge-row">
                    <Badge tone={watch.status === "active" ? "value" : "muted"}>
                      {watch.status}
                    </Badge>
                    <Badge tone="luxury">{watch.framing}</Badge>
                    {watch.badges.map((badge) => (
                      <Badge key={badge.label} tone={badge.tone}>
                        {badge.label}
                      </Badge>
                    ))}
                  </div>
                  <h3>{watch.route}</h3>
                  <p className="item-copy">
                    {watch.dates} · {watch.travelers} · {watch.cabin}
                  </p>
                </div>
                <div className="watch-best">
                  <span>Best now</span>
                  <strong>{watch.bestNow}</strong>
                </div>
              </div>

              <p className="watch-insight">{watch.insight}</p>
              <p className="item-copy">
                {watch.cadence}
                {watch.lastSearchedAt
                  ? ` · Last search ${formatSearchTime(watch.lastSearchedAt)}`
                  : " · No search yet"}
              </p>
              {watch.readiness ? (
                <p className="item-copy">
                  Readiness {watch.readiness.score}/100 · {watch.readiness.label}
                </p>
              ) : null}
              {firstReadinessBlocker ? (
                <div className="notice notice-alert">
                  <p className="field-label">First readiness blocker</p>
                  <p className="item-title">{firstReadinessBlocker}</p>
                  {readinessResolutions.length > 0 ? (
                    <div className="button-row">
                      {readinessResolutions.map((resolution) => (
                        <Button
                          key={`${resolution.code}-${resolution.path}`}
                          variant="secondary"
                          to={resolution.path}
                        >
                          {resolution.label}
                        </Button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
              {watch.currentDealStatus ? (
                <p className="item-copy">
                  Current deal status: {watch.currentDealStatus.replace(/_/g, " ")}
                </p>
              ) : null}

              <div className="button-row">
                {watch.ctaActions.map((action) => {
                  if (action.key === "search_now") {
                    return (
                      <Button
                        key={action.key}
                        type="button"
                        onClick={() => searchNowMutation.mutate(watch)}
                        disabled={searchNowMutation.isPending || !action.enabled}
                      >
                        {searchNowMutation.isPending ? "Searching..." : action.label}
                      </Button>
                    );
                  }
                  if (action.key === "open_deal" || action.key === "book_now") {
                    if (!watch.currentDealId) {
                      return null;
                    }
                    return (
                      <Button
                        key={action.key}
                        variant={
                          action.tone === "ghost"
                            ? "ghost"
                            : action.tone === "secondary"
                              ? "secondary"
                              : "primary"
                        }
                        to={`/deals/${watch.currentDealId}?watchId=${watch.id}`}
                        disabled={!action.enabled}
                      >
                        {action.label}
                      </Button>
                    );
                  }
                  if (action.key === "pause_watch" || action.key === "resume_watch") {
                    return (
                      <Button
                        key={action.key}
                        type="button"
                        variant={
                          action.tone === "ghost"
                            ? "ghost"
                            : action.tone === "secondary"
                              ? "secondary"
                              : "primary"
                        }
                        onClick={() =>
                          watchActionMutation.mutate({
                            watch,
                            action: action.key === "pause_watch" ? "pause" : "resume",
                          })
                        }
                        disabled={watchActionMutation.isPending || !action.enabled}
                      >
                        {action.label}
                      </Button>
                    );
                  }
                  if (action.key === "ignore") {
                    return (
                      <Button
                        key={action.key}
                        type="button"
                        variant={
                          action.tone === "ghost"
                            ? "ghost"
                            : action.tone === "secondary"
                              ? "secondary"
                              : "primary"
                        }
                        onClick={() => watchActionMutation.mutate({ watch, action: "ignore" })}
                        disabled={watchActionMutation.isPending || !action.enabled}
                      >
                        {action.label}
                      </Button>
                    );
                  }
                  return null;
                })}
                <Button variant="secondary" to={`/watches/${watch.id}/edit`}>
                  Edit
                </Button>
                <Button variant="ghost" to="/bookings">
                  {watch.status === "paused" ? "Review pause" : "Open bookings"}
                </Button>
              </div>
            </Surface>
          );
        })}
      </div>
    </div>
  );
}
