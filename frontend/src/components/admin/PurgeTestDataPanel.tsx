import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ApiError } from "@/api/client";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import type { TestDataPurgeResult } from "@/api/types";
import { Button, SectionHeading, Surface } from "@/components/ui/primitives";

const confirmationPhrase = "PURGE TEST DATA";
const preservedDataExplanation =
  "Users, traveler profiles, preferences, payment methods, loyalty accounts, credential profiles, and live provider activity are preserved.";

function errorDetail(error: unknown) {
  if (!(error instanceof ApiError) || !error.payload || typeof error.payload !== "object") {
    return "";
  }
  const detail = (error.payload as { detail?: unknown }).detail;
  return typeof detail === "string" ? detail : "";
}

function isStalePreviewError(error: unknown) {
  const detail = errorDetail(error).toLowerCase();
  return (
    detail.includes("preview changed") ||
    detail.includes("stale") ||
    detail.includes("plan_digest")
  );
}

function safeErrorMessage(error: unknown, fallback: string) {
  if (
    error instanceof TypeError ||
    (error instanceof Error && /network|failed to fetch/i.test(error.message))
  ) {
    return "Unable to reach the backend. Check the connection and try again.";
  }

  const detail = errorDetail(error).toLowerCase();
  if (isStalePreviewError(error)) {
    return "The purge preview is stale. Request a new preview before trying again.";
  }
  if (detail.includes("confirmation")) {
    return "The backend rejected the confirmation phrase. Request a new preview and enter the phrase exactly.";
  }
  if (
    detail.includes("unknown cancellation") ||
    detail.includes("unknown provenance")
  ) {
    return "The backend blocked this purge because cancellation provenance is unknown. Review the preview before continuing.";
  }
  if (
    detail.includes("unreverted feedback") ||
    detail.includes("could not be safely reverted")
  ) {
    return "The backend blocked this purge because feedback could not be safely reverted. Review the preview before continuing.";
  }
  if (error instanceof ApiError && error.status === 403) {
    return "Administrator access is required to preview or purge test data.";
  }
  if (error instanceof ApiError && error.status === 401) {
    return "The administrator session expired. Sign in again before continuing.";
  }
  if (error instanceof ApiError && Array.isArray((error.payload as { detail?: unknown } | undefined)?.detail)) {
    return "The backend rejected the purge request. Request a new preview and enter the confirmation phrase exactly.";
  }
  return fallback;
}

function countLabel(key: string) {
  return key
    .split("_")
    .filter(Boolean)
    .map((part, index) =>
      index === 0 ? part[0].toUpperCase() + part.slice(1) : part,
    )
    .join(" ");
}

function PurgeSummary({
  result,
  label,
  heading,
}: {
  result: TestDataPurgeResult;
  label: string;
  heading: string;
}) {
  const counts = Object.entries(result.deletedCounts).sort(([left], [right]) =>
    left.localeCompare(right),
  );

  return (
    <section
      className="form-shell stack-tight"
      role="region"
      aria-label={label}
    >
      <h3>{heading}</h3>
      <dl className="key-value-list purge-count-list">
        <div>
          <dt>Dry run</dt>
          <dd>{result.dryRun ? "Yes" : "No"}</dd>
        </div>
        {counts.map(([key, count]) => (
          <div key={key}>
            <dt>{countLabel(key)}</dt>
            <dd>{count}</dd>
          </div>
        ))}
        <div>
          <dt>Watches reset</dt>
          <dd>{result.resetWatchCount}</dd>
        </div>
        <div>
          <dt>Unknown cancellation provenance</dt>
          <dd>{result.unknownCancellationCount}</dd>
        </div>
        <div>
          <dt>Unreverted feedback</dt>
          <dd>{result.unrevertedFeedbackCount}</dd>
        </div>
      </dl>
      <div>
        <p className="field-label">Warnings</p>
        {result.warnings.length > 0 ? (
          <ul className="info-list">
            {result.warnings.map((warning, index) => (
              <li key={`${index}-${warning}`}>{warning}</li>
            ))}
          </ul>
        ) : (
          <p className="helper-copy">No warnings returned.</p>
        )}
      </div>
      <div className="notice">
        <strong>Preserved data</strong>
        <p className="helper-copy">{preservedDataExplanation}</p>
      </div>
      <p className="helper-copy">
        Plan digest: <code className="inline-code">{result.planDigest}</code>
      </p>
    </section>
  );
}

export function PurgeTestDataPanel() {
  const queryClient = useQueryClient();
  const [preview, setPreview] = useState<TestDataPurgeResult | null>(null);
  const [executionResult, setExecutionResult] =
    useState<TestDataPurgeResult | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const phraseRef = useRef<HTMLInputElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const successRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (errorMessage) {
      errorRef.current?.focus();
    }
  }, [errorMessage]);

  useEffect(() => {
    if (executionResult) {
      successRef.current?.focus();
    }
  }, [executionResult]);

  const previewMutation = useMutation({
    mutationFn: () => travelWatchApi.previewTestDataPurge(),
    onMutate: () => {
      setErrorMessage("");
      setExecutionResult(null);
      setCopyStatus("");
    },
    onSuccess: (result) => {
      setPreview(result);
      setConfirmation("");
    },
    onError: (error) => {
      setPreview(null);
      setConfirmation("");
      setErrorMessage(
        safeErrorMessage(error, "Unable to preview the test data purge."),
      );
    },
  });

  const purgeMutation = useMutation({
    mutationFn: (payload: { confirmation: string; planDigest: string }) =>
      travelWatchApi.purgeTestData(payload),
    onMutate: () => {
      setErrorMessage("");
      setExecutionResult(null);
      setCopyStatus("");
    },
    onSuccess: async (result) => {
      setExecutionResult(result);
      setPreview(null);
      setConfirmation("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.integrations }),
        queryClient.invalidateQueries({ queryKey: queryKeys.systemStatus }),
        queryClient.invalidateQueries({ queryKey: queryKeys.dashboard }),
        queryClient.invalidateQueries({ queryKey: queryKeys.bookings }),
        queryClient.invalidateQueries({ queryKey: queryKeys.profile }),
        queryClient.invalidateQueries({ queryKey: ["deal"] }),
      ]);
    },
    onError: (error) => {
      if (isStalePreviewError(error)) {
        setPreview(null);
        setConfirmation("");
      }
      setErrorMessage(
        safeErrorMessage(error, "The backend rejected the test data purge."),
      );
    },
  });

  const hasRetainedEvidence = Boolean(
    preview &&
      (preview.unknownCancellationCount > 0 ||
        preview.unrevertedFeedbackCount > 0),
  );
  const pending = previewMutation.isPending || purgeMutation.isPending;
  const canPurge = Boolean(
    preview?.planDigest &&
      confirmation === confirmationPhrase &&
      !pending,
  );

  const copyPhrase = async () => {
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard unavailable");
      }
      await navigator.clipboard.writeText(confirmationPhrase);
      setCopyStatus("Confirmation phrase copied.");
    } catch {
      phraseRef.current?.focus();
      phraseRef.current?.select();
      setCopyStatus(
        "Clipboard access is unavailable. The phrase is selected for manual copy.",
      );
    }
  };

  return (
    <Surface className="purge-test-data-panel">
      <SectionHeading
        eyebrow="Destructive maintenance"
        title="Purge test data"
        description="Preview simulated activity before removing it. Live and profile data are preserved."
      />

      <div className="notice notice-alert">
        <strong>Permanent destructive action.</strong> Only activity classified as
        simulated is eligible. Always review the current preview before purging.
      </div>

      <div className="panel-actions">
        <Button
          type="button"
          variant="secondary"
          onClick={() => previewMutation.mutate()}
          disabled={pending}
        >
          {previewMutation.isPending ? "Loading preview..." : "Preview purge"}
        </Button>
      </div>

      {errorMessage ? (
        <div
          ref={errorRef}
          className="notice notice-alert"
          role="alert"
          aria-label="Purge error"
          tabIndex={-1}
        >
          {errorMessage}
        </div>
      ) : null}

      {executionResult ? (
        <>
          <div
            ref={successRef}
            className="notice notice-value"
            role="status"
            aria-label="Purge succeeded"
            tabIndex={-1}
          >
            Test data purge completed. The exact backend result appears below.
          </div>
          <PurgeSummary
            result={executionResult}
            label="Purge execution summary"
            heading="Execution summary"
          />
        </>
      ) : null}

      {preview ? (
        <>
          <PurgeSummary
            result={preview}
            label="Purge preview"
            heading="Purge preview"
          />

          {hasRetainedEvidence ? (
            <div
              className="notice"
              role="status"
              aria-label="Retained evidence notice"
            >
              <strong>Retained evidence will not be deleted.</strong> These records
              will remain after the purge. The backend will remove only activity it
              has classified as simulated.
            </div>
          ) : null}

          <div className="form-shell stack-tight">
            <h3>Confirm permanent purge</h3>
            <p className="helper-copy">
              Copy the required phrase, then type it into the separate confirmation
              field exactly as shown.
            </p>
            <div className="toolbar-row">
              <label className="field-stack purge-confirmation-phrase">
                <span>Required confirmation phrase</span>
                <input
                  ref={phraseRef}
                  className="text-input inline-code"
                  aria-label="Required purge confirmation phrase"
                  readOnly
                  value={confirmationPhrase}
                />
              </label>
              <Button type="button" variant="secondary" onClick={copyPhrase}>
                Copy phrase
              </Button>
            </div>
            {copyStatus ? (
              <div
                className="notice"
                role="status"
                aria-label="Copy status"
              >
                {copyStatus}
              </div>
            ) : null}
            <label className="field-stack">
              <span>Type the confirmation phrase</span>
              <input
                className="text-input"
                aria-label="Type the confirmation phrase"
                autoComplete="off"
                spellCheck={false}
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
              />
            </label>
            <div className="panel-actions">
              <Button
                type="button"
                className="button-destructive"
                aria-label="Purge test data permanently"
                onClick={() => {
                  if (!preview || !canPurge) {
                    return;
                  }
                  purgeMutation.mutate({
                    confirmation,
                    planDigest: preview.planDigest,
                  });
                }}
                disabled={!canPurge}
              >
                {purgeMutation.isPending
                  ? "Purging test data..."
                  : "Purge test data permanently"}
              </Button>
            </div>
          </div>
        </>
      ) : null}
    </Surface>
  );
}
