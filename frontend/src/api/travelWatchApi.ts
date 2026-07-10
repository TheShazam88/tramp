import { ApiError, apiClient } from "@/api/client";
import {
  bookingsData,
  dashboardData,
  dealData,
  editWatchDraft,
  integrationData,
  newWatchDraft,
} from "@/api/mockData";
import type {
  BookingSummary,
  BookingsViewData,
  CurrentUser,
  DashboardData,
  DealData,
  DealApprovalResult,
  DealIntentResult,
  DealViewData,
  IntegrationData,
  IntegrationFlag,
  IntegrationTestResult,
  PaymentMethodProfile,
  ProfileWorkspace,
  SignupStartSession,
  TotpEnrollmentSession,
  TravelerProfile,
  TripTemplateProfile,
  UserPreferencesProfile,
  WatchDraft,
  WatchSummary,
  WatchStatus,
} from "@/api/types";

const useMockData = apiClient.mode !== "live";
let runtimePolicyCache:
  | {
      fetchedAt: number;
      mockDataEnabled: boolean;
      liveInventoryAvailable: boolean;
      currentInventoryMode: "mock" | "live" | "empty";
    }
  | null = null;

async function withLatency<T>(payload: T) {
  await new Promise((resolve) => window.setTimeout(resolve, 120));
  return payload;
}

async function getRuntimePolicy() {
  if (useMockData) {
    return {
      mockDataEnabled: true,
      liveInventoryAvailable: false,
      currentInventoryMode: "mock" as const,
    };
  }

  const now = Date.now();
  if (runtimePolicyCache && now - runtimePolicyCache.fetchedAt < 15000) {
    return runtimePolicyCache;
  }

  const response = await apiClient.get<HealthResponseRaw>("/health");
  const policy = {
    mockDataEnabled: response.checks?.mock_data_enabled ?? true,
    liveInventoryAvailable: response.checks?.live_inventory_available ?? false,
    currentInventoryMode:
      response.checks?.inventory_mode === "live"
        ? ("live" as const)
        : response.checks?.inventory_mode === "empty"
          ? ("empty" as const)
          : ("mock" as const),
  };
  runtimePolicyCache = { ...policy, fetchedAt: now };
  return policy;
}

function clearRuntimePolicyCache() {
  runtimePolicyCache = null;
}

interface AuthResponseRaw {
  user: {
    id: string;
    email: string;
    role: string;
    onboarding_completed: boolean;
    default_notify_channel: string;
    telegram_chat_id: string | null;
    totp_enabled: boolean;
  };
}

interface SignupStartResponseRaw {
  pending_token: string;
  totp_secret: string;
  provisioning_uri: string;
  manual_entry_key: string;
}

interface ProfileSummaryRaw {
  settings: {
    id: string;
    email: string;
    role: string;
    onboarding_completed: boolean;
    default_notify_channel: string;
    telegram_chat_id: string | null;
    totp_enabled: boolean;
  };
  preferences: {
    home_airports: string[];
    default_cabin: string | null;
    default_luxury_vs_savings: number;
    preferred_alliances: string[];
    preferred_airlines: string[];
    avoided_airlines: string[];
    preferred_hotel_brands: string[];
    avoided_hotel_brands: string[];
    quiet_hours_start: string | null;
    quiet_hours_end: string | null;
    default_notify_channel: string;
    avoid_redeye: boolean;
    prefer_refundable: boolean;
    seat_auto_select: boolean;
    default_hotel_min_rating: number | null;
    default_max_layover_minutes: number | null;
    default_min_connection_minutes: number | null;
  };
  travelers: Array<{
    id: string;
    traveler_relationship: string;
    display_name: string;
    legal_first_name: string;
    legal_last_name: string;
    dob: string;
    nationality: string;
    residency_country: string | null;
    passport_number: string | null;
    passport_country: string | null;
    passport_expiry: string | null;
    known_traveler_number: string | null;
    redress_number: string | null;
    seat_pref: string;
    meal_pref: string | null;
    accessibility_needs: string | null;
    infant_on_lap: boolean;
    loyalty_program_code: string | null;
    loyalty_account_number: string | null;
    loyalty_alliance: string | null;
    loyalty_status_tier: string | null;
    preferred_earning_for_alliance: boolean;
    loyalty_programs?: Array<{
      program_type: string;
      program_code: string;
      account_number: string;
      alliance: string;
      status_tier: string | null;
      is_favorite: boolean;
    }>;
  }>;
  traveler_groups: Array<{
    id: string;
    name: string;
    traveler_ids: string[];
  }>;
  payment_methods: Array<{
    id: string;
    label: string;
    brand: string | null;
    last4: string | null;
    cardholder_name: string | null;
    exp_month: number | null;
    exp_year: number | null;
    provider_token: string | null;
    billing_address: {
      line1: string;
      city: string;
      postal_code: string;
      country: string;
    } | null;
  }>;
  trip_templates: Array<{
    id: string;
    name: string;
    watch_payload: Record<string, unknown>;
  }>;
  household_summary?: {
    traveler_count?: number;
    traveler_group_count?: number;
    payment_method_count?: number;
    template_count?: number;
    passport_gap_count?: number;
    has_self_traveler?: boolean;
    has_payment_method?: boolean;
    totp_enabled?: boolean;
    setup_warnings?: string[];
    readiness_label?: string;
  };
}

type TravelerRaw = ProfileSummaryRaw["travelers"][number];

interface WatchGroupRaw {
  id?: string;
  name?: string;
  traveler_ids?: string[];
  travelerIds?: string[];
}

interface WatchRaw {
  id?: string;
  status?: string;
  route?: string;
  dates?: string;
  travelers?: string;
  traveler_ids?: string[] | null;
  traveler_names?: string[] | null;
  travelers_label?: string;
  traveler_group_id?: string | null;
  traveler_group?: string | WatchGroupRaw | null;
  traveler_group_name?: string | null;
  cabin?: string;
  cabin_class?: string | null;
  framing?: string | null;
  best_now?: string | null;
  bestNow?: string | null;
  insight?: string | null;
  cadence?: string | null;
  refresh_interval?: string | null;
  origin_iatas?: string[] | null;
  destination_iatas?: string[] | null;
  destination_mode?: string | null;
  flexible_region?: string | null;
  flexible_theme?: string | null;
  depart_date_from?: string | null;
  depart_date_to?: string | null;
  return_date_from?: string | null;
  return_date_to?: string | null;
  trip_min_nights?: number | null;
  trip_max_nights?: number | null;
  max_stops?: number | null;
  max_layover_minutes?: number | null;
  min_connection_minutes?: number | null;
  preferred_airlines?: string[] | null;
  preferred_alliances?: string[] | null;
  avoid_redeye?: boolean;
  prefer_refundable?: boolean;
  flight_budget_max?: number | string | null;
  hotel_budget_per_night_max?: number | string | null;
  budget_currency?: string | null;
  luxury_vs_savings?: number | null;
  hotel_min_rating?: number | string | null;
  notify_channel?: string | null;
  refreshInterval?: string | null;
  want_car?: boolean;
  include_airbnb?: boolean;
  trip_mode?: string | null;
  ideal_price?: number | string | null;
  glide_start_days?: number | null;
  glide_end_days?: number | null;
  current_deal?: {
    id?: string;
    deal_id?: string;
    all_in_price?: number | string | null;
    home_currency?: string | null;
    framing?: string | null;
    summary?: string | null;
  } | null;
  latest_deal?: {
    id?: string;
    deal_id?: string;
    all_in_price?: number | string | null;
    home_currency?: string | null;
    framing?: string | null;
    summary?: string | null;
  } | null;
  deal_id?: string | null;
  dealId?: string | null;
  best_price?: number | string | null;
  summary?: string | null;
  note?: string | null;
  readiness?: {
    score?: number;
    label?: string;
    blockers?: string[];
    warnings?: string[];
  } | null;
  badges?: Array<{ label?: string; tone?: string }> | null;
  cta_actions?: Array<{
    key?: string;
    label?: string;
    tone?: string;
    enabled?: boolean;
    detail?: string | null;
  }> | null;
}

interface WatchDashboardRaw {
  highlights?: Array<{ label?: string; value?: string | number; note?: string }>;
  watches?: WatchRaw[];
  items?: WatchRaw[];
  data?: WatchRaw[];
}

interface SearchWatchNowResult {
  dealId?: string;
  queued?: boolean;
  fallback?: boolean;
  deal?: DealData;
}

interface WatchCurrentDealRaw {
  id?: string;
  kind?: string;
  framing?: string;
  total_price?: number | string | null;
  currency?: string | null;
  quality_index?: number | null;
  value_score?: number | null;
  price_percentile?: number | null;
  timing_advice?: string | null;
  summary_text?: string | null;
  status?: string | null;
  created_at?: string | null;
  readiness?: WatchRaw["readiness"];
  badges?: WatchRaw["badges"];
}

interface WatchResponseRaw extends WatchRaw {
  route?: string;
  cabin_label?: string;
  dates_label?: string;
  current_deal?: WatchCurrentDealRaw | null;
}

interface CoverageReportRaw {
  confidence?: string | null;
  searched_sources?: string[];
  gaps?: string[];
  notes?: string[];
}

interface ValidationWarningRaw {
  code?: string;
  severity?: string;
  message?: string;
  traveler_name?: string | null;
}

interface LoyaltyPlanEntryRaw {
  traveler_name?: string;
  program_code?: string;
  alliance?: string;
  note?: string;
}

interface SearchNowDealRaw {
  id?: string;
  kind?: string;
  source?: string;
  total_price?: number | string | null;
  currency?: string | null;
  quality_index?: number | null;
  value_score?: number | null;
  price_percentile?: number | null;
  timing_advice?: string | null;
  framing?: string | null;
  summary_text?: string | null;
  coverage_report?: CoverageReportRaw | null;
  validation_warnings?: ValidationWarningRaw[];
  loyalty_plan?: LoyaltyPlanEntryRaw[];
  status?: string | null;
  expires_at?: string | null;
  booking?: BookingRaw | null;
  cancellation?: CancellationRaw | null;
  payload?: Record<string, unknown> | null;
  readiness?: WatchRaw["readiness"];
  badges?: WatchRaw["badges"];
  cta_actions?: WatchRaw["cta_actions"];
}

interface SearchNowResponseRaw {
  observed_at?: string;
  observations_created?: number;
  deals_upserted?: number;
  coverage_report?: CoverageReportRaw | null;
  proposed_deals?: SearchNowDealRaw[];
}

interface BookingRaw {
  id?: string;
  deal_id?: string | null;
  watch_id?: string | null;
  provider?: string | null;
  provider_booking_ref?: string | null;
  provider_correlation_id?: string | null;
  status?: string | null;
  amount_charged?: number | string | null;
  currency?: string | null;
  booked_at?: string | null;
  error_text?: string | null;
  ticketing_state?: string | null;
  calendar_event_id?: string | null;
  calendar_detail?: string | null;
  title?: string | null;
  route?: string | null;
  when?: string | null;
  deal?: SearchNowDealRaw | null;
  cancellation?: CancellationRaw | null;
  notifications?: Array<{
    id?: string | null;
    channel?: string | null;
    transport?: string | null;
    status?: string | null;
    error_text?: string | null;
  }> | null;
  disruptions?: Array<{
    id?: string | null;
    type?: string | null;
    status?: string | null;
  }> | null;
}

interface CancellationRaw {
  id?: string;
  reason?: string | null;
  refund_expected?: number | string | null;
  refund_received?: number | string | null;
  currency?: string | null;
  status?: string | null;
  requested_at?: string | null;
  resolved_at?: string | null;
}

interface LiveDealResponseRaw extends SearchNowDealRaw {
  route?: string | null;
  cabin?: string | null;
  cabin_label?: string | null;
  context?: string | null;
  breakdown?: string | null;
  score?: number | null;
  details?: string[];
  warnings?: string[];
  coverage?: string[];
  watch_id?: string | null;
  watch?: WatchResponseRaw | null;
}

interface DealTimelineRaw {
  current_price?: number | string | null;
  currency?: string | null;
  target_price?: number | string | null;
  glide_limit?: number | string | null;
  trend_summary?: string | null;
  points?: Array<{
    observed_at?: string | null;
    price?: number | string | null;
    currency?: string | null;
    label?: string | null;
    source?: string | null;
    price_percentile?: number | null;
  }> | null;
}

interface ApprovalResponseRaw {
  deal_id?: string | null;
  booking_id?: string | null;
  status?: string | null;
  detail?: string | null;
  message?: string | null;
  booking?: BookingRaw | null;
  cancellation?: CancellationRaw | null;
  action_taken?: Record<string, unknown> | null;
}

interface AdminIntegrationRaw {
  key?: string | null;
  name?: string | null;
  provider?: string | null;
  label?: string | null;
  category?: string | null;
  provider_key?: string | null;
  supports_shared_profile?: boolean | null;
  compatible_profile_provider_keys?: string[] | null;
  environment?: string | null;
  status?: string | null;
  detail?: string | null;
  enabled?: boolean | null;
  masked_credentials?: string | null;
  maskedCredentials?: string | null;
  credentials_configured?: boolean | null;
  credentialsConfigured?: boolean | null;
  credential_state?: string | null;
  credentialState?: string | null;
  credential_source?: string | null;
  updated_at?: string | null;
  updated_by?: string | null;
  validation_help?: string | null;
  credential_profile_id?: string | null;
  credential_profile_label?: string | null;
  credentials_masked?: Record<string, unknown> | null;
  credential_fields?: Array<{
    key?: string | null;
    label?: string | null;
    placeholder?: string | null;
    help_text?: string | null;
    sensitive?: boolean | null;
  }> | null;
  feature_flag_definitions?: Array<{
    key?: string | null;
    label?: string | null;
    default_enabled?: boolean | null;
    description?: string | null;
  }> | null;
  feature_flags?: Record<string, boolean> | Array<{ label?: string; enabled?: boolean }> | string[] | null;
  featureFlags?: Record<string, boolean> | Array<{ label?: string; enabled?: boolean }> | string[] | null;
}

interface AdminIntegrationCategoryRaw {
  id?: string | null;
  title?: string | null;
  description?: string | null;
}

interface AdminCredentialProfileRaw {
  id?: string | null;
  provider_key?: string | null;
  label?: string | null;
  credentials_masked?: Record<string, unknown> | null;
  updated_at?: string | null;
  updated_by?: string | null;
  usage_integration_keys?: string[] | null;
}

interface AdminIntegrationsResponseRaw {
  categories?: AdminIntegrationCategoryRaw[] | null;
  providers?: AdminIntegrationRaw[];
  integrations?: AdminIntegrationRaw[];
  credential_profiles?: AdminCredentialProfileRaw[] | null;
  feature_flags?: Record<string, boolean> | Array<{ label?: string; enabled?: boolean }> | string[] | null;
  featureFlags?: Record<string, boolean> | Array<{ label?: string; enabled?: boolean }> | string[] | null;
  health_notes?: string[] | null;
  healthNotes?: string[] | null;
  runtime_settings?: {
    mock_data_enabled?: boolean;
    live_inventory_available?: boolean;
    current_inventory_mode?: string;
  } | null;
  runtimeSettings?: {
    mockDataEnabled?: boolean;
    liveInventoryAvailable?: boolean;
    currentInventoryMode?: string;
  } | null;
}

interface HealthResponseRaw {
  status: string;
  environment: string;
  app: string;
  checks?: {
    mock_data_enabled?: boolean;
    live_inventory_available?: boolean;
    inventory_mode?: string;
  };
}

interface AdminIntegrationTestRaw {
  status?: string | null;
  detail?: string | null;
  message?: string | null;
  healthy?: boolean | null;
  ok?: boolean | null;
  tested_at?: string | null;
  testedAt?: string | null;
}

function listToText(values: string[] | null | undefined) {
  return (values ?? []).join(", ");
}

function coerceString(value: unknown) {
  return typeof value === "string" ? value : "";
}

function asStringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function formatCompactDate(value?: string | null) {
  if (!value) {
    return "";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" }).format(parsed);
}

function formatDateRange(start?: string | null, end?: string | null) {
  const startLabel = formatCompactDate(start);
  const endLabel = formatCompactDate(end);

  if (startLabel && endLabel) {
    return startLabel === endLabel ? startLabel : `${startLabel} - ${endLabel}`;
  }

  return startLabel || endLabel || "";
}

function formatRouteFromWatch(raw: WatchRaw) {
  if (raw.route) {
    return raw.route;
  }

  const origins = asStringList(raw.origin_iatas).join(", ");
  if (raw.destination_mode === "flexible") {
    const flexibleTarget = [raw.flexible_theme, raw.flexible_region].filter(Boolean).join(" · ");
    return [origins || "Anywhere", flexibleTarget || "Flexible destination"].filter(Boolean).join(" -> ");
  }

  const destinations = asStringList(raw.destination_iatas).join(", ");
  return [origins || "Any origin", destinations || "Any destination"].join(" -> ");
}

function formatDatesFromWatch(raw: WatchRaw) {
  const outbound = formatDateRange(raw.depart_date_from, raw.depart_date_to);
  const inbound = formatDateRange(raw.return_date_from, raw.return_date_to);

  if (outbound && inbound) {
    return `${outbound} / ${inbound}`;
  }

  if (outbound) {
    return outbound;
  }

  if (raw.trip_min_nights || raw.trip_max_nights) {
    const minimum = raw.trip_min_nights ?? raw.trip_max_nights;
    const maximum = raw.trip_max_nights ?? raw.trip_min_nights;
    return minimum === maximum ? `${minimum} nights` : `${minimum}-${maximum} nights`;
  }

  return raw.dates ?? "Dates flexible";
}

function formatCabinLabel(cabin: string | null | undefined) {
  const source = (cabin ?? "").trim();
  if (!source) {
    return "Any cabin";
  }

  return source
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function formatRefreshLabel(interval: string | null | undefined) {
  switch (interval) {
    case "6h":
      return "6h refresh";
    case "hourly":
      return "Hourly refresh";
    case "daily":
      return "Daily refresh";
    default:
      return "Refresh on schedule";
  }
}

function formatFramingLabel(framing: string | null | undefined) {
  switch (framing) {
    case "max_luxury":
      return "Max luxury";
    case "cheapest_ok":
      return "Cheapest acceptable";
    case "best_value":
      return "Best value";
    default:
      return "Best value";
  }
}

function parseNumericValue(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === "string") {
    const cleaned = value.replace(/[^0-9.-]/g, "");
    if (!cleaned) {
      return null;
    }
    const parsed = Number(cleaned);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
}

function formatMoneyValue(value: unknown, currency = "JPY") {
  const numeric = parseNumericValue(value);
  if (numeric === null) {
    return typeof value === "string" ? value : "";
  }

  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency,
      maximumFractionDigits: 0,
    }).format(numeric);
  } catch {
    return `${currency} ${numeric.toLocaleString()}`;
  }
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return "";
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(parsed);
}

function titleizeStatus(value: string | null | undefined) {
  const source = (value ?? "").trim();
  if (!source) {
    return "";
  }

  return source
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}

function mapReadiness(
  readiness:
    | {
        score?: number;
        label?: string;
        blockers?: string[];
        warnings?: string[];
      }
    | null
    | undefined,
) {
  if (!readiness) {
    return undefined;
  }
  return {
    score: typeof readiness.score === "number" ? readiness.score : 0,
    label: coerceString(readiness.label) || "Needs setup",
    blockers: asStringList(readiness.blockers),
    warnings: asStringList(readiness.warnings),
  };
}

function mapBadges(value: Array<{ label?: string; tone?: string }> | null | undefined) {
  return (value ?? [])
    .map((badge) => ({
      label: coerceString(badge.label),
      tone: (["value", "luxury", "alert", "muted"].includes(coerceString(badge.tone))
        ? coerceString(badge.tone)
        : "muted") as "value" | "luxury" | "alert" | "muted",
    }))
    .filter((badge) => badge.label);
}

function mapCtaActions(
  value:
    | Array<{
        key?: string;
        label?: string;
        tone?: string;
        enabled?: boolean;
        detail?: string | null;
      }>
    | null
    | undefined,
) {
  return (value ?? [])
    .map((action) => ({
      key: coerceString(action.key),
      label: coerceString(action.label) || titleizeStatus(coerceString(action.key)),
      tone: (["primary", "secondary", "ghost"].includes(coerceString(action.tone))
        ? coerceString(action.tone)
        : "secondary") as "primary" | "secondary" | "ghost",
      enabled: action.enabled ?? true,
      detail: coerceString(action.detail) || undefined,
    }))
    .filter((action) => action.key);
}

function mapDealTimeline(raw: DealTimelineRaw | null | undefined, dealCurrency?: string) {
  if (!raw) {
    return undefined;
  }
  const currency = coerceString(raw.currency) || dealCurrency || "JPY";
  return {
    currentPrice: formatMoneyValue(raw.current_price, currency) || undefined,
    targetPrice: formatMoneyValue(raw.target_price, currency) || undefined,
    glideLimit: formatMoneyValue(raw.glide_limit, currency) || undefined,
    trendSummary: coerceString(raw.trend_summary) || "Waiting for more history.",
    points: (raw.points ?? []).map((point) => ({
      observedAt: formatDateTime(point.observed_at) || coerceString(point.observed_at),
      price: formatMoneyValue(point.price, coerceString(point.currency) || currency),
      rawPrice: parseNumericValue(point.price) ?? 0,
      label: coerceString(point.label) || "Observed price",
      source: coerceString(point.source),
      percentile: typeof point.price_percentile === "number" ? point.price_percentile : undefined,
    })),
  };
}

function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function normalizeIntegrationEnvironment(value: string | null | undefined) {
  const source = coerceString(value).toLowerCase();
  if (source === "sandbox") {
    return "test";
  }
  if (source === "production") {
    return "live";
  }
  if (source === "disabled") {
    return "off";
  }
  return source || "off";
}

function normalizeIntegrationState(value: string | null | undefined, enabled: boolean, configured: boolean) {
  const source = coerceString(value).toLowerCase();
  if (["connected", "healthy", "ok", "success", "passed"].includes(source)) {
    return "connected" as const;
  }
  if (["disabled", "off"].includes(source)) {
    return "disabled" as const;
  }
  if (["not_set", "missing_credentials", "missing", "unconfigured"].includes(source)) {
    return "not_set" as const;
  }
  if (!enabled) {
    return "disabled" as const;
  }
  if (!configured) {
    return "not_set" as const;
  }
  return "attention" as const;
}

function mapIntegrationFlags(
  value: Record<string, boolean> | Array<{ label?: string; enabled?: boolean }> | string[] | null | undefined,
): IntegrationFlag[] {
  if (!value) {
    return [];
  }

  if (Array.isArray(value)) {
    return value
      .map((entry) => {
        if (typeof entry === "string") {
          return { label: titleizeStatus(entry) || entry, enabled: true };
        }

        return {
          label: coerceString(entry.label),
          enabled: entry.enabled ?? false,
        };
      })
      .filter((entry) => entry.label);
  }

  return Object.entries(value).map(([label, enabled]) => ({
    label: titleizeStatus(label) || label,
    enabled,
  }));
}

function mapIntegrationProvider(raw: AdminIntegrationRaw, index: number): IntegrationData["providers"][number] {
  const name =
    coerceString(raw.name) || coerceString(raw.label) || coerceString(raw.provider) || coerceString(raw.key) || `Provider ${index + 1}`;
  const key = coerceString(raw.key) || slugify(name) || `provider-${index + 1}`;
  const maskedValue = coerceString(raw.masked_credentials) || coerceString(raw.maskedCredentials) || undefined;
  const maskedObject =
    raw.credentials_masked && typeof raw.credentials_masked === "object"
      ? (raw.credentials_masked as Record<string, unknown>)
      : {};
  const configured =
    raw.credentials_configured ??
    raw.credentialsConfigured ??
    (Boolean(maskedValue) ||
      Object.keys(maskedObject).length > 0 ||
      Boolean(raw.credential_profile_id) ||
      false);
  const credentialStateSource = coerceString(raw.credential_state) || coerceString(raw.credentialState);
  const enabled = raw.enabled ?? normalizeIntegrationEnvironment(raw.environment) !== "off";
  const status = normalizeIntegrationState(raw.status, enabled, configured);
  const detail =
    coerceString(raw.detail) ||
    (configured
      ? "Credentials are stored encrypted and only exposed in masked form."
      : "Credentials have not been saved for this integration yet.");

  return {
    key,
    name,
    category: coerceString(raw.category) || "general",
    providerKey: coerceString(raw.provider_key) || undefined,
    supportsSharedProfile: raw.supports_shared_profile ?? false,
    compatibleProfileProviderKeys: Array.isArray(raw.compatible_profile_provider_keys)
      ? raw.compatible_profile_provider_keys.filter((item): item is string => typeof item === "string")
      : [],
    environment: normalizeIntegrationEnvironment(raw.environment),
    status,
    detail,
    enabled,
    credentialSource: coerceString(raw.credential_source),
    updatedAt: coerceString(raw.updated_at) || undefined,
    updatedBy: coerceString(raw.updated_by) || undefined,
    validationHelp: coerceString(raw.validation_help) || undefined,
    credentialProfileId: coerceString(raw.credential_profile_id) || undefined,
    credentialProfileLabel: coerceString(raw.credential_profile_label) || undefined,
    credentialState: {
      configured,
      label:
        titleizeStatus(credentialStateSource) ||
        (configured ? "Configured" : "Not set"),
      maskedValue,
    },
    credentialFields: Array.isArray(raw.credential_fields)
      ? raw.credential_fields
          .map((field) => ({
            key: coerceString(field.key),
            label: coerceString(field.label) || coerceString(field.key),
            placeholder: coerceString(field.placeholder) || undefined,
            helpText: coerceString(field.help_text) || undefined,
            sensitive: field.sensitive ?? true,
          }))
          .filter((field) => field.key)
      : [],
    credentialsMasked: maskedObject,
    featureFlags: mapIntegrationFlags(raw.feature_flags ?? raw.featureFlags),
    featureFlagDefinitions: Array.isArray(raw.feature_flag_definitions)
      ? raw.feature_flag_definitions
          .map((definition) => ({
            key: coerceString(definition.key),
            label: coerceString(definition.label) || coerceString(definition.key),
            defaultEnabled: definition.default_enabled ?? false,
            description: coerceString(definition.description) || undefined,
          }))
          .filter((definition) => definition.key)
      : [],
  };
}

function mapIntegrationCategory(raw: AdminIntegrationCategoryRaw): IntegrationData["categories"][number] {
  return {
    id: coerceString(raw.id),
    title: coerceString(raw.title) || "Untitled",
    description: coerceString(raw.description),
  };
}

function mapCredentialProfile(
  raw: AdminCredentialProfileRaw,
): IntegrationData["credentialProfiles"][number] {
  return {
    id: coerceString(raw.id),
    providerKey: coerceString(raw.provider_key),
    label: coerceString(raw.label) || "Saved profile",
    credentialsMasked:
      raw.credentials_masked && typeof raw.credentials_masked === "object"
        ? (raw.credentials_masked as Record<string, unknown>)
        : {},
    updatedAt: coerceString(raw.updated_at) || undefined,
    updatedBy: coerceString(raw.updated_by) || undefined,
    usageIntegrationKeys: Array.isArray(raw.usage_integration_keys)
      ? raw.usage_integration_keys.filter((item): item is string => typeof item === "string")
      : [],
  };
}

function mapIntegrationsResponse(raw: AdminIntegrationsResponseRaw | IntegrationData): IntegrationData {
  const providersSource = Array.isArray((raw as AdminIntegrationsResponseRaw).providers)
    ? ((raw as AdminIntegrationsResponseRaw).providers as AdminIntegrationRaw[])
    : Array.isArray((raw as AdminIntegrationsResponseRaw).integrations)
      ? ((raw as AdminIntegrationsResponseRaw).integrations as AdminIntegrationRaw[])
      : [];

  return {
    categories: Array.isArray((raw as AdminIntegrationsResponseRaw).categories)
      ? ((raw as AdminIntegrationsResponseRaw).categories as AdminIntegrationCategoryRaw[]).map(
          mapIntegrationCategory,
        )
      : "categories" in raw
        ? ((raw as IntegrationData).categories ?? [])
        : [],
    providers: providersSource.map(mapIntegrationProvider),
    credentialProfiles: Array.isArray((raw as AdminIntegrationsResponseRaw).credential_profiles)
      ? ((raw as AdminIntegrationsResponseRaw).credential_profiles as AdminCredentialProfileRaw[]).map(
          mapCredentialProfile,
        )
      : "credentialProfiles" in raw
        ? ((raw as IntegrationData).credentialProfiles ?? [])
        : [],
    featureFlags: mapIntegrationFlags(
      (raw as AdminIntegrationsResponseRaw).feature_flags ?? (raw as AdminIntegrationsResponseRaw).featureFlags,
    ),
    healthNotes: Array.isArray((raw as AdminIntegrationsResponseRaw).health_notes)
      ? ((raw as AdminIntegrationsResponseRaw).health_notes as string[])
      : Array.isArray((raw as AdminIntegrationsResponseRaw).healthNotes)
        ? ((raw as AdminIntegrationsResponseRaw).healthNotes as string[])
        : [],
    runtimeSettings:
      "runtimeSettings" in raw && raw.runtimeSettings
        ? {
            mockDataEnabled: raw.runtimeSettings.mockDataEnabled ?? true,
            liveInventoryAvailable: raw.runtimeSettings.liveInventoryAvailable ?? false,
            currentInventoryMode:
              raw.runtimeSettings.currentInventoryMode === "live"
                ? "live"
                : raw.runtimeSettings.currentInventoryMode === "empty"
                  ? "empty"
                  : "mock",
          }
        : {
            mockDataEnabled:
              (raw as AdminIntegrationsResponseRaw).runtime_settings?.mock_data_enabled ?? true,
            liveInventoryAvailable:
              (raw as AdminIntegrationsResponseRaw).runtime_settings?.live_inventory_available ??
              false,
            currentInventoryMode:
              (raw as AdminIntegrationsResponseRaw).runtime_settings?.current_inventory_mode ===
              "live"
                ? "live"
                : (raw as AdminIntegrationsResponseRaw).runtime_settings?.current_inventory_mode ===
                    "empty"
                  ? "empty"
                  : "mock",
          },
  };
}

function mapIntegrationTestResponse(providerKey: string, raw: AdminIntegrationTestRaw): IntegrationTestResult {
  const explicitHealthy = raw.healthy ?? raw.ok;
  const sourceStatus = coerceString(raw.status).toLowerCase();
  const passed =
    explicitHealthy === true || ["connected", "healthy", "ok", "success", "passed"].includes(sourceStatus);

  return {
    providerKey,
    status: passed ? "connected" : "attention",
    message:
      coerceString(raw.detail) ||
      coerceString(raw.message) ||
      (passed ? "Connection test passed." : "Connection test needs attention."),
    testedAt: coerceString(raw.tested_at) || coerceString(raw.testedAt) || undefined,
  };
}

function readDealId(value: unknown): string | undefined {
  if (!value || typeof value !== "object") {
    return typeof value === "string" ? value : undefined;
  }

  const objectValue = value as Record<string, unknown>;
  const nestedDeal = objectValue.deal;
  return (
    coerceString(objectValue.deal_id) ||
    coerceString(objectValue.dealId) ||
    coerceString(objectValue.id) ||
    (nestedDeal && typeof nestedDeal === "object"
      ? coerceString((nestedDeal as Record<string, unknown>).id) ||
        coerceString((nestedDeal as Record<string, unknown>).deal_id)
      : "")
  ) || undefined;
}

function mapCurrentUser(raw: AuthResponseRaw["user"]): CurrentUser {
  return {
    id: raw.id,
    email: raw.email,
    role: raw.role,
    onboardingCompleted: raw.onboarding_completed,
    defaultNotifyChannel: raw.default_notify_channel,
    telegramChatId: raw.telegram_chat_id,
    totpEnabled: raw.totp_enabled,
  };
}

function emptyWorkspace(currentUser: CurrentUser | null = null): ProfileWorkspace {
  return {
    currentUser,
    travelers: [],
    travelerGroups: [],
    travelerGroupOptions: [],
    preferences: {
      homeAirports: [],
      defaultCabin: "economy",
      defaultLuxuryVsSavings: 0.6,
      preferredAlliances: [],
      preferredAirlines: [],
      avoidedAirlines: [],
      preferredHotelBrands: [],
      avoidedHotelBrands: [],
      quietHoursStart: "",
      quietHoursEnd: "",
      defaultNotifyChannel: "email",
      avoidRedeye: false,
      preferRefundable: false,
      seatAutoSelect: false,
      defaultHotelMinRating: "",
      maxLayoverMinutes: "",
      minConnectionMinutes: "",
    },
    paymentMethods: [],
    templates: [],
    householdSummary: {
      travelerCount: 0,
      travelerGroupCount: 0,
      paymentMethodCount: 0,
      templateCount: 0,
      passportGapCount: 0,
      hasSelfTraveler: false,
      hasPaymentMethod: false,
      totpEnabled: Boolean(currentUser?.totpEnabled),
      setupWarnings: [],
      readinessLabel: "Household setup needs attention",
    },
  };
}

function deriveTravelerGroups(workspace: ProfileWorkspace): string[] {
  if (workspace.travelerGroups.length > 0) {
    return workspace.travelerGroups;
  }

  const names = workspace.travelers.map((traveler) => traveler.displayName).filter(Boolean);
  if (names.length === 0) {
    return [];
  }

  const groups = ["All travelers"];
  if (names.length >= 2) {
    groups.push(`${names[0]} + ${names[1]}`);
  }
  for (const name of names) {
    groups.push(`Solo · ${name}`);
  }
  return [...new Set(groups)];
}

function mapTravelerProfile(traveler: TravelerRaw): TravelerProfile {
  const loyaltyPrograms = (traveler.loyalty_programs ?? []).map((program) => ({
    programType: program.program_type,
    programCode: program.program_code,
    accountNumber: program.account_number,
    alliance: program.alliance,
    statusTier: program.status_tier ?? "",
    isFavorite: program.is_favorite,
  }));
  const favoriteLoyaltyProgram =
    loyaltyPrograms.find((program) => program.isFavorite) ?? loyaltyPrograms[0];

  return {
    id: traveler.id,
    displayName: traveler.display_name,
    relationship: traveler.traveler_relationship,
    legalFirstName: traveler.legal_first_name,
    legalLastName: traveler.legal_last_name,
    dob: traveler.dob,
    nationality: traveler.nationality,
    residencyCountry: traveler.residency_country ?? "",
    passportNumber: traveler.passport_number ?? "",
    passportCountry: traveler.passport_country ?? "",
    passportExpiry: traveler.passport_expiry ?? "",
    knownTravelerNumber: traveler.known_traveler_number ?? "",
    redressNumber: traveler.redress_number ?? "",
    seatPreference: traveler.seat_pref,
    mealPreference: traveler.meal_pref ?? "",
    loyaltyProgramCode: favoriteLoyaltyProgram?.programCode ?? traveler.loyalty_program_code ?? "",
    loyaltyAccountNumber:
      favoriteLoyaltyProgram?.accountNumber ?? traveler.loyalty_account_number ?? "",
    loyaltyAlliance: favoriteLoyaltyProgram?.alliance ?? traveler.loyalty_alliance ?? "none",
    loyaltyStatusTier:
      favoriteLoyaltyProgram?.statusTier ?? traveler.loyalty_status_tier ?? "",
    preferredEarningForAlliance:
      favoriteLoyaltyProgram?.isFavorite ?? traveler.preferred_earning_for_alliance,
    loyaltyPrograms,
    accessibilityNeeds: traveler.accessibility_needs ?? "",
    infantOnLap: traveler.infant_on_lap,
  };
}

function mapProfile(raw: ProfileSummaryRaw): ProfileWorkspace {
  const workspace: ProfileWorkspace = {
    currentUser: {
      id: raw.settings.id,
      email: raw.settings.email,
      role: raw.settings.role,
      onboardingCompleted: raw.settings.onboarding_completed,
      defaultNotifyChannel: raw.settings.default_notify_channel,
      telegramChatId: raw.settings.telegram_chat_id,
      totpEnabled: raw.settings.totp_enabled,
    },
    travelers: raw.travelers.map(mapTravelerProfile),
    travelerGroups: raw.traveler_groups.map((group) => group.name),
    travelerGroupOptions: raw.traveler_groups.map((group) => ({
      id: group.id,
      name: group.name,
      travelerIds: group.traveler_ids,
    })),
    preferences: {
      homeAirports: raw.preferences.home_airports ?? [],
      defaultCabin: raw.preferences.default_cabin ?? "economy",
      defaultLuxuryVsSavings: raw.preferences.default_luxury_vs_savings,
      preferredAlliances: raw.preferences.preferred_alliances ?? [],
      preferredAirlines: raw.preferences.preferred_airlines ?? [],
      avoidedAirlines: raw.preferences.avoided_airlines ?? [],
      preferredHotelBrands: raw.preferences.preferred_hotel_brands ?? [],
      avoidedHotelBrands: raw.preferences.avoided_hotel_brands ?? [],
      quietHoursStart: raw.preferences.quiet_hours_start ?? "",
      quietHoursEnd: raw.preferences.quiet_hours_end ?? "",
      defaultNotifyChannel: raw.preferences.default_notify_channel,
      avoidRedeye: raw.preferences.avoid_redeye,
      preferRefundable: raw.preferences.prefer_refundable,
      seatAutoSelect: raw.preferences.seat_auto_select,
      defaultHotelMinRating:
        raw.preferences.default_hotel_min_rating === null
          ? ""
          : String(raw.preferences.default_hotel_min_rating),
      maxLayoverMinutes:
        raw.preferences.default_max_layover_minutes === null
          ? ""
          : String(raw.preferences.default_max_layover_minutes),
      minConnectionMinutes:
        raw.preferences.default_min_connection_minutes === null
          ? ""
          : String(raw.preferences.default_min_connection_minutes),
    },
    paymentMethods: raw.payment_methods.map((paymentMethod) => ({
      id: paymentMethod.id,
      label: paymentMethod.label,
      brand: paymentMethod.brand ?? "",
      cardholderName: paymentMethod.cardholder_name ?? "",
      cardNumber: "",
      last4: paymentMethod.last4 ?? "",
      expMonth: paymentMethod.exp_month === null ? "" : String(paymentMethod.exp_month),
      expYear: paymentMethod.exp_year === null ? "" : String(paymentMethod.exp_year),
      providerToken: paymentMethod.provider_token ?? "",
      billingAddressLine1: paymentMethod.billing_address?.line1 ?? "",
      billingAddressCity: paymentMethod.billing_address?.city ?? "",
      billingAddressPostalCode: paymentMethod.billing_address?.postal_code ?? "",
      billingCountry: paymentMethod.billing_address?.country ?? "",
    })),
    templates: raw.trip_templates.map((template) => ({
      id: template.id,
      name: template.name,
      travelerGroup: String(template.watch_payload.travelerGroup ?? "All travelers"),
      origin: String(template.watch_payload.origin ?? ""),
      destination: String(template.watch_payload.destination ?? ""),
      flightBudgetMax: String(template.watch_payload.flightBudgetMax ?? ""),
      hotelBudgetPerNightMax: String(template.watch_payload.hotelBudgetPerNightMax ?? ""),
      notes: String(template.watch_payload.notes ?? ""),
    })),
    householdSummary: {
      travelerCount: raw.household_summary?.traveler_count ?? raw.travelers.length,
      travelerGroupCount: raw.household_summary?.traveler_group_count ?? raw.traveler_groups.length,
      paymentMethodCount: raw.household_summary?.payment_method_count ?? raw.payment_methods.length,
      templateCount: raw.household_summary?.template_count ?? raw.trip_templates.length,
      passportGapCount: raw.household_summary?.passport_gap_count ?? 0,
      hasSelfTraveler: raw.household_summary?.has_self_traveler ?? raw.travelers.length > 0,
      hasPaymentMethod: raw.household_summary?.has_payment_method ?? raw.payment_methods.length > 0,
      totpEnabled: raw.household_summary?.totp_enabled ?? raw.settings.totp_enabled,
      setupWarnings: asStringList(raw.household_summary?.setup_warnings),
      readinessLabel:
        coerceString(raw.household_summary?.readiness_label) || "Household setup needs attention",
    },
  };

  workspace.travelerGroups = deriveTravelerGroups(workspace);
  return workspace;
}

async function liveOrFallback<T>(request: () => Promise<T>, fallback: T): Promise<T> {
  if (useMockData) {
    return withLatency(fallback);
  }

  try {
    return await request();
  } catch (error) {
    if (error instanceof ApiError && [404, 501].includes(error.status)) {
      return withLatency(fallback);
    }

    throw error;
  }
}

function isEndpointUnavailable(error: unknown) {
  return error instanceof ApiError && [404, 405, 501].includes(error.status);
}

async function tryCandidateGet<T>(paths: string[]) {
  for (const path of paths) {
    try {
      return await apiClient.get<T>(path);
    } catch (error) {
      if (isEndpointUnavailable(error)) {
        continue;
      }

      throw error;
    }
  }

  return null;
}

async function tryCandidatePost<T>(paths: string[], body?: unknown) {
  for (const path of paths) {
    try {
      return await apiClient.post<T>(path, body);
    } catch (error) {
      if (isEndpointUnavailable(error)) {
        continue;
      }

      throw error;
    }
  }

  return null;
}

async function getCurrentUser() {
  if (useMockData) {
    return null;
  }

  try {
    const response = await apiClient.get<AuthResponseRaw>("/auth/me");
    return mapCurrentUser(response.user);
  } catch (error) {
    if (error instanceof ApiError && [401, 403].includes(error.status)) {
      return null;
    }

    throw error;
  }
}

function buildWatchDraftFromWorkspace(workspace: ProfileWorkspace, watchId?: string): WatchDraft {
  const travelerOptions = workspace.travelers.map((traveler) => ({
    id: traveler.id,
    displayName: traveler.displayName,
    relationship: traveler.relationship,
  }));
  const travelerGroups =
    workspace.travelerGroupOptions.length > 0
      ? workspace.travelerGroupOptions
      : deriveTravelerGroups(workspace).map((name, index) => ({
          id: `derived-${index}`,
          name,
          travelerIds: workspace.travelers.map((traveler) => traveler.id),
        }));
  const primaryTemplate = workspace.templates[0];
  const selectedGroup =
    travelerGroups.find((group) => group.name === primaryTemplate?.travelerGroup) ?? travelerGroups[0];
  const selectedTravelerIds = selectedGroup?.travelerIds ?? travelerOptions.map((traveler) => traveler.id);

  return {
    id: watchId,
    title: watchId ? "Refine watch" : "Create a new watch",
    travelerOptions,
    status: "active",
    travelerGroups,
    selectedTravelerIds,
    selectedGroupId: selectedGroup?.id ?? "",
    selectedGroup: selectedGroup?.name ?? "All travelers",
    tripMode: "flights_then_hotels",
    origins: workspace.preferences.homeAirports.join(", "),
    destination: primaryTemplate?.destination ?? "",
    destinationMode: "fixed",
    flexibleRegion: "",
    flexibleTheme: "",
    departDateFrom: "",
    departDateTo: "",
    returnDateFrom: "",
    returnDateTo: "",
    tripMinNights: "",
    tripMaxNights: "",
    cabinClass: "",
    maxStops: "",
    maxLayoverMinutes: "",
    minConnectionMinutes: "",
    preferredAirlines: listToText(workspace.preferences.preferredAirlines),
    preferredAlliances: listToText(workspace.preferences.preferredAlliances),
    budgetCurrency: "JPY",
    flightBudget: primaryTemplate?.flightBudgetMax || "",
    hotelBudget: primaryTemplate?.hotelBudgetPerNightMax || "",
    luxuryVsSavings: workspace.preferences.defaultLuxuryVsSavings,
    hotelMinRating: workspace.preferences.defaultHotelMinRating,
    preferRefundable: workspace.preferences.preferRefundable,
    avoidRedeye: workspace.preferences.avoidRedeye,
    includeAirbnb: false,
    wantCar: false,
    notifyChannel: workspace.preferences.defaultNotifyChannel || "inherit",
    refreshInterval: "daily",
    idealPrice: "",
    glideStartDays: "42",
    glideEndDays: "3",
  };
}

function matchTravelerGroupForIds(
  travelerIds: string[],
  travelerGroups: Array<{ id: string; name: string; travelerIds: string[] }>,
) {
  const normalizedSelected = [...new Set(travelerIds)];
  return travelerGroups.find((group) => {
    const normalizedGroup = [...new Set(group.travelerIds)];
    return (
      normalizedGroup.length === normalizedSelected.length &&
      normalizedGroup.every((travelerId) => normalizedSelected.includes(travelerId))
    );
  });
}

function resolveTravelerGroup(raw: WatchRaw, workspace: ProfileWorkspace) {
  const rawGroup = raw.traveler_group;
  const rawGroupId =
    coerceString(raw.traveler_group_id) ||
    (rawGroup && typeof rawGroup === "object" ? coerceString((rawGroup as WatchGroupRaw).id) : "");
  const rawGroupName =
    coerceString(raw.traveler_group_name) ||
    (typeof rawGroup === "string" ? rawGroup : "") ||
    (rawGroup && typeof rawGroup === "object" ? coerceString((rawGroup as WatchGroupRaw).name) : "");

  const matchedGroup = workspace.travelerGroupOptions.find(
    (group) => group.id === rawGroupId || group.name === rawGroupName,
  );

  return {
    id: matchedGroup?.id ?? rawGroupId,
    name: matchedGroup?.name || rawGroupName || raw.travelers_label || "All travelers",
  };
}

function mapWatchToSummary(raw: WatchRaw, workspace: ProfileWorkspace): WatchSummary {
  const currency = coerceString(raw.budget_currency) || coerceString(raw.current_deal?.home_currency) || "JPY";
  const dealPrice = raw.current_deal?.all_in_price ?? raw.latest_deal?.all_in_price ?? raw.best_price;
  const bestNow =
    coerceString(raw.best_now) ||
    coerceString(raw.bestNow) ||
    (dealPrice !== undefined && dealPrice !== null ? formatMoneyValue(dealPrice, currency) : "") ||
    (raw.status === "paused" ? "Paused" : "No live price yet");

  const travelerGroup = resolveTravelerGroup(raw, workspace);
  const derivedTravelers =
    raw.travelers ||
    raw.travelers_label ||
    travelerGroup.name ||
    (raw.current_deal?.summary ? "Saved traveler set" : "Traveler set");

  return {
    id: coerceString(raw.id),
    route: formatRouteFromWatch(raw),
    dates: formatDatesFromWatch(raw),
    travelers: derivedTravelers,
    cabin: raw.cabin || formatCabinLabel(raw.cabin_class),
    status: (raw.status as WatchStatus) || "active",
    framing: formatFramingLabel(raw.framing || raw.current_deal?.framing || raw.latest_deal?.framing),
    bestNow,
    insight:
      coerceString(raw.insight) ||
      coerceString(raw.current_deal?.summary) ||
      coerceString(raw.latest_deal?.summary) ||
      coerceString(raw.summary) ||
      coerceString(raw.note) ||
      "Watch saved to the live backend. Run a fresh search to update pricing context.",
    cadence: raw.cadence || formatRefreshLabel(raw.refresh_interval || raw.refreshInterval),
    currentDealId:
      readDealId(raw.current_deal) || readDealId(raw.latest_deal) || coerceString(raw.deal_id || raw.dealId) || undefined,
    currentDealStatus:
      coerceString((raw.current_deal as WatchCurrentDealRaw | undefined)?.status) ||
      coerceString((raw.latest_deal as WatchCurrentDealRaw | undefined)?.status) ||
      undefined,
    searchLabel: readDealId(raw.current_deal) || readDealId(raw.latest_deal) || coerceString(raw.deal_id || raw.dealId)
      ? "Open deal"
      : "Search now",
    readiness: mapReadiness(raw.readiness),
    badges: mapBadges(raw.badges),
    ctaActions: mapCtaActions(raw.cta_actions),
  };
}

function buildCoverageLines(report?: CoverageReportRaw | null, explicitCoverage?: string[]) {
  if (explicitCoverage && explicitCoverage.length > 0) {
    return explicitCoverage;
  }

  if (!report) {
    return [];
  }

  const lines = [
    report.confidence ? `Coverage confidence: ${titleizeStatus(report.confidence)}` : "",
    report.searched_sources?.length ? `${report.searched_sources.length} sources searched` : "",
    report.searched_sources?.length ? report.searched_sources.join(", ") : "",
    ...(report.gaps ?? []).map((gap) => `Gap: ${gap}`),
    ...(report.notes ?? []),
  ].filter(Boolean);

  return lines;
}

function buildWarningLines(warnings?: string[], validationWarnings?: ValidationWarningRaw[]) {
  const validationMessages =
    validationWarnings?.map((warning) =>
      [warning.message, warning.traveler_name ? `Traveler: ${warning.traveler_name}` : ""].filter(Boolean).join(" · "),
    ) ?? [];
  return [...(warnings ?? []), ...validationMessages].filter(Boolean);
}

function buildLoyaltyLines(loyaltyPlan?: string[], entries?: LoyaltyPlanEntryRaw[]) {
  const mappedEntries =
    entries?.map((entry) =>
      [entry.traveler_name, entry.program_code, entry.alliance, entry.note].filter(Boolean).join(" -> "),
    ) ?? [];
  return [...(loyaltyPlan ?? []), ...mappedEntries].filter(Boolean);
}

function mergeUnique(items: Array<string | undefined>) {
  return [...new Set(items.map((item) => item?.trim()).filter(Boolean) as string[])];
}

function readDealPayloadText(raw: SearchNowDealRaw | LiveDealResponseRaw, key: string) {
  const payload = raw.payload;
  if (!payload || typeof payload !== "object") {
    return "";
  }
  const value = payload[key];
  return typeof value === "string" ? value : "";
}

function mapDealPayloadToView(
  raw: SearchNowDealRaw | LiveDealResponseRaw | null | undefined,
  options: {
    dealId: string;
    watchId?: string;
    route?: string;
    cabin?: string;
    context?: string;
    breakdown?: string;
    explicitPrice?: string;
    explicitWasPrice?: string;
    details?: string[];
    warnings?: string[];
    loyaltyPlan?: string[];
    coverage?: string[];
    provider?: string;
  } = { dealId: "" },
): DealData | null {
  if (!raw) {
    return null;
  }

  const currency = coerceString(raw.currency) || "JPY";
  const price = options.explicitPrice || formatMoneyValue(raw.total_price, currency) || dealData.price;
  const route = options.route || coerceString((raw as LiveDealResponseRaw).route) || "Saved deal";
  const cabin =
    options.cabin ||
    coerceString((raw as LiveDealResponseRaw).cabin_label) ||
    coerceString((raw as LiveDealResponseRaw).cabin) ||
    "Cabin not specified";
  const context =
    options.context ||
    readDealPayloadText(raw, "historical_context") ||
    coerceString((raw as LiveDealResponseRaw).context) ||
    coerceString(raw.summary_text) ||
    "This deal came from the live watch pipeline. Review provider, warnings, and coverage before approval.";
  const timingAdvice = coerceString(raw.timing_advice);
  const provider = options.provider || coerceString(raw.source);
  const details = mergeUnique([
    ...(options.details ?? []),
    provider ? `Provider: ${provider}` : undefined,
    readDealPayloadText(raw, "target_price") ? `Target price ${readDealPayloadText(raw, "target_price")} ${currency}` : undefined,
    readDealPayloadText(raw, "glide_limit") ? `Current glide limit ${readDealPayloadText(raw, "glide_limit")} ${currency}` : undefined,
    timingAdvice || undefined,
    raw.kind ? `Inventory type: ${titleizeStatus(raw.kind)}` : undefined,
  ]);
  const warnings = mergeUnique([
    ...(options.warnings ?? []),
    ...buildWarningLines(undefined, raw.validation_warnings),
  ]);
  const loyaltyPlan = mergeUnique([
    ...(options.loyaltyPlan ?? []),
    ...buildLoyaltyLines(undefined, raw.loyalty_plan),
  ]);
  const coverage = mergeUnique([
    ...(options.coverage ?? []),
    ...buildCoverageLines(raw.coverage_report),
  ]);
  const scoreSource = raw.value_score ?? raw.quality_index ?? (raw.price_percentile ? 100 - raw.price_percentile : null);
  const score = Math.max(0, Math.min(100, Math.round(scoreSource ?? 0)));
  const dealStatus = coerceString(raw.status) || undefined;
  const booking = "booking" in raw ? raw.booking : null;
  const cancellation = "cancellation" in raw ? raw.cancellation : null;
  const refundReceived = cancellation ? formatMoneyValue(cancellation.refund_received, cancellation.currency || currency) : "";
  const refundExpected = cancellation ? formatMoneyValue(cancellation.refund_expected, cancellation.currency || currency) : "";
  const readiness = mapReadiness(raw.readiness);
  const badges = mapBadges(raw.badges);
  const ctaActions = mapCtaActions(raw.cta_actions);

  return {
    id: coerceString(raw.id) || options.dealId,
    watchId: options.watchId,
    route,
    cabin,
    price,
    wasPrice: options.explicitWasPrice || "",
    context,
    breakdown:
      options.breakdown ||
      [
        provider ? `Provider ${provider}` : "",
        readDealPayloadText(raw, "target_price") ? `Target ${readDealPayloadText(raw, "target_price")} ${currency}` : "",
        timingAdvice,
        raw.price_percentile !== null && raw.price_percentile !== undefined
          ? `Price percentile ${Math.round(raw.price_percentile)}`
          : "",
      ]
        .filter(Boolean)
        .join(" · "),
    score,
    details,
    loyaltyPlan,
    warnings,
    coverage,
    provider: provider || undefined,
    expiresAt:
      "expires_at" in raw ? formatDateTime(coerceString((raw as LiveDealResponseRaw).expires_at) || undefined) || undefined : undefined,
    dealStatus,
    bookingStatus: coerceString(booking?.status) || undefined,
    cancellationStatus: coerceString(cancellation?.status) || undefined,
    refundStatus:
      cancellation?.status
        ? refundReceived
          ? "Refund received"
          : refundExpected
            ? "Refund pending"
            : titleizeStatus(cancellation.status)
        : undefined,
    refundAmount: refundReceived || refundExpected || undefined,
    approvalDetail:
      booking?.error_text ||
      (dealStatus === "confirmed"
        ? "Approval intent has already been recorded for this deal."
        : "Confirming this deal records secure approval intent with TOTP. Booking remains a later deterministic step."),
    readiness,
    badges,
    ctaActions,
  };
}

function buildDealFromWatch(
  watch: WatchResponseRaw,
  dealId: string,
  seed?: Partial<DealData> | null,
): DealViewData {
  const currentDeal = watch.current_deal;
  const route = watch.route || formatRouteFromWatch(watch);
  const cabin = coerceString(watch.cabin_label) || formatCabinLabel(watch.cabin_class);
  const base = mapDealPayloadToView(currentDeal, {
    dealId,
    watchId: coerceString(watch.id) || seed?.watchId,
    route: seed?.route || route,
    cabin: seed?.cabin || cabin,
    context: seed?.context || coerceString(currentDeal?.summary_text),
    breakdown: seed?.breakdown,
    explicitPrice: seed?.price,
    explicitWasPrice: seed?.wasPrice,
    details: seed?.details,
    warnings: seed?.warnings,
    loyaltyPlan: seed?.loyaltyPlan,
    coverage: seed?.coverage,
    provider: seed?.provider,
  });

  return {
    deal:
      base ?? {
        ...seed,
        id: dealId,
        watchId: coerceString(watch.id) || seed?.watchId,
        route: seed?.route || route,
        cabin: seed?.cabin || cabin,
        price: seed?.price || "Live price unavailable",
        wasPrice: seed?.wasPrice || "",
        context:
          seed?.context ||
          "A live deal summary exists on this watch, but the dedicated deal review endpoint is not available yet.",
        breakdown: seed?.breakdown || "",
        score: seed?.score ?? 0,
        details: seed?.details ?? [],
        loyaltyPlan: seed?.loyaltyPlan ?? [],
        warnings: seed?.warnings ?? [],
        coverage: seed?.coverage ?? [],
        badges: seed?.badges ?? [],
        ctaActions: seed?.ctaActions ?? [],
      },
    source: "watch-derived",
    fallbackNote:
      "Detailed deal review is not exposed by this backend yet. Showing the best live context available from the watch record.",
    approvalAvailable: true,
  };
}

function mapBookingRecord(raw: BookingRaw): BookingSummary {
  const currency =
    coerceString(raw.currency) || coerceString(raw.cancellation?.currency) || coerceString(raw.deal?.currency) || "JPY";
  const route = coerceString(raw.title) || coerceString(raw.route) || "Booked trip";
  const bookedAtLabel = formatDateTime(raw.booked_at);
  const cancellationStatus = coerceString(raw.cancellation?.status);
  const refundReceived = formatMoneyValue(raw.cancellation?.refund_received, currency);
  const refundExpected = formatMoneyValue(raw.cancellation?.refund_expected, currency);
  const bookingStatus = coerceString(raw.status);

  return {
    id: coerceString(raw.id),
    dealId: coerceString(raw.deal_id) || readDealId(raw.deal),
    watchId: coerceString(raw.watch_id),
    title: route,
    when: coerceString(raw.when) || bookedAtLabel || "Travel dates pending",
    status:
      cancellationStatus
        ? `${titleizeStatus(cancellationStatus)} cancellation`
        : titleizeStatus(bookingStatus) || "Booking update",
    amount:
      formatMoneyValue(raw.amount_charged, currency) ||
      formatMoneyValue(raw.deal?.total_price, raw.deal?.currency || currency) ||
      "Amount pending",
    provider: coerceString(raw.provider) || coerceString(raw.deal?.source) || "Provider pending",
    actions: [
      coerceString(raw.deal_id) || readDealId(raw.deal) ? "Open deal review" : "",
      cancellationStatus ? "Review cancellation state" : "View itinerary",
    ].filter(Boolean),
    bookingStatus: bookingStatus || undefined,
    cancellationStatus: cancellationStatus || undefined,
    refundStatus:
      cancellationStatus
        ? refundReceived
          ? "Refund received"
          : refundExpected
            ? "Refund pending"
            : titleizeStatus(cancellationStatus)
        : undefined,
    refundAmount: refundReceived || refundExpected || undefined,
    providerReference: coerceString(raw.provider_booking_ref) || undefined,
    statusDetail:
      raw.error_text ||
      coerceString(raw.ticketing_state) ||
      (bookedAtLabel ? `Booked ${bookedAtLabel}` : ""),
    approvalDetail:
      bookingStatus === "pending_ticketing"
        ? "Approval succeeded and provider ticketing is still in flight."
        : undefined,
    bookedAt: coerceString(raw.booked_at) || undefined,
    calendarDetail: coerceString(raw.calendar_detail) || undefined,
    notificationStatuses: Array.isArray(raw.notifications)
      ? raw.notifications.map((notification) => {
          const channel = titleizeStatus(coerceString(notification.channel)) || "Notification";
          const status = titleizeStatus(coerceString(notification.status)) || "Pending";
          return `${channel}: ${status}`;
        })
      : [],
    disruptionStatuses: Array.isArray(raw.disruptions)
      ? raw.disruptions.map((disruption) => {
          const kind = titleizeStatus(coerceString(disruption.type)) || "Disruption";
          const status = titleizeStatus(coerceString(disruption.status)) || "New";
          return `${kind}: ${status}`;
        })
      : [],
    disruptions: Array.isArray(raw.disruptions)
      ? raw.disruptions.map((disruption) => ({
          id: coerceString(disruption.id),
          type: coerceString(disruption.type),
          status: coerceString(disruption.status),
        }))
      : [],
  };
}

function deriveDashboardFromWatches(watches: WatchSummary[]): DashboardData {
  const activeCount = watches.filter((watch) => watch.status === "active").length;
  const bestCandidate = watches.find((watch) => watch.bestNow && watch.bestNow !== "Paused");

  return {
    highlights: [
      {
        label: "Best value today",
        value: bestCandidate?.bestNow || "No live price yet",
        note: bestCandidate
          ? `${bestCandidate.route} is the strongest live watch candidate right now.`
          : "Save a watch and run Search now to populate live pricing context.",
      },
      {
        label: "Active watches",
        value: String(activeCount),
        note: `${watches.length} watches loaded from the backend dashboard.`,
      },
      {
        label: "Coverage confidence",
        value: watches.length > 0 ? "Live" : "Waiting",
        note: "The dashboard is now derived from the live watch collection when dedicated highlights are unavailable.",
      },
    ],
    watches,
  };
}

function mapDashboardResponse(raw: WatchDashboardRaw | WatchRaw[] | null | undefined, workspace: ProfileWorkspace) {
  if (Array.isArray(raw)) {
    return deriveDashboardFromWatches(raw.map((watch) => mapWatchToSummary(watch, workspace)));
  }

  if (!raw) {
    return null;
  }

  const watchList = Array.isArray(raw.watches)
    ? raw.watches
    : Array.isArray(raw.items)
      ? raw.items
      : Array.isArray(raw.data)
        ? raw.data
        : [];
  const watches = watchList.map((watch) => mapWatchToSummary(watch, workspace));

  const highlights =
    raw.highlights?.map((item) => ({
      label: coerceString(item.label),
      value: String(item.value ?? ""),
      note: coerceString(item.note),
    })) ?? [];

  if (highlights.length > 0) {
    return {
      highlights,
      watches,
    };
  }

  return deriveDashboardFromWatches(watches);
}

function mapWatchToDraft(raw: WatchRaw, workspace: ProfileWorkspace): WatchDraft {
  const fallback = buildWatchDraftFromWorkspace(workspace, coerceString(raw.id));
  const travelerGroup = resolveTravelerGroup(raw, workspace);
  const matchedGroup =
    workspace.travelerGroupOptions.find((group) => group.id === travelerGroup.id || group.name === travelerGroup.name) ??
    fallback.travelerGroups.find((group) => group.name === travelerGroup.name);
  const selectedTravelerIds =
    Array.isArray(raw.traveler_ids) && raw.traveler_ids.length > 0
      ? raw.traveler_ids
      : matchedGroup?.travelerIds ?? fallback.selectedTravelerIds;

  return {
    ...fallback,
    id: coerceString(raw.id) || fallback.id,
    title: fallback.id ? `Refine ${formatRouteFromWatch(raw)}` : fallback.title,
    status: ((raw.status as WatchStatus) || fallback.status) as WatchStatus,
    travelerGroups: fallback.travelerGroups,
    selectedTravelerIds,
    selectedGroupId: matchedGroup?.id ?? fallback.selectedGroupId,
    selectedGroup: matchedGroup?.name || travelerGroup.name || fallback.selectedGroup,
    tripMode: coerceString(raw.trip_mode) || fallback.tripMode,
    origins: listToText(raw.origin_iatas) || fallback.origins,
    destination:
      raw.destination_mode === "flexible"
        ? fallback.destination
        : listToText(raw.destination_iatas) || fallback.destination,
    destinationMode: raw.destination_mode === "flexible" ? "flexible" : fallback.destinationMode,
    flexibleRegion: coerceString(raw.flexible_region),
    flexibleTheme: coerceString(raw.flexible_theme),
    departDateFrom: coerceString(raw.depart_date_from).slice(0, 10),
    departDateTo: coerceString(raw.depart_date_to).slice(0, 10),
    returnDateFrom: coerceString(raw.return_date_from).slice(0, 10),
    returnDateTo: coerceString(raw.return_date_to).slice(0, 10),
    tripMinNights: raw.trip_min_nights === null || raw.trip_min_nights === undefined ? "" : String(raw.trip_min_nights),
    tripMaxNights: raw.trip_max_nights === null || raw.trip_max_nights === undefined ? "" : String(raw.trip_max_nights),
    cabinClass: coerceString(raw.cabin_class) || fallback.cabinClass,
    maxStops: raw.max_stops === null || raw.max_stops === undefined ? "" : String(raw.max_stops),
    maxLayoverMinutes:
      raw.max_layover_minutes === null || raw.max_layover_minutes === undefined
        ? fallback.maxLayoverMinutes
        : String(raw.max_layover_minutes),
    minConnectionMinutes:
      raw.min_connection_minutes === null || raw.min_connection_minutes === undefined
        ? fallback.minConnectionMinutes
        : String(raw.min_connection_minutes),
    preferredAirlines: listToText(raw.preferred_airlines) || fallback.preferredAirlines,
    preferredAlliances: listToText(raw.preferred_alliances) || fallback.preferredAlliances,
    budgetCurrency: coerceString(raw.budget_currency) || fallback.budgetCurrency,
    flightBudget:
      raw.flight_budget_max === null || raw.flight_budget_max === undefined
        ? fallback.flightBudget
        : formatMoneyValue(raw.flight_budget_max, coerceString(raw.budget_currency) || "JPY"),
    hotelBudget:
      raw.hotel_budget_per_night_max === null || raw.hotel_budget_per_night_max === undefined
        ? fallback.hotelBudget
        : formatMoneyValue(raw.hotel_budget_per_night_max, coerceString(raw.budget_currency) || "JPY"),
    luxuryVsSavings:
      typeof raw.luxury_vs_savings === "number" ? raw.luxury_vs_savings : fallback.luxuryVsSavings,
    hotelMinRating:
      raw.hotel_min_rating === null || raw.hotel_min_rating === undefined ? fallback.hotelMinRating : String(raw.hotel_min_rating),
    preferRefundable: raw.prefer_refundable ?? fallback.preferRefundable,
    avoidRedeye: raw.avoid_redeye ?? fallback.avoidRedeye,
    includeAirbnb: raw.include_airbnb ?? fallback.includeAirbnb,
    wantCar: raw.want_car ?? fallback.wantCar,
    notifyChannel: coerceString(raw.notify_channel) || fallback.notifyChannel,
    refreshInterval: coerceString(raw.refresh_interval || raw.refreshInterval) || fallback.refreshInterval,
    idealPrice:
      raw.ideal_price === null || raw.ideal_price === undefined
        ? fallback.idealPrice
        : formatMoneyValue(raw.ideal_price, coerceString(raw.budget_currency) || "JPY"),
    glideStartDays:
      raw.glide_start_days === null || raw.glide_start_days === undefined
        ? fallback.glideStartDays
        : String(raw.glide_start_days),
    glideEndDays:
      raw.glide_end_days === null || raw.glide_end_days === undefined
        ? fallback.glideEndDays
        : String(raw.glide_end_days),
  };
}

function maybe(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function toInteger(value: string) {
  const numeric = parseNumericValue(value);
  return numeric === null ? undefined : Math.round(numeric);
}

function toNumber(value: string) {
  const numeric = parseNumericValue(value);
  return numeric === null ? undefined : numeric;
}

function parseTextList(value: string, normalize = (item: string) => item) {
  return value
    .split(",")
    .map((item) => normalize(item.trim()))
    .filter(Boolean);
}

function buildWatchPayload(draft: WatchDraft) {
  const matchedGroup = matchTravelerGroupForIds(draft.selectedTravelerIds, draft.travelerGroups);
  return {
    status: draft.status,
    trip_mode: draft.tripMode,
    traveler_group_id: maybe(matchedGroup?.id ?? draft.selectedGroupId),
    traveler_ids: draft.selectedTravelerIds,
    origin_iatas: parseTextList(draft.origins, (item) => item.toUpperCase()),
    destination_mode: draft.destinationMode,
    destination_iatas:
      draft.destinationMode === "fixed"
        ? parseTextList(draft.destination, (item) => item.toUpperCase())
        : undefined,
    flexible_region: draft.destinationMode === "flexible" ? maybe(draft.flexibleRegion) : undefined,
    flexible_theme: draft.destinationMode === "flexible" ? maybe(draft.flexibleTheme) : undefined,
    depart_date_from: maybe(draft.departDateFrom),
    depart_date_to: maybe(draft.departDateTo),
    return_date_from: maybe(draft.returnDateFrom),
    return_date_to: maybe(draft.returnDateTo),
    trip_min_nights: toInteger(draft.tripMinNights),
    trip_max_nights: toInteger(draft.tripMaxNights),
    cabin_class: maybe(draft.cabinClass),
    max_stops: toInteger(draft.maxStops),
    max_layover_minutes: toInteger(draft.maxLayoverMinutes),
    min_connection_minutes: toInteger(draft.minConnectionMinutes),
    preferred_airlines: parseTextList(draft.preferredAirlines, (item) => item.toUpperCase()),
    preferred_alliances: parseTextList(draft.preferredAlliances, (item) => item.toLowerCase()),
    flight_budget_max: toNumber(draft.flightBudget),
    hotel_budget_per_night_max: toNumber(draft.hotelBudget),
    budget_currency: maybe(draft.budgetCurrency.toUpperCase()),
    luxury_vs_savings: draft.luxuryVsSavings,
    hotel_min_rating: toNumber(draft.hotelMinRating),
    prefer_refundable: draft.preferRefundable,
    avoid_redeye: draft.avoidRedeye,
    include_airbnb: draft.includeAirbnb,
    want_car: draft.wantCar,
    notify_channel: draft.notifyChannel,
    refresh_interval: draft.refreshInterval,
    ideal_price: toNumber(draft.idealPrice),
    glide_start_days: toInteger(draft.glideStartDays),
    glide_end_days: toInteger(draft.glideEndDays),
  };
}

function mockProfileWorkspace(): ProfileWorkspace {
  return emptyWorkspace({
    id: "mock-user",
    email: "demo@example.com",
    role: "admin",
    onboardingCompleted: false,
    defaultNotifyChannel: "telegram",
    telegramChatId: null,
    totpEnabled: true,
  });
}

export const queryKeys = {
  dashboard: ["dashboard"] as const,
  watchDraft: (watchId?: string) => ["watch-draft", watchId ?? "new"] as const,
  deal: (dealId: string, watchId?: string) => ["deal", dealId, watchId ?? "unscoped"] as const,
  bookings: ["bookings"] as const,
  profile: ["profile"] as const,
  integrations: ["integrations"] as const,
  systemStatus: ["system-status"] as const,
};

export const travelWatchApi = {
  getSystemStatus: async () => {
    const policy = await getRuntimePolicy();
    return policy;
  },

  getDashboard: async (): Promise<DashboardData> => {
    if (useMockData) {
      return withLatency(dashboardData);
    }

    const workspace = await travelWatchApi.getProfileWorkspace();

    try {
      const response = await apiClient.get<WatchDashboardRaw>("/watches/dashboard");
      const mapped = mapDashboardResponse(response, workspace);
      if (mapped) {
        return mapped;
      }
    } catch (error) {
      if (!(error instanceof ApiError) || ![404, 501].includes(error.status)) {
        throw error;
      }
    }

    try {
      const response = await apiClient.get<WatchDashboardRaw | WatchRaw[]>("/watches");
      const mapped = mapDashboardResponse(response, workspace);
      if (mapped) {
        return mapped;
      }
    } catch (error) {
      if (error instanceof ApiError && [404, 501].includes(error.status)) {
        const policy = await getRuntimePolicy();
        if (policy.mockDataEnabled) {
          return withLatency(dashboardData);
        }
        return deriveDashboardFromWatches([]);
      }

      throw error;
    }

    const policy = await getRuntimePolicy();
    if (policy.mockDataEnabled) {
      return withLatency(dashboardData);
    }
    return deriveDashboardFromWatches([]);
  },

  getWatchDraft: async (watchId?: string): Promise<WatchDraft> => {
    if (useMockData) {
      return withLatency(watchId ? { ...editWatchDraft, id: watchId } : newWatchDraft);
    }

    const workspace = await travelWatchApi.getProfileWorkspace();
    if (!watchId) {
      return buildWatchDraftFromWorkspace(workspace);
    }

    try {
      const response = await apiClient.get<WatchRaw>(`/watches/${watchId}`);
      return mapWatchToDraft(response, workspace);
    } catch (error) {
      if (error instanceof ApiError && [404, 501].includes(error.status)) {
        return buildWatchDraftFromWorkspace(workspace, watchId);
      }

      throw error;
    }
  },

  getDealReview: async (
    dealId: string,
    options?: { watchId?: string; seed?: Partial<DealData> | null },
  ): Promise<DealViewData> => {
    const watchId = options?.watchId || options?.seed?.watchId;

    if (useMockData) {
      return withLatency({
        deal: {
          ...dealData,
          ...options?.seed,
          id: dealId,
          watchId,
        },
        source: "mock",
        approvalAvailable: true,
      });
    }

    const liveDeal = await tryCandidateGet<LiveDealResponseRaw>([`/deals/${dealId}`]);
    const liveTimeline = await tryCandidateGet<DealTimelineRaw>([`/deals/${dealId}/timeline`]);
    if (liveDeal) {
      const mapped = mapDealPayloadToView(liveDeal, {
        dealId,
        watchId: coerceString(liveDeal.watch_id) || watchId,
        route:
          options?.seed?.route ||
          coerceString(liveDeal.route) ||
          coerceString(liveDeal.watch?.route),
        cabin:
          options?.seed?.cabin ||
          coerceString(liveDeal.cabin_label) ||
          coerceString(liveDeal.cabin) ||
          coerceString(liveDeal.watch?.cabin_label),
        context: options?.seed?.context || coerceString(liveDeal.context),
        breakdown: options?.seed?.breakdown || coerceString(liveDeal.breakdown),
        explicitPrice: options?.seed?.price,
        explicitWasPrice: options?.seed?.wasPrice,
        details: [...(options?.seed?.details ?? []), ...(liveDeal.details ?? [])],
        warnings: [...(options?.seed?.warnings ?? []), ...(liveDeal.warnings ?? [])],
        loyaltyPlan: options?.seed?.loyaltyPlan,
        coverage: [...(options?.seed?.coverage ?? []), ...(liveDeal.coverage ?? [])],
        provider: options?.seed?.provider,
      });

      if (mapped) {
        mapped.timeline = mapDealTimeline(liveTimeline, coerceString(liveDeal.currency));
        return {
          deal: mapped,
          source: "live",
          approvalAvailable: true,
        };
      }
    }

    if (watchId) {
      try {
        const watch = await apiClient.get<WatchResponseRaw>(`/watches/${watchId}`);
        const built = buildDealFromWatch(watch, dealId, options?.seed);
        built.deal.timeline = mapDealTimeline(liveTimeline);
        return built;
      } catch (error) {
        if (!isEndpointUnavailable(error)) {
          throw error;
        }
      }
    }

    const policy = await getRuntimePolicy();
    if (!policy.mockDataEnabled) {
      throw new Error(
        "Mock data is disabled and no live deal review payload is available for this watch yet.",
      );
    }

    return {
      deal: {
        ...dealData,
        ...options?.seed,
        id: dealId,
        watchId,
      },
      source: "mock",
      fallbackNote:
        "Neither a dedicated deal review endpoint nor a watch-scoped deal summary is available yet. Showing the existing review fallback.",
      approvalAvailable: false,
    };
  },

  getBookings: async (): Promise<BookingsViewData> => {
    if (useMockData) {
      return withLatency({ items: bookingsData, source: "mock" });
    }

    const response = await tryCandidateGet<BookingRaw[] | { items?: BookingRaw[]; bookings?: BookingRaw[] }>([
      "/bookings",
    ]);
    if (response) {
      const items = Array.isArray(response)
        ? response
        : Array.isArray(response.items)
          ? response.items
          : Array.isArray(response.bookings)
            ? response.bookings
            : [];
      return {
        items: items.map(mapBookingRecord),
        source: "live",
      };
    }

    const policy = await getRuntimePolicy();
    if (!policy.mockDataEnabled) {
      return {
        items: [],
        source: "live",
        fallbackNote:
          "Mock data is disabled and no live bookings payload is available yet.",
      };
    }

    return {
      items: bookingsData,
      source: "mock",
      fallbackNote:
        "Live bookings are not exposed by this backend yet. Showing the existing booking placeholders until the endpoint lands.",
    };
  },

  getProfileWorkspace: async (): Promise<ProfileWorkspace> => {
    if (useMockData) {
      return withLatency(mockProfileWorkspace());
    }

    const currentUser = await getCurrentUser();
    if (!currentUser) {
      return emptyWorkspace();
    }

    const response = await apiClient.get<ProfileSummaryRaw>("/profile");
    return mapProfile(response);
  },

  saveWatchDraft: async (draft: WatchDraft) => {
    const payload = buildWatchPayload(draft);

    if (useMockData) {
      return withLatency({
        id: draft.id ?? "mock-watch",
      });
    }

    if (draft.id) {
      const response = await apiClient.patch<WatchRaw | { id?: string }>(`/watches/${draft.id}`, payload);
      return { id: readDealId(response) || coerceString((response as WatchRaw).id) || draft.id };
    }

    const response = await apiClient.post<WatchRaw | { id?: string }>("/watches", payload);
    return { id: readDealId(response) || coerceString((response as WatchRaw).id) };
  },

  updateWatchStatus: async (watchId: string, action: "pause" | "resume") => {
    if (useMockData) {
      await withLatency(null);
      return;
    }
    await apiClient.post(`/watches/${encodeURIComponent(watchId)}/${action}`, {});
  },

  searchWatchNow: async (watchId: string): Promise<SearchWatchNowResult> => {
    if (useMockData) {
      return withLatency({ dealId: dealData.id, deal: { ...dealData, watchId }, fallback: true });
    }

    const candidatePaths = [`/watches/${watchId}/search-now`, `/watches/${watchId}/search`, `/watches/${watchId}/refresh`];
    for (const path of candidatePaths) {
      try {
        const response = await apiClient.post<SearchNowResponseRaw | unknown>(path);
        const firstRawDeal =
          response && typeof response === "object" && "proposed_deals" in response
            ? (response as SearchNowResponseRaw).proposed_deals?.[0]
            : null;
        const dealId = readDealId(response) || (firstRawDeal ? readDealId(firstRawDeal) : "");
        const firstDeal =
          firstRawDeal ? mapDealPayloadToView(firstRawDeal, { dealId: dealId || "" }) : null;
        if (dealId) {
          return { dealId, deal: firstDeal ?? undefined };
        }

        if (
          response &&
          typeof response === "object" &&
          "proposed_deals" in response &&
          Array.isArray((response as SearchNowResponseRaw).proposed_deals) &&
          ((response as SearchNowResponseRaw).proposed_deals?.length ?? 0) === 0
        ) {
          throw new Error("No live inventory is available for this watch right now.");
        }

        return { queued: true };
      } catch (error) {
        if (error instanceof ApiError && [404, 405, 501].includes(error.status)) {
          continue;
        }

        throw error;
      }
    }

    const policy = await getRuntimePolicy();
    if (!policy.mockDataEnabled) {
      throw new Error(
        "Mock data is disabled and no live search endpoint is available for this backend yet.",
      );
    }

    return { dealId: dealData.id, deal: { ...dealData, watchId }, fallback: true };
  },

  approveDeal: async (payload: {
    dealId: string;
    watchId?: string;
    totpCode: string;
    masterKeyPassphrase: string;
  }): Promise<DealApprovalResult> => {
    if (useMockData) {
      return withLatency({
        dealId: payload.dealId,
        bookingId: "booking-ana",
        bookingStatus: "ticketed",
        provider: "ANA via Duffel",
        amount: dealData.price,
        confirmationNote: "Mock approval completed. The booking is now ticketed in the existing scaffold.",
      });
    }

    const body = {
      totp_code: payload.totpCode,
      master_key_passphrase: payload.masterKeyPassphrase,
    };
    const candidatePaths = [
      `/deals/${payload.dealId}/approve`,
      `/deals/${payload.dealId}/book`,
      payload.watchId ? `/watches/${payload.watchId}/deals/${payload.dealId}/approve` : "",
    ].filter(Boolean);
    const response = await tryCandidatePost<ApprovalResponseRaw | BookingRaw>(candidatePaths, body);

    if (!response) {
      throw new Error("The live approval endpoint is not available on this backend yet.");
    }

    if ("provider" in response || "amount_charged" in response) {
      const booking = response as BookingRaw;
      return {
        dealId: payload.dealId,
        bookingId: coerceString(booking.id) || undefined,
        bookingStatus: coerceString(booking.status) || undefined,
        provider: coerceString(booking.provider) || undefined,
        amount: formatMoneyValue(booking.amount_charged, booking.currency || "JPY") || undefined,
        confirmationNote: "Approval completed and the provider booking record was created.",
        cancellationStatus: coerceString(booking.cancellation?.status) || undefined,
        refundStatus: booking.cancellation?.refund_received
          ? "Refund received"
          : booking.cancellation?.refund_expected
            ? "Refund pending"
            : undefined,
        refundAmount:
          formatMoneyValue(booking.cancellation?.refund_received, booking.cancellation?.currency || "JPY") ||
          formatMoneyValue(booking.cancellation?.refund_expected, booking.cancellation?.currency || "JPY") ||
          undefined,
      };
    }

    const approval = response as ApprovalResponseRaw;
    const booking = approval.booking;
    const currency = booking?.currency || booking?.cancellation?.currency || "JPY";
    return {
      dealId: coerceString(approval.deal_id) || payload.dealId,
      bookingId: coerceString(approval.booking_id) || coerceString(booking?.id) || undefined,
      bookingStatus: coerceString(approval.status) || coerceString(booking?.status) || undefined,
      provider: coerceString(booking?.provider) || undefined,
      amount: formatMoneyValue(booking?.amount_charged, currency) || undefined,
      confirmationNote:
        coerceString(approval.detail) ||
        coerceString(approval.message) ||
        "Approval completed. Review bookings for ticketing, cancellation, and refund updates.",
      cancellationStatus:
        coerceString(approval.cancellation?.status) || coerceString(booking?.cancellation?.status) || undefined,
      refundStatus:
        approval.cancellation?.refund_received || booking?.cancellation?.refund_received
          ? "Refund received"
          : approval.cancellation?.refund_expected || booking?.cancellation?.refund_expected
            ? "Refund pending"
            : undefined,
      refundAmount:
        formatMoneyValue(approval.cancellation?.refund_received, approval.cancellation?.currency || currency) ||
        formatMoneyValue(approval.cancellation?.refund_expected, approval.cancellation?.currency || currency) ||
        formatMoneyValue(booking?.cancellation?.refund_received, booking?.cancellation?.currency || currency) ||
        formatMoneyValue(booking?.cancellation?.refund_expected, booking?.cancellation?.currency || currency) ||
        undefined,
    };
  },

  createApprovalToken: async (dealId: string) => {
    if (useMockData) {
      return withLatency({
        token: "mock-approval-token",
        expiresAt: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
      });
    }

    const response = await apiClient.post<{ token?: string | null; expires_at?: string | null }>(
      `/deals/${encodeURIComponent(dealId)}/approval-token`,
      {},
    );
    return {
      token: coerceString(response.token),
      expiresAt: coerceString(response.expires_at) || "",
    };
  },

  verifyApprovalToken: async (payload: { dealId: string; token: string }) => {
    if (useMockData) {
      return withLatency({
        valid: true,
        expiresAt: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
      });
    }
    const response = await apiClient.post<{ valid?: boolean | null; expires_at?: string | null }>(
      `/deals/${encodeURIComponent(payload.dealId)}/approval-token/verify`,
      { token: payload.token },
    );
    return {
      valid: Boolean(response.valid),
      expiresAt: coerceString(response.expires_at) || "",
    };
  },

  confirmDealIntent: async (payload: {
    dealId: string;
    token: string;
    totpCode: string;
  }): Promise<DealIntentResult> => {
    if (useMockData) {
      return withLatency({
        dealId: payload.dealId,
        status: "confirmed",
        detail: "Approval intent recorded. Booking remains a separate deterministic step in V3.",
      });
    }

    const response = await apiClient.post<ApprovalResponseRaw>(`/deals/${encodeURIComponent(payload.dealId)}/confirm-intent`, {
      token: payload.token,
      totp_code: payload.totpCode,
    });
    return {
      dealId: coerceString(response.deal_id) || payload.dealId,
      status: coerceString(response.status) || "confirmed",
      detail: coerceString(response.detail) || "Approval intent recorded.",
    };
  },

  rejectDeal: async (payload: { dealId: string; reason: string }): Promise<DealIntentResult> => {
    if (useMockData) {
      return withLatency({
        dealId: payload.dealId,
        status: "rejected",
        detail: "Rejection recorded. TRAMP will use this feedback to improve future proposals.",
        actionTaken: { reason: payload.reason },
      });
    }

    const response = await apiClient.post<ApprovalResponseRaw & { action_taken?: Record<string, unknown> | null }>(
      `/deals/${encodeURIComponent(payload.dealId)}/reject`,
      { reason: payload.reason },
    );
    return {
      dealId: coerceString(response.deal_id) || payload.dealId,
      status: coerceString(response.status) || "rejected",
      detail: coerceString(response.detail) || "Rejection recorded.",
      actionTaken: response.action_taken || undefined,
    };
  },

  getIntegrations: async (): Promise<IntegrationData> => {
    if (useMockData) {
      return withLatency({
        ...integrationData,
        runtimeSettings: {
          mockDataEnabled: true,
          liveInventoryAvailable: false,
          currentInventoryMode: "mock",
        },
      });
    }

    const response = await apiClient.get<AdminIntegrationsResponseRaw | IntegrationData>("/admin/integrations");
    return mapIntegrationsResponse(response);
  },

  testIntegrationConnection: async (providerKey: string): Promise<IntegrationTestResult> => {
    if (useMockData) {
      return withLatency({
        providerKey,
        status: "connected",
        message: "Demo connection passed. Live mode will surface backend availability and access failures directly.",
        testedAt: new Date().toISOString(),
      });
    }

    const encodedProviderKey = encodeURIComponent(providerKey);
    const response = await tryCandidatePost<AdminIntegrationTestRaw>([
      `/admin/integrations/${encodedProviderKey}/test`,
      `/admin/integrations/${encodedProviderKey}/test-connection`,
    ]);

    if (!response) {
      throw new Error("The live test-connection endpoint is not available on this backend yet.");
    }

    return mapIntegrationTestResponse(providerKey, response);
  },

  saveIntegration: async (payload: {
    key: string;
    enabled: boolean;
    environment: string;
    credentials: Record<string, unknown>;
    featureFlags: Record<string, boolean>;
    credentialProfileId?: string | null;
  }) => {
    if (useMockData) {
      await withLatency(null);
      return;
    }

    const encodedProviderKey = encodeURIComponent(payload.key);
    await apiClient.patch(`/admin/integrations/${encodedProviderKey}`, {
      enabled: payload.enabled,
      environment: payload.environment,
      credentials: payload.credentials,
      feature_flags: payload.featureFlags,
      credential_profile_id: payload.credentialProfileId ?? null,
    });
    clearRuntimePolicyCache();
  },

  saveCredentialProfile: async (payload: {
    id?: string;
    providerKey: string;
    label: string;
    credentials: Record<string, unknown>;
  }) => {
    if (useMockData) {
      await withLatency(null);
      return;
    }
    if (payload.id) {
      await apiClient.patch(`/admin/credential-profiles/${encodeURIComponent(payload.id)}`, {
        label: payload.label,
        credentials: payload.credentials,
      });
      return;
    }
    await apiClient.post("/admin/credential-profiles", {
      provider_key: payload.providerKey,
      label: payload.label,
      credentials: payload.credentials,
    });
  },

  deleteCredentialProfile: async (profileId: string) => {
    if (useMockData) {
      await withLatency(null);
      return;
    }
    await apiClient.delete(`/admin/credential-profiles/${encodeURIComponent(profileId)}`);
  },

  saveRuntimeSettings: async (payload: { mockDataEnabled: boolean }) => {
    if (useMockData) {
      await withLatency(null);
      return;
    }
    await apiClient.patch("/admin/runtime-settings", {
      mock_data_enabled: payload.mockDataEnabled,
    });
    clearRuntimePolicyCache();
  },

  triggerBookingDisruption: async (bookingId: string) => {
    if (useMockData) {
      await withLatency(null);
      return;
    }
    await apiClient.post(`/bookings/${encodeURIComponent(bookingId)}/disruptions/test`, {});
  },

  resolveDisruption: async (disruptionId: string) => {
    if (useMockData) {
      await withLatency(null);
      return;
    }
    await apiClient.post(`/disruptions/${encodeURIComponent(disruptionId)}/resolve`, {});
  },

  startSignup: async (payload: { email: string; password: string }): Promise<SignupStartSession> => {
    if (useMockData) {
      return withLatency({
        email: payload.email,
        pendingToken: "mock-pending-token",
        totpSecret: "JBSWY3DPEHPK3PXP",
        provisioningUri:
          "otpauth://totp/TRAMP:demo@example.com?secret=JBSWY3DPEHPK3PXP&issuer=TRAMP",
        manualEntryKey: "JBSWY3DPEHPK3PXP",
      });
    }

    const response = await apiClient.post<SignupStartResponseRaw>("/auth/signup/start", payload);
    return {
      email: payload.email,
      pendingToken: response.pending_token,
      totpSecret: response.totp_secret,
      provisioningUri: response.provisioning_uri,
      manualEntryKey: response.manual_entry_key,
    };
  },

  completeSignup: async (payload: { pendingToken: string; totpCode: string }) => {
    if (useMockData) {
      return withLatency({
        user: {
          id: "mock-user",
          email: "demo@example.com",
          role: "admin",
          onboardingCompleted: false,
          defaultNotifyChannel: "email",
          telegramChatId: null,
          totpEnabled: true,
        },
      });
    }

    const response = await apiClient.post<AuthResponseRaw>("/auth/signup/complete", {
      pending_token: payload.pendingToken,
      totp_code: payload.totpCode,
    });

    return {
      user: mapCurrentUser(response.user),
    };
  },

  login: async (payload: { email: string; password: string; totpCode?: string }) => {
    if (useMockData) {
      return withLatency({
        user: {
          id: "mock-user",
          email: payload.email,
          role: "admin",
          onboardingCompleted: false,
          defaultNotifyChannel: "email",
          telegramChatId: null,
          totpEnabled: Boolean(payload.totpCode),
        },
      });
    }

    const response = await apiClient.post<AuthResponseRaw>("/auth/login", {
      email: payload.email,
      password: payload.password,
      totp_code: payload.totpCode || undefined,
    });

    return {
      user: mapCurrentUser(response.user),
    };
  },

  logout: async () => {
    if (useMockData) {
      await withLatency(null);
      return;
    }

    await apiClient.post("/auth/logout", {});
  },

  startTotpEnrollment: async (): Promise<TotpEnrollmentSession> => {
    if (useMockData) {
      return withLatency({
        pendingToken: "mock-totp-enroll",
        totpSecret: "JBSWY3DPEHPK3PXP",
        provisioningUri: "otpauth://totp/TRAMP:demo@example.com?secret=JBSWY3DPEHPK3PXP&issuer=TRAMP",
        manualEntryKey: "JBSWY3DPEHPK3PXP",
      });
    }

    const response = await apiClient.post<SignupStartResponseRaw>("/auth/totp/enroll/start", {});
    return {
      pendingToken: response.pending_token,
      totpSecret: response.totp_secret,
      provisioningUri: response.provisioning_uri,
      manualEntryKey: response.manual_entry_key,
    };
  },

  completeTotpEnrollment: async (payload: { pendingToken: string; totpCode: string }) => {
    if (useMockData) {
      return withLatency({
        user: {
          id: "mock-user",
          email: "demo@example.com",
          role: "admin",
          onboardingCompleted: false,
          defaultNotifyChannel: "email",
          telegramChatId: null,
          totpEnabled: true,
        },
      });
    }

    const response = await apiClient.post<AuthResponseRaw>("/auth/totp/enroll/complete", {
      pending_token: payload.pendingToken,
      totp_code: payload.totpCode,
    });

    return {
      user: mapCurrentUser(response.user),
    };
  },

  saveTraveler: async (traveler: Omit<TravelerProfile, "id"> & { id?: string }) => {
    const payload = {
      traveler_relationship: traveler.relationship,
      display_name: traveler.displayName,
      legal_first_name: traveler.legalFirstName,
      legal_last_name: traveler.legalLastName,
      dob: traveler.dob,
      nationality: traveler.nationality,
      residency_country: maybe(traveler.residencyCountry),
      passport_number: maybe(traveler.passportNumber),
      passport_country: maybe(traveler.passportCountry),
      passport_expiry: maybe(traveler.passportExpiry),
      known_traveler_number: maybe(traveler.knownTravelerNumber),
      redress_number: maybe(traveler.redressNumber),
      seat_pref: traveler.seatPreference,
      meal_pref: maybe(traveler.mealPreference),
      accessibility_needs: maybe(traveler.accessibilityNeeds),
      infant_on_lap: traveler.infantOnLap,
      loyalty_programs: traveler.loyaltyPrograms.map((program) => ({
        program_type: program.programType || "airline",
        program_code: program.programCode.trim().toUpperCase(),
        account_number: program.accountNumber.trim(),
        alliance: maybe(program.alliance),
        status_tier: maybe(program.statusTier),
        is_favorite: program.isFavorite,
      })),
    };

    if (traveler.id) {
      const response = await apiClient.patch<TravelerRaw>(`/profile/travelers/${traveler.id}`, payload);
      return mapTravelerProfile(response);
    }
    const response = await apiClient.post<TravelerRaw>("/profile/travelers", payload);
    return mapTravelerProfile(response);
  },

  deleteTraveler: async (travelerId: string) => {
    await apiClient.delete(`/profile/travelers/${travelerId}`);
  },

  saveTravelerGroup: async (group: { id?: string; name: string; travelerIds: string[] }) => {
    if (group.id) {
      await apiClient.patch(`/profile/traveler-groups/${encodeURIComponent(group.id)}`, {
        name: group.name,
        traveler_ids: group.travelerIds,
      });
      return;
    }
    await apiClient.post(`/profile/traveler-groups`, {
      name: group.name,
      traveler_ids: group.travelerIds,
    });
  },

  deleteTravelerGroup: async (groupId: string) => {
    await apiClient.delete(`/profile/traveler-groups/${encodeURIComponent(groupId)}`);
  },

  completeOnboarding: async () => {
    await apiClient.post("/profile/onboarding/complete");
  },

  savePreferences: async (preferences: UserPreferencesProfile) => {
    await apiClient.put("/profile/preferences", {
      home_airports: preferences.homeAirports,
      default_cabin: preferences.defaultCabin,
      default_luxury_vs_savings: preferences.defaultLuxuryVsSavings,
      preferred_alliances: preferences.preferredAlliances,
      preferred_airlines: preferences.preferredAirlines,
      avoided_airlines: preferences.avoidedAirlines,
      preferred_hotel_brands: preferences.preferredHotelBrands,
      avoided_hotel_brands: preferences.avoidedHotelBrands,
      quiet_hours_start: maybe(preferences.quietHoursStart),
      quiet_hours_end: maybe(preferences.quietHoursEnd),
      default_notify_channel: preferences.defaultNotifyChannel,
      avoid_redeye: preferences.avoidRedeye,
      prefer_refundable: preferences.preferRefundable,
      seat_auto_select: preferences.seatAutoSelect,
      default_hotel_min_rating: preferences.defaultHotelMinRating
        ? Number(preferences.defaultHotelMinRating)
        : undefined,
      default_max_layover_minutes: preferences.maxLayoverMinutes
        ? Number(preferences.maxLayoverMinutes)
        : undefined,
      default_min_connection_minutes: preferences.minConnectionMinutes
        ? Number(preferences.minConnectionMinutes)
        : undefined,
    });
  },

  saveUserSettings: async (settings: {
    defaultNotifyChannel: string;
    telegramChatId: string;
  }) => {
    if (useMockData) {
      return withLatency(undefined);
    }

    await apiClient.patch("/profile/settings", {
      default_notify_channel: settings.defaultNotifyChannel,
      telegram_chat_id: maybe(settings.telegramChatId),
    });
  },

  savePaymentMethod: async (paymentMethod: Omit<PaymentMethodProfile, "id"> & { id?: string }) => {
    const billingAddress =
      paymentMethod.billingAddressLine1 &&
      paymentMethod.billingAddressCity &&
      paymentMethod.billingAddressPostalCode &&
      paymentMethod.billingCountry
        ? {
            line1: paymentMethod.billingAddressLine1,
            city: paymentMethod.billingAddressCity,
            postal_code: paymentMethod.billingAddressPostalCode,
            country: paymentMethod.billingCountry,
          }
        : undefined;

    if (paymentMethod.id) {
      const payload: Record<string, unknown> = {
        label: paymentMethod.label,
        brand: maybe(paymentMethod.brand),
        cardholder_name: maybe(paymentMethod.cardholderName),
        exp_month: paymentMethod.expMonth ? Number(paymentMethod.expMonth) : undefined,
        exp_year: paymentMethod.expYear ? Number(paymentMethod.expYear) : undefined,
        provider_token: maybe(paymentMethod.providerToken),
        billing_address: billingAddress,
      };
      if (paymentMethod.cardNumber.trim()) {
        payload.card_number = paymentMethod.cardNumber;
      }
      await apiClient.patch(`/profile/payment-methods/${paymentMethod.id}`, payload);
      return;
    }

    if (!paymentMethod.cardNumber.trim()) {
      throw new Error("Card number is required for a new payment method.");
    }

    await apiClient.post("/profile/payment-methods", {
      label: paymentMethod.label,
      brand: maybe(paymentMethod.brand),
      cardholder_name: paymentMethod.cardholderName,
      card_number: paymentMethod.cardNumber,
      exp_month: Number(paymentMethod.expMonth),
      exp_year: Number(paymentMethod.expYear),
      provider_token: maybe(paymentMethod.providerToken),
      billing_address: billingAddress,
    });
  },

  deletePaymentMethod: async (paymentMethodId: string) => {
    await apiClient.delete(`/profile/payment-methods/${paymentMethodId}`);
  },

  saveTemplate: async (template: Omit<TripTemplateProfile, "id"> & { id?: string }) => {
    const watchPayload = {
      travelerGroup: template.travelerGroup,
      origin: template.origin,
      destination: template.destination,
      flightBudgetMax: template.flightBudgetMax,
      hotelBudgetPerNightMax: template.hotelBudgetPerNightMax,
      notes: template.notes,
    };

    if (template.id) {
      await apiClient.patch(`/profile/trip-templates/${template.id}`, {
        name: template.name,
        watch_payload: watchPayload,
      });
      return;
    }

    await apiClient.post("/profile/trip-templates", {
      name: template.name,
      watch_payload: watchPayload,
    });
  },

  deleteTemplate: async (templateId: string) => {
    await apiClient.delete(`/profile/trip-templates/${templateId}`);
  },
};
