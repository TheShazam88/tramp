import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useLocation, useParams, useSearchParams } from "react-router-dom";

import { ApiError } from "@/api/client";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import type { BookDealRequest, DealData } from "@/api/types";
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

function readinessResolutionFor(blocker: string) {
  const normalized = blocker.toLowerCase();

  if (
    normalized.includes("payment") ||
    normalized.includes("traveler") ||
    normalized.includes("passport")
  ) {
    return { to: "/profile", label: "Open profile setup" };
  }
  if (normalized.includes("two-factor") || normalized.includes("authentication")) {
    return { to: "/setup/2fa", label: "Set up two-factor authentication" };
  }
  if (normalized.includes("provider") || normalized.includes("inventory")) {
    return { to: "/admin/integrations", label: "Review provider integrations" };
  }
  if (
    normalized.includes("watch") ||
    normalized.includes("deal") ||
    normalized.includes("expired") ||
    normalized.includes("refresh")
  ) {
    return { to: "/watches", label: "Open watches" };
  }
  return { to: "/profile/presets", label: "Review profile presets" };
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
  const [paymentMethodId, setPaymentMethodId] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [masterKeyPassphrase, setMasterKeyPassphrase] = useState("");
  const [approvalNotice, setApprovalNotice] = useState<string | null>(null);

  const { data, error } = useQuery({
    queryKey: queryKeys.deal(dealId, watchId),
    queryFn: () => travelWatchApi.getDealReview(dealId, { watchId, seed: reviewSeed }),
  });
  const { data: profileWorkspace, error: profileError } = useQuery({
    queryKey: queryKeys.profile,
    queryFn: travelWatchApi.getProfileWorkspace,
  });
  const approvalTokenVerification = useQuery({
    queryKey: ["deal-approval-token", dealId, approvalTokenFromLink],
    queryFn: () => travelWatchApi.verifyApprovalToken({ dealId, token: approvalTokenFromLink }),
    enabled: approvalTokenFromLink.length > 0,
  });

  const bookingMutation = useMutation({
    mutationFn: (payload: BookDealRequest) => travelWatchApi.bookDeal(payload),
    retry: false,
    onSuccess: async (result) => {
      const bookingDetails = [
        result.confirmationNote,
        result.provider ? `Provider: ${result.provider}.` : "",
        result.amount ? `Amount: ${result.amount}.` : "",
        result.bookingStatus ? `Status: ${result.bookingStatus.replace(/_/g, " ")}.` : "",
      ].filter(Boolean);
      setApprovalNotice(bookingDetails.join(" "));
      setShowApprovalForm(false);
      setPaymentMethodId("");
      setTotpCode("");
      setMasterKeyPassphrase("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.deal(dealId, watchId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }),
        queryClient.invalidateQueries({ queryKey: queryKeys.bookings }),
        queryClient.invalidateQueries({ queryKey: queryKeys.profile }),
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
  const bookingLocked = ["rejected", "booked", "expired", "failed"].includes(deal.dealStatus ?? "");
  const bookNowAction = deal.ctaActions.find((action) => action.key === "book_now");
  const ignoreAction = deal.ctaActions.find((action) => action.key === "ignore");
  const readinessBlockers = deal.readiness?.blockers ?? [];
  const hasReadinessBlockers = readinessBlockers.length > 0;
  const hasNoPaymentMethods = profileWorkspace?.paymentMethods.length === 0;
  const readinessBlockersForGuidance = hasNoPaymentMethods
    ? readinessBlockers.filter((blocker) => !blocker.toLowerCase().includes("payment"))
    : readinessBlockers;
  const readinessResolutionLinks = Array.from(
    new Map(
      readinessBlockersForGuidance.map((blocker) => {
        const resolution = readinessResolutionFor(blocker);
        return [resolution.to, resolution] as const;
      }),
    ).values(),
  );
  const linkedApprovalUnavailable =
    approvalTokenFromLink.length > 0 &&
    (approvalTokenVerification.isFetching ||
      approvalTokenVerification.isError ||
      approvalTokenVerification.data?.valid !== true);
  const bookingCanSubmit =
    data.approvalAvailable &&
    bookNowAction?.enabled !== false &&
    !bookingLocked &&
    !hasReadinessBlockers &&
    paymentMethodId.length > 0 &&
    /^\d{6}$/.test(totpCode) &&
    !bookingMutation.isPending &&
    !linkedApprovalUnavailable;

  const closeSecureBookingForm = () => {
    setShowApprovalForm(false);
    setPaymentMethodId("");
    setTotpCode("");
    setMasterKeyPassphrase("");
    bookingMutation.reset();
  };

  return (
    <div className="stack">
      <Surface className="page-hero">
        <SectionHeading
          eyebrow="Screen 3"
          title={`${deal.route} · ${deal.cabin}`}
          description="Review price context, loyalty mapping, coverage, and warnings before secure booking or rejection."
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
        {bookingMutation.isError ? (
          <div className="notice notice-alert">
            {getErrorMessage(bookingMutation.error, "Unable to complete this booking.")}
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
              eyebrow="Secure booking"
              title="Confirm and book"
              description="Choose a saved payment method and verify this booking with your six-digit TOTP code."
            />

            <div className="form-grid">
              {profileWorkspace?.paymentMethods.length ? (
                <div className="field-stack">
                  <label htmlFor="booking-payment-method">Saved payment method</label>
                  <select
                    id="booking-payment-method"
                    className="text-input"
                    value={paymentMethodId}
                    onChange={(event) => setPaymentMethodId(event.target.value)}
                  >
                    <option value="">Select a payment method</option>
                    {profileWorkspace.paymentMethods.map((paymentMethod) => {
                      const expiry =
                        paymentMethod.expMonth && paymentMethod.expYear
                          ? `, expires ${paymentMethod.expMonth}/${paymentMethod.expYear}`
                          : "";
                      return (
                        <option key={paymentMethod.id} value={paymentMethod.id}>
                          {paymentMethod.label} | {paymentMethod.brand || "Card"} ending{" "}
                          {paymentMethod.last4 || "----"}
                          {expiry}
                        </option>
                      );
                    })}
                  </select>
                  <p className="helper-copy">Only masked card details are shown. Card secrets stay protected.</p>
                </div>
              ) : profileWorkspace ? (
                <div className="notice notice-alert field-span-full">
                  <p className="item-title">No saved payment methods</p>
                  <p className="item-copy">
                    Add a payment method in your profile before booking this deal.
                  </p>
                  <Button variant="secondary" to="/profile">
                    Manage payment methods
                  </Button>
                </div>
              ) : (
                <div className="muted-card field-span-full">Loading saved payment methods...</div>
              )}

              <div className="field-stack">
                <label htmlFor="booking-totp">Six-digit TOTP code</label>
                <input
                  id="booking-totp"
                  className="text-input"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  value={totpCode}
                  onChange={(event) => setTotpCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="123456"
                />
              </div>

              <div className="field-stack">
                <label htmlFor="booking-master-key">Master-key passphrase (optional)</label>
                <input
                  id="booking-master-key"
                  className="text-input"
                  type="password"
                  autoComplete="off"
                  spellCheck={false}
                  value={masterKeyPassphrase}
                  onChange={(event) => setMasterKeyPassphrase(event.target.value)}
                  placeholder="Leave blank when not required"
                />
                <p className="helper-copy">
                  Your backend security mode determines whether this passphrase is required.
                </p>
              </div>
            </div>

            {profileError ? (
              <div className="notice notice-alert">
                {getErrorMessage(profileError, "Unable to load saved payment methods.")}
              </div>
            ) : null}

            {!data.approvalAvailable ? (
              <div className="notice notice-alert">
                Booking approval is unavailable for this deal right now.
              </div>
            ) : null}

            <div className="button-row">
              <Button
                type="button"
                onClick={() =>
                  bookingMutation.mutate({
                    dealId,
                    paymentMethodId,
                    totpCode,
                    masterKeyPassphrase,
                  })
                }
                disabled={!bookingCanSubmit}
              >
                {bookingMutation.isPending ? "Booking..." : "Book now"}
              </Button>
              <Button type="button" variant="secondary" onClick={closeSecureBookingForm}>
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

      {hasNoPaymentMethods ? (
        <div className="notice notice-alert">
          <p className="item-title">Add a saved payment method</p>
          <p className="item-copy">
            A saved payment method is required before TRAMP can book this deal. Add one in your profile,
            then return to this review.
          </p>
          <Button variant="secondary" to="/profile">
            Add payment method
          </Button>
        </div>
      ) : null}

      {readinessBlockersForGuidance.length > 0 ? (
        <div className="notice notice-alert">
          <p className="item-title">Resolve booking readiness</p>
          <p className="item-copy">Book now stays disabled until these setup items are resolved.</p>
          <ul className="info-list">
            {readinessBlockersForGuidance.map((blocker) => (
              <li key={blocker}>{blocker}</li>
            ))}
          </ul>
          <div className="button-row">
            {readinessResolutionLinks.map((resolution) => (
              <Button key={resolution.to} variant="secondary" to={resolution.to}>
                {resolution.label}
              </Button>
            ))}
          </div>
        </div>
      ) : null}

      <div className="button-row">
        <Button
          type="button"
          onClick={() => {
            if (showApprovalForm) {
              closeSecureBookingForm();
              return;
            }
            bookingMutation.reset();
            setApprovalNotice(null);
            setShowApprovalForm(true);
          }}
          disabled={
            bookingLocked ||
            bookNowAction?.enabled === false ||
            hasReadinessBlockers
          }
        >
          {showApprovalForm ? "Hide booking form" : bookNowAction?.label || "Book now"}
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
