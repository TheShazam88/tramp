import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";

import { apiClient } from "@/api/client";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import { TrampBrand } from "@/components/brand/TrampBrand";
import { TrampStampBadge } from "@/components/rewards/TrampStampButterfly";
import { Button } from "@/components/ui/primitives";

const navigation = [
  { to: "/watches", label: "Watches" },
  { to: "/bookings", label: "Bookings" },
  { to: "/profile", label: "Profile" },
  { to: "/admin/integrations", label: "Admin" },
];

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const isOnboarding =
    location.pathname.startsWith("/onboarding") || location.pathname.startsWith("/setup/2fa");
  const { data, isLoading } = useQuery({
    queryKey: queryKeys.profile,
    queryFn: travelWatchApi.getProfileWorkspace,
  });
  const { data: systemStatus } = useQuery({
    queryKey: queryKeys.systemStatus,
    queryFn: travelWatchApi.getSystemStatus,
    enabled: apiClient.mode === "live",
  });
  const logoutMutation = useMutation({
    mutationFn: travelWatchApi.logout,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.profile });
      navigate("/login", { replace: true });
    },
  });

  if (isLoading) {
    return (
      <div className="app-shell">
        <main className="page-frame">
          <div className="surface-card">Loading your workspace...</div>
        </main>
      </div>
    );
  }

  if (!data?.currentUser) {
    return <Navigate to="/login" replace />;
  }

  const needsTotpSetup = !data.currentUser.totpEnabled;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <div className="topbar-brand-copy">
            <p className="eyebrow">Autonomous travel booking</p>
            <TrampBrand compact />
            <p className="brand-tagline">
              {isOnboarding ? "Security and onboarding" : "Operator console"}
            </p>
          </div>
        </div>
        <div className="button-row topbar-actions">
          <TrampStampBadge balance={data.trampStampBalance} />
          {needsTotpSetup ? (
            <Button variant="secondary" to="/setup/2fa">
              Enable 2FA
            </Button>
          ) : null}
          <Link className="button button-secondary" to="/watches/new">
            New watch
          </Link>
          <Button
            variant="ghost"
            type="button"
            onClick={() => logoutMutation.mutate()}
            disabled={logoutMutation.isPending}
          >
            {logoutMutation.isPending ? "Signing out..." : "Sign out"}
          </Button>
        </div>
      </header>

      <main className="page-frame">
        {needsTotpSetup && !isOnboarding ? (
          <div className="notice notice-alert">
            Two-factor authentication is not enabled yet for this account. Complete the onboarding step before using booking approvals.
          </div>
        ) : null}
        {apiClient.mode === "live" ? (
          systemStatus?.liveInventoryAvailable ? (
            <div className="notice notice-value">Live provider inventory is active.</div>
          ) : (
            <div className="notice notice-alert">
              No flight or hotel connection is live right now.{" "}
              {systemStatus?.mockDataEnabled
                ? "The product may show mock/simulated inventory until a real provider is connected or the admin disables mock data."
                : "Mock data is disabled, so screens without real provider data will stay empty until live connections are implemented."}
            </div>
          )
        ) : null}
        <Outlet />
      </main>

      <nav className="bottom-nav" aria-label="Primary">
        {navigation.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              isActive ? "bottom-link bottom-link-active" : "bottom-link"
            }
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
