import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  useBeforeUnload,
  useBlocker,
  useLocation,
  useParams,
  useSearchParams,
} from "react-router-dom";

import {
  clearStoredBookingAttempt,
  loadStoredBookingAttempt,
  saveStoredBookingAttempt,
} from "@/api/bookingAttempts";
import type { StoredBookingAttempt } from "@/api/bookingAttempts";
import { ApiError } from "@/api/client";
import {
  bookingErrorKind,
  getApiErrorMessage,
  getBookingConflictDetail,
} from "@/api/errors";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import type {
  BookDealRequest,
  BookingAttemptReconciliation,
  DealApprovalResult,
  DealData,
} from "@/api/types";
import {
  Badge,
  Button,
  InfoList,
  PillRow,
  ScoreBar,
  SectionHeading,
  Surface,
} from "@/components/ui/primitives";

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

type BookingFeedback = {
  kind: "success" | "error" | "status";
  message: string;
};

type BookingMutationOutcome =
  | { result: DealApprovalResult; errorKind?: never; message?: never }
  | {
      result?: never;
      errorKind: "definite" | "ambiguous";
      message: string;
      conflictCode?: string;
      safeToRetry: boolean;
    };

export function DealReviewPage() {
  const { dealId = "deal-118400" } = useParams();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const watchId = searchParams.get("watchId") ?? undefined;
  const approvalTokenFromLink = searchParams.get("approvalToken") ?? "";
  const approvalTokenQueryKey = useMemo(
    () => queryKeys.approvalToken(dealId, approvalTokenFromLink),
    [approvalTokenFromLink, dealId],
  );
  const reviewSeed = useMemo(
    () => ((location.state as DealReviewLocationState | null)?.reviewSeed ?? null),
    [location.state],
  );
  const [logicalAttempt, setLogicalAttempt] = useState<StoredBookingAttempt | null>(() =>
    loadStoredBookingAttempt(dealId),
  );
  const [showApprovalForm, setShowApprovalForm] = useState(Boolean(logicalAttempt));
  const [paymentMethodId, setPaymentMethodId] = useState(
    logicalAttempt?.paymentMethodId ?? "",
  );
  const [totpCode, setTotpCode] = useState("");
  const [masterKeyPassphrase, setMasterKeyPassphrase] = useState("");
  const [approvalNotice, setApprovalNotice] = useState<string | null>(null);
  const [bookingFeedback, setBookingFeedback] = useState<BookingFeedback | null>(null);
  const [bookingAttemptPending, setBookingAttemptPending] = useState(false);
  const [attemptAllowsRetry, setAttemptAllowsRetry] = useState(false);
  const [attemptReconciliationPending, setAttemptReconciliationPending] = useState(
    Boolean(logicalAttempt),
  );
  const bookingFeedbackRef = useRef<HTMLDivElement>(null);
  const navigationAlertRef = useRef<HTMLDivElement>(null);
  const bookingRequestRef = useRef<BookDealRequest | null>(null);
  const bookingAttemptPendingRef = useRef(false);
  const idempotencyKeyRef = useRef<string | null>(
    logicalAttempt?.idempotencyKey ?? null,
  );
  const mintedApprovalTokenRef = useRef<string | null>(null);
  const consumedApprovalTokenRef = useRef<string | null>(null);
  const reconciledAttemptKeyRef = useRef<string | null>(null);
  const allowInternalNavigationRef = useRef(false);
  const mountedRef = useRef(true);

  const { data, error } = useQuery({
    queryKey: queryKeys.deal(dealId, watchId),
    queryFn: () => travelWatchApi.getDealReview(dealId, { watchId, seed: reviewSeed }),
  });
  const { data: profileWorkspace, error: profileError } = useQuery({
    queryKey: queryKeys.profile,
    queryFn: travelWatchApi.getProfileWorkspace,
  });
  const approvalTokenVerification = useQuery({
    queryKey: approvalTokenQueryKey,
    queryFn: () => travelWatchApi.verifyApprovalToken({ dealId, token: approvalTokenFromLink }),
    enabled: approvalTokenFromLink.length > 0,
  });

  const bookingMutation = useMutation<BookingMutationOutcome, never, void>({
    mutationFn: async () => {
      const payload = bookingRequestRef.current;
      if (!payload) {
        return {
          errorKind: "definite",
          message: "Secure booking details expired. Re-enter them and try again.",
          safeToRetry: true,
        };
      }
      try {
        return { result: await travelWatchApi.bookDeal(payload) };
      } catch (error) {
        const errorKind = bookingErrorKind(error);
        const conflict = getBookingConflictDetail(error);
        return {
          errorKind,
          message: getApiErrorMessage(error, "Unable to complete this booking."),
          conflictCode: conflict?.code,
          safeToRetry: conflict?.safeToRetry ?? errorKind === "definite",
        };
      }
    },
    retry: false,
  });
  const resetBookingMutation = bookingMutation.reset;
  const resetBookingMutationRef = useRef(resetBookingMutation);
  resetBookingMutationRef.current = resetBookingMutation;

  const rejectMutation = useMutation({
    mutationFn: (reason: string) => {
      if (bookingAttemptPendingRef.current || idempotencyKeyRef.current) {
        throw new Error("Resolve the active booking attempt before rejecting this deal.");
      }
      return travelWatchApi.rejectDeal({ dealId, reason });
    },
    onSuccess: async (result) => {
      setApprovalNotice(result.detail);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.dealVariants(dealId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }),
      ]);
    },
  });

  const persistLogicalAttempt = useCallback((attempt: StoredBookingAttempt) => {
    saveStoredBookingAttempt(attempt);
    setLogicalAttempt(attempt);
    setPaymentMethodId(attempt.paymentMethodId);
    idempotencyKeyRef.current = attempt.idempotencyKey;
  }, []);

  const clearLogicalAttempt = useCallback(() => {
    clearStoredBookingAttempt(dealId);
    setLogicalAttempt(null);
    setAttemptAllowsRetry(false);
    setAttemptReconciliationPending(false);
    idempotencyKeyRef.current = null;
    mintedApprovalTokenRef.current = null;
    reconciledAttemptKeyRef.current = null;
  }, [dealId]);

  const completeBookingSuccess = useCallback(
    async (result: DealApprovalResult) => {
      const bookingDetails = [
        result.confirmationNote,
        result.provider ? `Provider: ${result.provider}.` : "",
        result.amount ? `Amount: ${result.amount}.` : "",
        result.bookingStatus
          ? `Status: ${result.bookingStatus.replace(/_/g, " ")}.`
          : "",
      ].filter(Boolean);
      clearLogicalAttempt();

      if (approvalTokenFromLink) {
        await queryClient.cancelQueries({ queryKey: approvalTokenQueryKey, exact: true });
        consumedApprovalTokenRef.current = approvalTokenFromLink;
        const nextSearchParams = new URLSearchParams(searchParams);
        nextSearchParams.delete("approvalToken");
      allowInternalNavigationRef.current = true;
        setSearchParams(nextSearchParams, { replace: true });
        await Promise.resolve();
      allowInternalNavigationRef.current = false;
        queryClient.removeQueries({ queryKey: approvalTokenQueryKey, exact: true });
      }

      await Promise.allSettled([
        queryClient.invalidateQueries({ queryKey: queryKeys.dealVariants(dealId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }),
        queryClient.invalidateQueries({ queryKey: queryKeys.bookings }),
        queryClient.invalidateQueries({ queryKey: queryKeys.profile }),
      ]);
      if (mountedRef.current) {
        setBookingFeedback({ kind: "success", message: bookingDetails.join(" ") });
        setShowApprovalForm(false);
        setPaymentMethodId("");
      }
    },
    [
      approvalTokenFromLink,
      approvalTokenQueryKey,
      clearLogicalAttempt,
      dealId,
      queryClient,
      searchParams,
      setSearchParams,
    ],
  );

  const applyAttemptReconciliation = useCallback(
    async (
      storedAttempt: StoredBookingAttempt,
      result: BookingAttemptReconciliation,
    ) => {
      if (
        result.dealId !== storedAttempt.dealId ||
        result.paymentMethodId !== storedAttempt.paymentMethodId
      ) {
        const conflictAttempt: StoredBookingAttempt = {
          ...storedAttempt,
          paymentMethodId:
            result.dealId === storedAttempt.dealId
              ? result.paymentMethodId
              : storedAttempt.paymentMethodId,
          state: "manual_recovery",
          code: "idempotency_conflict",
          message:
            "Stored booking details did not match the server record. Manual recovery is required.",
        };
        persistLogicalAttempt(conflictAttempt);
        setAttemptAllowsRetry(false);
        setBookingFeedback({ kind: "status", message: conflictAttempt.message ?? "" });
        return;
      }
      if (result.booking) {
        await completeBookingSuccess(result.booking);
        return;
      }
      if (result.safeToRetry) {
        clearLogicalAttempt();
        setBookingFeedback({ kind: "error", message: result.message });
        setShowApprovalForm(true);
        return;
      }

      const unresolvedAttempt: StoredBookingAttempt = {
        ...storedAttempt,
        state: "manual_recovery",
        code: result.code,
        message: result.message,
      };
      persistLogicalAttempt(unresolvedAttempt);
      setAttemptAllowsRetry(false);
      setShowApprovalForm(true);
      setBookingFeedback({ kind: "status", message: result.message });
    },
    [clearLogicalAttempt, completeBookingSuccess, persistLogicalAttempt],
  );

  const reconcileLogicalAttempt = useCallback(
    async (storedAttempt: StoredBookingAttempt) => {
      setAttemptReconciliationPending(true);
      setAttemptAllowsRetry(false);
      setBookingFeedback({
        kind: "status",
        message: "Checking the saved booking attempt before any new action.",
      });
      try {
        const result = await travelWatchApi.reconcileBookingAttempt(
          storedAttempt.idempotencyKey,
        );
        if (mountedRef.current) {
          await applyAttemptReconciliation(storedAttempt, result);
        }
      } catch (reconciliationError) {
        if (!mountedRef.current) {
          return;
        }
        if (reconciliationError instanceof ApiError && reconciliationError.status === 404) {
          const retryableAttempt: StoredBookingAttempt = {
            ...storedAttempt,
            state: "reconciling",
            code: "not_found",
            message:
              "No server booking record was found. Retry this same booking attempt.",
          };
          persistLogicalAttempt(retryableAttempt);
          setAttemptAllowsRetry(true);
          setShowApprovalForm(true);
          setBookingFeedback({ kind: "error", message: retryableAttempt.message ?? "" });
        } else {
          const pendingAttempt: StoredBookingAttempt = {
            ...storedAttempt,
            state: "reconciling",
            code: "reconciliation_unavailable",
            message:
              "Booking recovery could not be checked. Do not start another booking attempt.",
          };
          persistLogicalAttempt(pendingAttempt);
          setAttemptAllowsRetry(false);
          setBookingFeedback({ kind: "status", message: pendingAttempt.message ?? "" });
        }
      } finally {
        if (mountedRef.current) {
          setAttemptReconciliationPending(false);
        }
      }
    },
    [applyAttemptReconciliation, persistLogicalAttempt],
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      bookingRequestRef.current = null;
      bookingAttemptPendingRef.current = false;
      idempotencyKeyRef.current = null;
      mintedApprovalTokenRef.current = null;
      consumedApprovalTokenRef.current = null;
      resetBookingMutationRef.current();
    };
  }, []);

  useEffect(() => {
    bookingFeedbackRef.current?.focus();
  }, [bookingFeedback]);

  useEffect(() => {
    const consumedToken = consumedApprovalTokenRef.current;
    if (!approvalTokenFromLink && consumedToken) {
      queryClient.removeQueries({
        queryKey: queryKeys.approvalToken(dealId, consumedToken),
        exact: true,
      });
      consumedApprovalTokenRef.current = null;
    }
  }, [approvalTokenFromLink, dealId, queryClient]);

  useEffect(() => {
    const storedAttempt = loadStoredBookingAttempt(dealId);
    if (!storedAttempt) {
      setLogicalAttempt(null);
      setAttemptAllowsRetry(false);
      setAttemptReconciliationPending(false);
      setPaymentMethodId("");
      idempotencyKeyRef.current = null;
      reconciledAttemptKeyRef.current = null;
      return;
    }
    persistLogicalAttempt(storedAttempt);
    setShowApprovalForm(true);
    if (
      bookingAttemptPendingRef.current ||
      reconciledAttemptKeyRef.current === storedAttempt.idempotencyKey
    ) {
      return;
    }
    reconciledAttemptKeyRef.current = storedAttempt.idempotencyKey;
    void reconcileLogicalAttempt(storedAttempt);
  }, [dealId, persistLogicalAttempt, reconcileLogicalAttempt]);

  const isBookingPending = bookingAttemptPending || bookingMutation.isPending;
  const hasUnresolvedAttempt = logicalAttempt !== null;
  const navigationLocked = isBookingPending || hasUnresolvedAttempt;
  const navigationBlocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      navigationLocked &&
      !allowInternalNavigationRef.current &&
      (currentLocation.pathname !== nextLocation.pathname ||
        currentLocation.search !== nextLocation.search),
  );

  useBeforeUnload(
    useCallback(
      (event) => {
        if (navigationLocked) {
          event.preventDefault();
          event.returnValue = "";
        }
      },
      [navigationLocked],
    ),
  );

  useEffect(() => {
    if (navigationBlocker.state === "blocked") {
      navigationAlertRef.current?.focus();
    }
  }, [navigationBlocker.state]);

  const clearSensitiveFields = useCallback(() => {
    setTotpCode("");
    setMasterKeyPassphrase("");
  }, []);

  if (!data) {
    return (
      <div className="stack">
        <Surface>
          {error ? getApiErrorMessage(error, "Unable to load the deal review.") : "Loading deal review..."}
        </Surface>
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
  const readinessBlockersForGuidance = readinessBlockers;
  const readinessResolutionLinks = (deal.readiness?.resolutions ?? []).filter(
    (resolution) =>
      !hasNoPaymentMethods || resolution.code !== "payment_method_required",
  );
  const linkedApprovalUnavailable =
    approvalTokenFromLink.length > 0 &&
    (approvalTokenVerification.isFetching ||
      approvalTokenVerification.isError ||
      approvalTokenVerification.data?.valid !== true);
  const attemptBlocksBooking =
    attemptReconciliationPending || (hasUnresolvedAttempt && !attemptAllowsRetry);
  const effectivePaymentMethodId =
    logicalAttempt?.paymentMethodId ?? paymentMethodId;
  const bookingCanSubmit =
    data.approvalAvailable &&
    bookNowAction?.enabled !== false &&
    !bookingLocked &&
    !hasReadinessBlockers &&
    effectivePaymentMethodId.length > 0 &&
    /^\d{6}$/.test(totpCode) &&
    !isBookingPending &&
    !attemptBlocksBooking &&
    !linkedApprovalUnavailable;

  const submitBooking = async () => {
    if (!bookingCanSubmit || bookingAttemptPendingRef.current) {
      return;
    }

    bookingAttemptPendingRef.current = true;
    setBookingAttemptPending(true);
    setBookingFeedback(null);
    setAttemptAllowsRetry(false);
    const storedAttempt: StoredBookingAttempt = logicalAttempt ?? {
      version: 1,
      dealId,
      idempotencyKey: idempotencyKeyRef.current ?? crypto.randomUUID(),
      paymentMethodId: effectivePaymentMethodId,
      state: "starting",
    };
    persistLogicalAttempt(storedAttempt);
    const idempotencyKey = storedAttempt.idempotencyKey;

    try {
      let approvalToken = approvalTokenFromLink;
      if (!approvalToken) {
        if (!mintedApprovalTokenRef.current) {
          const approval = await travelWatchApi.createApprovalToken(dealId);
          if (!mountedRef.current) {
            return;
          }
          if (!approval.token) {
            throw new Error("Unable to create a secure approval token for this booking.");
          }
          mintedApprovalTokenRef.current = approval.token;
        }
        approvalToken = mintedApprovalTokenRef.current ?? "";
      }
      if (!approvalToken) {
        throw new Error("Unable to create a secure approval token for this booking.");
      }

      bookingRequestRef.current = {
        dealId,
        approvalToken,
        paymentMethodId: storedAttempt.paymentMethodId,
        totpCode,
        masterKeyPassphrase,
        idempotencyKey,
      };
      persistLogicalAttempt({ ...storedAttempt, state: "submitted" });
      const outcome = await bookingMutation.mutateAsync();
      bookingRequestRef.current = null;
      if (mountedRef.current) {
        clearSensitiveFields();
        resetBookingMutation();
      }
      if (!mountedRef.current) {
        return;
      }
      if (outcome.result) {
        await completeBookingSuccess(outcome.result);
        return;
      }

      if (outcome.errorKind === "ambiguous") {
        const reconciliationAttempt: StoredBookingAttempt = {
          ...storedAttempt,
          state: "reconciling",
          ...(outcome.conflictCode ? { code: outcome.conflictCode } : {}),
          message: outcome.message,
        };
        persistLogicalAttempt(reconciliationAttempt);
        reconciledAttemptKeyRef.current = idempotencyKey;
        await reconcileLogicalAttempt(reconciliationAttempt);
        return;
      }

      if (outcome.safeToRetry) {
        clearLogicalAttempt();
        setBookingFeedback({
          kind: "error",
          message: outcome.message,
        });
        return;
      }

      const unresolvedAttempt: StoredBookingAttempt = {
        ...storedAttempt,
        state: "manual_recovery",
        ...(outcome.conflictCode ? { code: outcome.conflictCode } : {}),
        message: outcome.message,
      };
      persistLogicalAttempt(unresolvedAttempt);
      setBookingFeedback({ kind: "status", message: outcome.message });
    } catch (submissionError) {
      clearLogicalAttempt();
      if (mountedRef.current) {
        setBookingFeedback({
          kind: "error",
          message: getApiErrorMessage(submissionError, "Unable to start this secure booking."),
        });
      }
    } finally {
      bookingRequestRef.current = null;
      bookingAttemptPendingRef.current = false;
      if (mountedRef.current) {
        clearSensitiveFields();
        setBookingAttemptPending(false);
        resetBookingMutation();
      }
    }
  };

  const closeSecureBookingForm = () => {
    if (bookingAttemptPendingRef.current || isBookingPending) {
      return;
    }
    const hasUnresolvedAttempt = Boolean(idempotencyKeyRef.current);
    setShowApprovalForm(false);
    if (!hasUnresolvedAttempt) {
      setPaymentMethodId("");
      mintedApprovalTokenRef.current = null;
    }
    clearSensitiveFields();
    bookingRequestRef.current = null;
    resetBookingMutation();
  };

  return (
    <div className="stack">
      {navigationBlocker.state === "blocked" ? (
        <div
          ref={navigationAlertRef}
          className="notice notice-alert"
          role="alert"
          tabIndex={-1}
        >
          <p className="item-title">Booking recovery is still pending</p>
          <p className="item-copy">
            Stay on this page while the booking is processing, or leave only after the active
            request settles. Saved recovery details never include your security codes.
          </p>
          <div className="button-row">
            <Button type="button" onClick={() => navigationBlocker.reset?.()}>
              Stay on this page
            </Button>
            {!isBookingPending ? (
              <Button
                type="button"
                variant="secondary"
                onClick={() => navigationBlocker.proceed?.()}
              >
                Leave and keep recovery
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

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
        {error ? (
          <div className="notice notice-alert" role="alert">
            {getApiErrorMessage(error, "Unable to refresh this deal.")}
          </div>
        ) : null}
        {approvalNotice ? <div className="notice notice-value">{approvalNotice}</div> : null}
        {approvalTokenFromLink ? (
          approvalTokenVerification.isError ? (
            <div className="notice notice-alert" role="alert">
              {getApiErrorMessage(
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
        {rejectMutation.isError ? (
          <div className="notice notice-alert" role="alert">
            {getApiErrorMessage(rejectMutation.error, "Unable to record rejection feedback for this deal.")}
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

        {bookingFeedback ? (
          <div
            ref={bookingFeedbackRef}
            className={
              bookingFeedback.kind === "error"
                ? "notice notice-alert"
                : "notice notice-value"
            }
            role={bookingFeedback.kind === "error" ? "alert" : "status"}
            tabIndex={-1}
          >
            {bookingFeedback.message}
          </div>
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
                    onChange={(event) => {
                      if (!bookingAttemptPendingRef.current && !idempotencyKeyRef.current) {
                        setPaymentMethodId(event.target.value);
                      }
                    }}
                    disabled={isBookingPending || hasUnresolvedAttempt}
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
                  disabled={isBookingPending}
                />
              </div>

              <div className="field-stack">
                <label htmlFor="booking-master-key">Master-key passphrase (optional)</label>
                <input
                  id="booking-master-key"
                  className="text-input"
                  type="password"
                  autoComplete="new-password"
                  spellCheck={false}
                  value={masterKeyPassphrase}
                  onChange={(event) => setMasterKeyPassphrase(event.target.value)}
                  placeholder="Leave blank when not required"
                  disabled={isBookingPending}
                />
                <p className="helper-copy">
                  Your backend security mode determines whether this passphrase is required.
                </p>
              </div>
            </div>

            {profileError ? (
              <div className="notice notice-alert" role="alert">
                {getApiErrorMessage(profileError, "Unable to load saved payment methods.")}
              </div>
            ) : null}

            {!data.approvalAvailable ? (
              <div className="notice notice-alert" role="alert">
                Booking approval is unavailable for this deal right now.
              </div>
            ) : null}

            <div className="button-row">
              <Button
                type="button"
                onClick={() => void submitBooking()}
                disabled={!bookingCanSubmit}
              >
                {isBookingPending ? "Booking..." : "Book now"}
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={closeSecureBookingForm}
                disabled={isBookingPending}
              >
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
              disabled={
                rejectMutation.isPending ||
                isBookingPending ||
                hasUnresolvedAttempt ||
                dealIntentLocked ||
                ignoreAction?.enabled === false
              }
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
              <Button key={resolution.code} variant="secondary" to={resolution.path}>
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
            if (isBookingPending) {
              return;
            }
            if (showApprovalForm) {
              closeSecureBookingForm();
              return;
            }
            resetBookingMutation();
            setApprovalNotice(null);
            if (!idempotencyKeyRef.current) {
              setBookingFeedback(null);
            }
            setShowApprovalForm(true);
          }}
          disabled={
            isBookingPending ||
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
          disabled={
            rejectMutation.isPending ||
            isBookingPending ||
            hasUnresolvedAttempt ||
            dealIntentLocked ||
            ignoreAction?.enabled === false
          }
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
