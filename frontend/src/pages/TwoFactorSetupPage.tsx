import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { QRCodeSVG } from "qrcode.react";

import { ApiError } from "@/api/client";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import { Badge, Button, SectionHeading, Surface } from "@/components/ui/primitives";
import type { TotpEnrollmentSession } from "@/api/types";

const TOTP_SETUP_SESSION_KEY = "tramp.pending-totp-setup.v1";

type SetupStage = "intro" | "scan" | "verify" | "done";

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

function readSetupSession() {
  if (typeof window === "undefined") {
    return null;
  }

  const raw = window.sessionStorage.getItem(TOTP_SETUP_SESSION_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as TotpEnrollmentSession;
  } catch {
    return null;
  }
}

function writeSetupSession(value: TotpEnrollmentSession | null) {
  if (typeof window === "undefined") {
    return;
  }

  if (value) {
    window.sessionStorage.setItem(TOTP_SETUP_SESSION_KEY, JSON.stringify(value));
    return;
  }

  window.sessionStorage.removeItem(TOTP_SETUP_SESSION_KEY);
}

function normalizeStage(value: string | undefined): SetupStage {
  if (value === "scan" || value === "verify" || value === "done") {
    return value;
  }
  return "intro";
}

export function TwoFactorSetupPage() {
  const { stage: stageParam } = useParams();
  const stage = normalizeStage(stageParam);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [pendingSetup, setPendingSetup] = useState<TotpEnrollmentSession | null>(() => readSetupSession());
  const [totpCode, setTotpCode] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.profile,
    queryFn: travelWatchApi.getProfileWorkspace,
  });

  const currentUser = data?.currentUser ?? null;

  const startTotpEnrollmentMutation = useMutation({
    mutationFn: travelWatchApi.startTotpEnrollment,
    onSuccess: (session) => {
      setPendingSetup(session);
      writeSetupSession(session);
    },
  });

  const completeTotpEnrollmentMutation = useMutation({
    mutationFn: (payload: { pendingToken: string; totpCode: string }) =>
      travelWatchApi.completeTotpEnrollment(payload),
    onSuccess: async () => {
      setPendingSetup(null);
      writeSetupSession(null);
      setTotpCode("");
      await queryClient.invalidateQueries({ queryKey: queryKeys.profile });
      navigate("/setup/2fa/done", { replace: true });
    },
  });

  useEffect(() => {
    if (!currentUser || currentUser.totpEnabled || stage !== "scan" || pendingSetup) {
      return;
    }
    if (startTotpEnrollmentMutation.isPending) {
      return;
    }
    startTotpEnrollmentMutation.mutate();
  }, [currentUser, pendingSetup, stage, startTotpEnrollmentMutation]);

  const steps = useMemo(
    () => [
      {
        id: "intro",
        label: "Start",
        active: stage === "intro",
        complete: stage !== "intro",
      },
      {
        id: "scan",
        label: "Scan QR",
        active: stage === "scan",
        complete: stage === "verify" || stage === "done" || Boolean(currentUser?.totpEnabled),
      },
      {
        id: "verify",
        label: "Verify",
        active: stage === "verify",
        complete: stage === "done" || Boolean(currentUser?.totpEnabled),
      },
      {
        id: "done",
        label: "Done",
        active: stage === "done",
        complete: stage === "done" || Boolean(currentUser?.totpEnabled),
      },
    ],
    [currentUser?.totpEnabled, stage],
  );

  if (isLoading) {
    return (
      <div className="app-shell auth-shell">
        <main className="page-frame auth-frame">
          <Surface>Loading 2FA setup...</Surface>
        </main>
      </div>
    );
  }

  if (!currentUser) {
    return <Navigate to="/login" replace />;
  }

  if (currentUser.totpEnabled && stage !== "done") {
    return <Navigate to="/setup/2fa/done" replace />;
  }

  if ((stage === "verify" || stage === "done") && !pendingSetup && !currentUser.totpEnabled) {
    return <Navigate to="/setup/2fa/scan" replace />;
  }

  return (
    <div className="app-shell auth-shell">
      <main className="page-frame auth-frame">
        <div className="stack">
          <Surface className="page-hero">
            <SectionHeading
              eyebrow="TRAMP Security"
              title="Set up two-factor authentication"
              description="This is a one-time setup. We’ll guide you through scanning a QR code and confirming the first code from your authenticator app."
              action={<Badge tone="value">{steps.filter((item) => item.complete).length} / {steps.length}</Badge>}
            />
            <div className="setup-stepper" aria-label="2FA setup progress">
              {steps.map((item) => (
                <div
                  key={item.id}
                  className={
                    item.active
                      ? "setup-step-card setup-step-card-active"
                      : item.complete
                        ? "setup-step-card setup-step-card-complete"
                        : "setup-step-card"
                  }
                >
                  <span>{item.label}</span>
                </div>
              ))}
            </div>
          </Surface>

          {stage === "intro" ? (
            <Surface className="setup-stage">
              <SectionHeading
                eyebrow="Step 1"
                title="Get ready"
                description="Use Duo Mobile, Google Authenticator, 1Password, Authy, or any standard TOTP app."
              />
              <div className="split-layout">
                <Surface className="inset-card">
                  <h3>What happens next</h3>
                  <ul className="info-list">
                    <li>We generate a one-time QR code for this account.</li>
                    <li>You scan it with your authenticator app.</li>
                    <li>You enter the first six-digit code to finish setup.</li>
                  </ul>
                </Surface>
                <Surface className="inset-card">
                  <h3>Account</h3>
                  <p className="item-copy">
                    Signed in as <strong>{currentUser.email}</strong>.
                  </p>
                  <p className="item-copy">
                    Booking approvals will require TOTP after this is enabled.
                  </p>
                </Surface>
              </div>
              <div className="button-row">
                <Button to="/setup/2fa/scan">Continue to QR setup</Button>
                <Button variant="ghost" to="/onboarding">
                  Back to onboarding
                </Button>
              </div>
            </Surface>
          ) : null}

          {stage === "scan" ? (
            <Surface className="setup-stage">
              <SectionHeading
                eyebrow="Step 2"
                title="Scan the QR code"
                description="Open your authenticator app and scan this code. If scanning is not available, use the manual setup key below."
              />

              {startTotpEnrollmentMutation.isError ? (
                <div className="notice notice-alert">
                  {getErrorMessage(startTotpEnrollmentMutation.error, "Unable to prepare the QR code.")}
                </div>
              ) : null}

              {!pendingSetup ? (
                <Surface className="inset-card">Preparing your secure setup code...</Surface>
              ) : (
                <div className="split-layout">
                  <Surface className="inset-card qr-panel">
                    <div className="qr-code-frame">
                      <QRCodeSVG value={pendingSetup.provisioningUri} size={220} includeMargin />
                    </div>
                    <p className="helper-copy">Scan this in your authenticator app.</p>
                    <div className="button-row">
                      <a className="button button-secondary" href={pendingSetup.provisioningUri}>
                        Open authenticator link
                      </a>
                    </div>
                  </Surface>

                  <Surface className="inset-card">
                    <h3>Manual setup</h3>
                    <p className="item-copy">If you prefer, enter this key manually in the app:</p>
                    <p className="inline-code">{pendingSetup.manualEntryKey}</p>
                    <p className="helper-copy">
                      Account label: <strong>{currentUser.email}</strong>
                    </p>
                    <p className="helper-copy">Issuer: <strong>TRAMP</strong></p>
                  </Surface>
                </div>
              )}

              <div className="button-row">
                <Button
                  to="/setup/2fa/verify"
                  disabled={!pendingSetup || startTotpEnrollmentMutation.isPending}
                >
                  I’ve scanned the code
                </Button>
                <Button
                  variant="ghost"
                  type="button"
                  onClick={() => {
                    setPendingSetup(null);
                    writeSetupSession(null);
                    startTotpEnrollmentMutation.reset();
                    startTotpEnrollmentMutation.mutate();
                  }}
                  disabled={startTotpEnrollmentMutation.isPending}
                >
                  Generate a new QR code
                </Button>
              </div>
            </Surface>
          ) : null}

          {stage === "verify" ? (
            <Surface className="setup-stage">
              <SectionHeading
                eyebrow="Step 3"
                title="Verify your first code"
                description="Enter the current six-digit code from your authenticator app to activate two-factor authentication."
              />
              <form
                className="form-shell"
                onSubmit={(event) => {
                  event.preventDefault();
                  if (!pendingSetup) {
                    return;
                  }
                  completeTotpEnrollmentMutation.mutate({
                    pendingToken: pendingSetup.pendingToken,
                    totpCode,
                  });
                }}
              >
                <div className="form-grid">
                  <div className="field-stack">
                    <label htmlFor="totp-verify-code">Six-digit code</label>
                    <input
                      id="totp-verify-code"
                      className="text-input"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      value={totpCode}
                      onChange={(event) => setTotpCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                      placeholder="123456"
                      disabled={completeTotpEnrollmentMutation.isPending}
                    />
                  </div>
                </div>

                {completeTotpEnrollmentMutation.isError ? (
                  <div className="notice notice-alert">
                    {getErrorMessage(completeTotpEnrollmentMutation.error, "That code could not be verified.")}
                  </div>
                ) : null}

                <div className="button-row">
                  <Button
                    type="submit"
                    disabled={completeTotpEnrollmentMutation.isPending || totpCode.length !== 6}
                  >
                    {completeTotpEnrollmentMutation.isPending ? "Verifying..." : "Enable 2FA"}
                  </Button>
                  <Button variant="ghost" to="/setup/2fa/scan">
                    Back to QR code
                  </Button>
                </div>
              </form>
            </Surface>
          ) : null}

          {stage === "done" ? (
            <Surface className="setup-stage">
              <SectionHeading
                eyebrow="Step 4"
                title="Two-factor authentication is on"
                description="Your account is now protected. You only have to do this setup once."
              />
              <div className="notice notice-value">
                <strong>{currentUser.email}</strong>
                <p className="item-copy">2FA is enabled and ready for booking approvals.</p>
              </div>
              <div className="button-row">
                <Button to="/watches">Go to watches</Button>
                <Button variant="secondary" to="/onboarding">
                  Finish onboarding
                </Button>
                <Button variant="ghost" to="/profile">
                  Open profile
                </Button>
              </div>
            </Surface>
          ) : null}

          <div className="auth-link-row">
            <Link className="helper-link" to="/onboarding">
              Return to onboarding
            </Link>
          </div>
        </div>
      </main>
    </div>
  );
}
