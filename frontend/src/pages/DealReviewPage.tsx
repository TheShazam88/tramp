import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useLocation, useParams, useSearchParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import type { DealData } from "@/api/types";
import {
  Badge,
  Button,
  InfoList,
  PillRow,
  ScoreBar,
  SectionHeading,
  Surface,
} from "@/components/ui/primitives";

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

function toneForStatus(status?: string | null) {
  switch (status) {
    case "confirmed":
    case "ticketed":
      return "value" as const;
    case "processing":
    case "pending_ticketing":
      return "luxury" as const;
    case "requested":
    case "failed":
    case "refunded":
      return "alert" as const;
    default:
      return "muted" as const;
  }
}

interface DealReviewLocationState {
  reviewSeed?: Partial<DealData>;
}

export function DealReviewPage() {
  const { dealId = "deal-118400" } = useParams();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const watchId = searchParams.get("watchId") ?? undefined;
  const approvalTokenFromLink = searchParams.get("approvalToken") ?? "";
  const reviewSeed = useMemo(
    () => ((location.state as DealReviewLocationState | null)?.reviewSeed ?? null),
    [location.state],
  );
  const [showApprovalForm, setShowApprovalForm] = useState(false);
  const [totpCode, setTotpCode] = useState("");
  const [approvalNotice, setApprovalNotice] = useState<string | null>(null);

  const { data, error } = useQuery({
    queryKey: queryKeys.deal(dealId, watchId),
    queryFn: () => travelWatchApi.getDealReview(dealId, { watchId, seed: reviewSeed }),
  });
  const approvalTokenVerification = useQuery({
    queryKey: ["deal-approval-token", dealId, approvalTokenFromLink],
    queryFn: () => travelWatchApi.verifyApprovalToken({ dealId, token: approvalTokenFromLink }),
    enabled: approvalTokenFromLink.length > 0,
  });

  const approvalMutation = useMutation({
    mutationFn: async (payload: { totpCode: string }) => {
      const token =
        approvalTokenFromLink ||
        (await travelWatchApi.createApprovalToken(dealId)).token;
      return travelWatchApi.confirmDealIntent({
        dealId,
        token,
        totpCode: payload.totpCode,
      });
    },
    onSuccess: async (result) => {
      setApprovalNotice(result.detail);
      setShowApprovalForm(false);
      setTotpCode("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.deal(dealId, watchId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }),
      ]);
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (reason: string) => travelWatchApi.rejectDeal({ dealId, reason }),
    onSuccess: async (result) => {
      setApprovalNotice(result.detail);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.deal(dealId, watchId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }),
      ]);
    },
  });

  if (!data) {
    return (
      <div className="stack">
        <Surface>{error ? getErrorMessage(error, "Unable to load the deal review.") : "Loading deal review..."}</Surface>
      </div>
    );
  }

  const deal = data.deal;
  const dealIntentLocked = ["confirmed", "rejected", "booked", "expired", "failed"].includes(
    deal.dealStatus ?? "",
  );
  const bookNowAction = deal.ctaActions.find((action) => action.key === "book_now");
  const ignoreAction = deal.ctaActions.find((action) => action.key === "ignore");

  return (
    <div className="stack">
      <Surface className="page-hero">
        <SectionHeading
          eyebrow="Screen 3"
          title={`${deal.route} · ${deal.cabin}`}
            description="Review price context, loyalty mapping, coverage, and warnings before recording approval or rejection intent."
          action={
            <Badge tone={deal.bookingStatus ? "value" : deal.expiresAt ? "alert" : "muted"}>
              {deal.bookingStatus || (deal.expiresAt ? `Expires ${deal.expiresAt}` : deal.dealStatus || "Review")}
            </Badge>
          }
        />

        {data.fallbackNote ? <div className="notice notice-value">{data.fallbackNote}</div> : null}
        {error ? <div className="notice notice-alert">{getErrorMessage(error, "Unable to refresh this deal.")}</div> : null}
        {approvalNotice ? <div className="notice notice-value">{approvalNotice}</div> : null}
        {approvalTokenFromLink ? (
          approvalTokenVerification.isError ? (
            <div className="notice notice-alert">
              {getErrorMessage(
                approvalTokenVerification.error,
                "This secure approval link is no longer valid. Generate a fresh review link from the deal.",
              )}
            </div>
          ) : approvalTokenVerification.data?.valid ? (
            <div className="notice notice-value">
              Opened from a secure notification link.
              {approvalTokenVerification.data.expiresAt ? ` Link expires ${approvalTokenVerification.data.expiresAt}.` : ""}
            </div>
          ) : null
        ) : null}
        {approvalMutation.isError ? (
          <div className="notice notice-alert">
            {getErrorMessage(approvalMutation.error, "Unable to record approval intent for this deal.")}
          </div>
        ) : null}
        {rejectMutation.isError ? (
          <div className="notice notice-alert">
            {getErrorMessage(rejectMutation.error, "Unable to record rejection feedback for this deal.")}
          </div>
        ) : null}

        <PillRow items={["Best value", "Max luxury", "Cheapest ok"]} selected="Best value" />
        <div className="badge-row">
          {deal.dealStatus ? <Badge tone={toneForStatus(deal.dealStatus)}>{deal.dealStatus.replace(/_/g, " ")}</Badge> : null}
          {deal.bookingStatus ? (
            <Badge tone={toneForStatus(deal.bookingStatus)}>{deal.bookingStatus.replace(/_/g, " ")}</Badge>
          ) : null}
          {deal.cancellationStatus ? (
            <Badge tone={toneForStatus(deal.cancellationStatus)}>
              {deal.cancellationStatus.replace(/_/g, " ")} cancellation
            </Badge>
          ) : null}
          {deal.refundStatus ? <Badge tone="muted">{deal.refundStatus}</Badge> : null}
          {deal.badges.map((badge) => (
            <Badge key={badge.label} tone={badge.tone}>
              {badge.label}
            </Badge>
          ))}
        </div>

        <div className="price-hero">
          <div>
            <p className="hero-price">{deal.price}</p>
            {deal.wasPrice ? <p className="hero-strike">Was {deal.wasPrice}</p> : null}
          </div>
          <Badge tone="luxury">{deal.provider || "All-in"}</Badge>
        </div>

        <p className="hero-context">{deal.context}</p>
        {deal.breakdown ? <p className="item-copy">{deal.breakdown}</p> : null}
        {deal.refundAmount ? <p className="item-copy">Refund state: {deal.refundAmount}</p> : null}
        {deal.approvalDetail ? <p className="item-copy">{deal.approvalDetail}</p> : null}

        <ScoreBar value={deal.score} label="Deal score" />

        <div className="split-layout">
          <Surface className="inset-card">
            <SectionHeading
              eyebrow="Why this is winning"
              title="Value framing"
              description="The design keeps the signature score bar and price context central."
            />
            <InfoList items={deal.details} />
          </Surface>

          <Surface className="inset-card">
            <SectionHeading
              eyebrow="Booking readiness"
              title={deal.readiness ? `${deal.readiness.score}/100 · ${deal.readiness.label}` : "Approval context"}
              description="Transparent blockers and warnings now drive both the page explanation and the CTA state."
            />
            {deal.readiness?.blockers?.length ? (
              <div className="stack-tight">
                {deal.readiness.blockers.map((warning) => (
                  <Badge key={warning} tone="alert">
                    {warning}
                  </Badge>
                ))}
              </div>
            ) : null}
            {deal.readiness?.warnings?.length ? (
              <div className="stack-tight">
                {deal.readiness.warnings.map((warning) => (
                  <Badge key={warning} tone="muted">
                    {warning}
                  </Badge>
                ))}
              </div>
            ) : null}
            <InfoList items={deal.loyaltyPlan} />
            <div className="stack-tight">
              {deal.warnings.map((warning) => (
                <Badge key={warning} tone="alert">
                  {warning}
                </Badge>
              ))}
            </div>
          </Surface>
        </div>

        <Surface className="inset-card">
          <SectionHeading
            eyebrow="Coverage"
            title="Honest search scope"
            description="Coverage stays explicit instead of implying a global minimum."
          />
          <InfoList items={deal.coverage} />
        </Surface>

        {deal.timeline ? (
          <Surface className="inset-card">
            <SectionHeading
              eyebrow="History"
              title="Price timeline"
              description="This exposes the saved observation history so the deal is backed by movement, not just one score."
            />
            <div className="summary-grid">
              <Surface className="field-card">
                <p className="field-label">Current</p>
                <strong>{deal.timeline.currentPrice || deal.price}</strong>
              </Surface>
              <Surface className="field-card">
                <p className="field-label">Target</p>
                <strong>{deal.timeline.targetPrice || "Not set"}</strong>
              </Surface>
              <Surface className="field-card">
                <p className="field-label">Glide limit</p>
                <strong>{deal.timeline.glideLimit || "Not set"}</strong>
              </Surface>
            </div>
            <p className="item-copy">{deal.timeline.trendSummary}</p>
            <div className="stack-tight">
              {deal.timeline.points.map((point) => (
                <Surface key={`${point.observedAt}-${point.price}`} className="list-card inset-card">
                  <div className="watch-topline">
                    <div>
                      <strong>{point.price}</strong>
                      <p className="item-copy">
                        {point.observedAt} · {point.label}
                      </p>
                    </div>
                    <Badge tone="muted">
                      {point.percentile !== undefined ? `P${Math.round(point.percentile)}` : point.source || "Saved"}
                    </Badge>
                  </div>
                </Surface>
              ))}
            </div>
          </Surface>
        ) : null}

        {showApprovalForm ? (
          <Surface className="inset-card approval-card">
            <SectionHeading
              eyebrow="Secure approval"
              title="Confirm approval intent"
              description="V3 records a secure TOTP-backed approval decision here. The actual booking executor remains a later deterministic step."
            />

            <div className="form-grid">
              <div className="field-stack">
                <label htmlFor="approval-totp">Six-digit TOTP code</label>
                <input
                  id="approval-totp"
                  className="text-input"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={totpCode}
                  onChange={(event) => setTotpCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="123456"
                />
              </div>
            </div>

            {!data.approvalAvailable ? (
              <div className="notice notice-alert">
                The live approval-intent endpoint is intentionally unavailable on this backend right now.
              </div>
            ) : null}

            <div className="button-row">
              <Button
                type="button"
                onClick={() => approvalMutation.mutate({ totpCode })}
                disabled={
                  approvalMutation.isPending ||
                  approvalTokenVerification.isFetching ||
                  (approvalTokenFromLink.length > 0 && approvalTokenVerification.data?.valid === false) ||
                  !data.approvalAvailable ||
                  totpCode.length !== 6
                }
              >
                {approvalMutation.isPending ? "Recording..." : "Confirm approval"}
              </Button>
              <Button type="button" variant="secondary" onClick={() => setShowApprovalForm(false)}>
                Cancel
              </Button>
            </div>
          </Surface>
        ) : null}
      </Surface>

      <Surface className="inset-card">
        <SectionHeading
          eyebrow="Reject"
          title="Tell TRAMP what to avoid next"
          description="Rejection now feeds the watch so future proposals can adapt instead of repeating the same mistake."
        />
        <div className="button-row">
          {[
            ["too_pricey", "Too pricey"],
            ["not_luxurious_enough", "Not luxurious enough"],
            ["layover_too_long", "Layover too long"],
            ["wrong_airline", "Wrong airline"],
            ["wrong_hotel", "Wrong hotel"],
            ["wrong_area", "Wrong area"],
            ["other", "Other"],
          ].map(([value, label]) => (
            <Button
              key={value}
              type="button"
              variant="secondary"
              onClick={() => rejectMutation.mutate(value)}
              disabled={rejectMutation.isPending || dealIntentLocked || ignoreAction?.enabled === false}
            >
              {rejectMutation.isPending ? "Saving..." : label}
            </Button>
          ))}
        </div>
      </Surface>

      <div className="button-row">
        <Button
          type="button"
          onClick={() => setShowApprovalForm((current) => !current)}
          disabled={
            dealIntentLocked ||
            bookNowAction?.enabled === false ||
            Boolean(deal.readiness?.blockers?.length)
          }
        >
          {showApprovalForm ? "Hide approval" : bookNowAction?.label || "Book now"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          onClick={() => rejectMutation.mutate("other")}
          disabled={rejectMutation.isPending || dealIntentLocked || ignoreAction?.enabled === false}
        >
          {ignoreAction?.label || "Ignore"}
        </Button>
        <Button variant="secondary" to="/bookings">
          Open bookings
        </Button>
        <Button variant="ghost" to="/watches">
          Back to watches
        </Button>
      </div>
    </div>
  );
}
