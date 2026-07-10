import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "@/api/client";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import { TrampBrand } from "@/components/brand/TrampBrand";
import { Button, SectionHeading, Surface } from "@/components/ui/primitives";

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

export function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    email: "",
    password: "",
    totpCode: "",
  });

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.profile,
    queryFn: travelWatchApi.getProfileWorkspace,
  });

  const loginMutation = useMutation({
    mutationFn: travelWatchApi.login,
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.profile });
      navigate(result.user.totpEnabled ? "/watches" : "/setup/2fa", { replace: true });
    },
  });

  if (isLoading) {
    return (
      <div className="app-shell">
        <main className="page-frame">
          <Surface>Checking your session...</Surface>
        </main>
      </div>
    );
  }

  if (data?.currentUser) {
    return <Navigate to={data.currentUser.totpEnabled ? "/watches" : "/setup/2fa"} replace />;
  }

  return (
    <div className="app-shell login-shell">
      <main className="page-frame login-frame">
        <div className="login-stage">
          <Surface className="page-hero login-hero">
            <p className="login-kicker">Luxury travel command</p>
            <TrampBrand as="h1" className="login-brand" />
            <SectionHeading
              eyebrow="Secure access"
              title="Sign in"
              description="Enter your credentials to access the TRAMP control room. On first login, TRAMP will guide you through a one-time QR-based 2FA setup."
            />
          </Surface>

          <Surface className="login-form-card">
            <form
              className="form-shell"
              onSubmit={(event) => {
                event.preventDefault();
                loginMutation.mutate({
                  email: form.email.trim(),
                  password: form.password,
                  totpCode: form.totpCode.trim() || undefined,
                });
              }}
            >
              <div className="form-grid">
                <div className="field-stack">
                  <label htmlFor="login-email">Email</label>
                  <input
                    id="login-email"
                    className="text-input"
                    type="email"
                    value={form.email}
                    onChange={(event) => setForm((current) => ({ ...current, email: event.target.value }))}
                    autoComplete="email"
                    placeholder="name@example.com"
                    disabled={loginMutation.isPending}
                  />
                </div>

                <div className="field-stack">
                  <label htmlFor="login-password">Password</label>
                  <input
                    id="login-password"
                    className="text-input"
                    type="password"
                    value={form.password}
                    onChange={(event) => setForm((current) => ({ ...current, password: event.target.value }))}
                    autoComplete="current-password"
                    placeholder="Enter your password"
                    disabled={loginMutation.isPending}
                  />
                </div>

                <div className="field-stack">
                  <label htmlFor="login-totp">TOTP code</label>
                  <input
                    id="login-totp"
                    className="text-input"
                    inputMode="numeric"
                    value={form.totpCode}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        totpCode: event.target.value.replace(/\D/g, "").slice(0, 6),
                      }))
                    }
                    placeholder="Enter after enrollment"
                    disabled={loginMutation.isPending}
                  />
                </div>
              </div>

              <p className="helper-copy">
                Your credentials are never shown on this screen. If 2FA is not enrolled yet, leave the TOTP field blank for your first successful sign-in.
              </p>

              {loginMutation.isError ? (
                <div className="notice notice-alert">
                  {getErrorMessage(loginMutation.error, "Sign-in failed.")}
                </div>
              ) : null}

              <div className="panel-actions">
                <Button type="submit" disabled={loginMutation.isPending}>
                  {loginMutation.isPending ? "Signing in..." : "Sign in"}
                </Button>
              </div>
            </form>
          </Surface>
        </div>
      </main>
    </div>
  );
}
