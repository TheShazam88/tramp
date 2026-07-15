import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ApiError, apiClient } from "@/api/client";
import { travelWatchApi } from "@/api/travelWatchApi";
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

function isAmbiguousExecutionOutcome(error: unknown) {
  return !(error instanceof ApiError) || error.status >= 500;
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
      <div role="group" aria-label="Purge counts">
        <dl
          className="key-value-list purge-count-list"
          aria-label="Purge count details"
        >
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
      </div>
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
  const liveApiMode = apiClient.mode === "live";
  const [preview, setPreview] = useState<TestDataPurgeResult | null>(null);
  const [executionResult, setExecutionResult] =
    useState<TestDataPurgeResult | null>(null);
  const [confirmation, setConfirmation] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [outcomeUnknown, setOutcomeUnknown] = useState(false);
  const phraseRef = useRef<HTMLInputElement>(null);
  const errorRef = useRef<HTMLDivElement>(null);
  const previewStatusRef = useRef<HTMLDivElement>(null);
  const successRef = useRef<HTMLDivElement>(null);
  const activationLockRef = useRef(false);
  const previewRequestRef = useRef<Promise<TestDataPurgeResult> | null>(null);
  const purgeRequestRef = useRef<Promise<TestDataPurgeResult> | null>(null);

  useEffect(() => {
    if (errorMessage) {
      errorRef.current?.focus();
    }
  }, [errorMessage]);

  useEffect(() => {
    if (preview) {
      previewStatusRef.current?.focus();
    }
  }, [preview]);

  useEffect(() => {
    if (executionResult) {
      successRef.current?.focus();
    }
  }, [executionResult]);

  const previewMutation = useMutation({
    mutationFn: async () => {
      if (previewRequestRef.current) {
        return previewRequestRef.current;
      }
      const request = travelWatchApi.previewTestDataPurge();
      previewRequestRef.current = request;
      try {
        return await request;
      } finally {
        if (previewRequestRef.current === request) {
          previewRequestRef.current = null;
        }
      }
    },
    onMutate: () => {
      setErrorMessage("");
      setOutcomeUnknown(false);
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
      setOutcomeUnknown(false);
      setErrorMessage(
        safeErrorMessage(error, "Unable to preview the test data purge."),
      );
    },
    onSettled: () => {
      activationLockRef.current = false;
    },
  });

  const purgeMutation = useMutation({
    mutationFn: async (payload: { confirmation: string; planDigest: string }) => {
      if (purgeRequestRef.current) {
        return purgeRequestRef.current;
      }
      const request = travelWatchApi.purgeTestData(payload);
      purgeRequestRef.current = request;
      try {
        return await request;
      } finally {
        if (purgeRequestRef.current === request) {
          purgeRequestRef.current = null;
        }
      }
    },
    onMutate: () => {
      setErrorMessage("");
      setOutcomeUnknown(false);
      setExecutionResult(null);
      setCopyStatus("");
    },
    onSuccess: async (result) => {
      setExecutionResult(result);
      setPreview(null);
      setConfirmation("");
      await queryClient.invalidateQueries({ refetchType: "all" });
    },
    onError: async (error) => {
      if (isAmbiguousExecutionOutcome(error)) {
        setPreview(null);
        setConfirmation("");
        setOutcomeUnknown(true);
        setErrorMessage(
          "TRAMP could not confirm whether the purge completed. The preview and confirmation were cleared, and cached data is being refreshed. Request a fresh preview before trying again.",
        );
        await queryClient.invalidateQueries({ refetchType: "all" });
        return;
      }
      if (isStalePreviewError(error)) {
        setPreview(null);
        setConfirmation("");
      }
      setOutcomeUnknown(false);
      setErrorMessage(
        safeErrorMessage(error, "The backend rejected the test data purge."),
      );
    },
    onSettled: () => {
      activationLockRef.current = false;
    },
  });

  const hasRetainedEvidence = Boolean(
    preview &&
      (preview.unknownCancellationCount > 0 ||
        preview.unrevertedFeedbackCount > 0),
  );
  const pending = previewMutation.isPending || purgeMutation.isPending;
  const canPurge = Boolean(
    liveApiMode &&
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

  const requestPreview = () => {
    if (activationLockRef.current || pending) {
      return;
    }
    activationLockRef.current = true;
    previewMutation.mutate();
  };

  const executePurge = () => {
    if (!preview || !canPurge || activationLockRef.current) {
      return;
    }
    activationLockRef.current = true;
    purgeMutation.mutate({
      confirmation,
      planDigest: preview.planDigest,
    });
  };

  return (
    <Surface
      className="purge-test-data-panel"
      role="region"
      aria-label="Purge test data controls"
    >
      <SectionHeading
        eyebrow="Destructive maintenance"
        title="Purge test data"
        description="Preview simulated activity before removing it. Live and profile data are preserved."
      />

      <div className="notice notice-alert">
        <strong>Permanent destructive action.</strong> Only activity classified as
        simulated is eligible. Always review the current preview before purging.
      </div>

      {!liveApiMode ? (
        <div className="notice" role="status" aria-label="Mock purge mode">
          <strong>Preview only in mock frontend mode.</strong> Destructive execution
          is disabled. Switch the frontend to live API mode to run a real purge.
        </div>
      ) : null}

      <div className="panel-actions">
        <Button
          type="button"
          variant="secondary"
          onClick={requestPreview}
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
          aria-label={outcomeUnknown ? "Purge outcome unknown" : "Purge error"}
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
          <div
            ref={previewStatusRef}
            className="notice notice-value"
            role="status"
            aria-label="Purge preview ready"
            aria-live="polite"
            tabIndex={-1}
          >
            Purge preview ready. Review every count and warning before continuing.
          </div>
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

          {liveApiMode ? (
            <div
              className="form-shell stack-tight"
              role="region"
              aria-label="Purge confirmation"
            >
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
                  onClick={executePurge}
                  disabled={!canPurge}
                >
                  {purgeMutation.isPending
                    ? "Purging test data..."
                    : "Purge test data permanently"}
                </Button>
              </div>
            </div>
          ) : null}
        </>
      ) : null}
    </Surface>
  );
}
