export type WatchStatus = "active" | "paused" | "fulfilled";
export type IntegrationState = "connected" | "attention" | "disabled" | "not_set";
export type IntegrationEnvironment = "test" | "live" | "off";

export interface ReadinessResolution {
  code: string;
  label: string;
  path: string;
}

export interface ReadinessState {
  score: number;
  label: string;
  blockers: string[];
  warnings: string[];
  resolutions: ReadinessResolution[];
}

export interface SemanticBadge {
  label: string;
  tone: "value" | "luxury" | "alert" | "muted";
}

export interface CtaAction {
  key: string;
  label: string;
  tone: "primary" | "secondary" | "ghost";
  enabled: boolean;
  detail?: string;
}

export interface WatchSummary {
  id: string;
  route: string;
  dates: string;
  travelers: string;
  cabin: string;
  status: WatchStatus;
  framing: string;
  bestNow: string;
  insight: string;
  cadence: string;
  searchLabel?: string;
  currentDealId?: string;
  currentDealStatus?: string;
  readiness?: ReadinessState;
  badges: SemanticBadge[];
  ctaActions: CtaAction[];
}

export interface DashboardData {
  highlights: Array<{
    label: string;
    value: string;
    note: string;
  }>;
  watches: WatchSummary[];
}

export interface OnboardingData {
  progressLabel: string;
  steps: Array<{
    id: string;
    title: string;
    detail: string;
    complete: boolean;
  }>;
  callouts: string[];
}

export interface WatchDraft {
  id?: string;
  title: string;
  travelerOptions: Array<{
    id: string;
    displayName: string;
    relationship: string;
  }>;
  status: WatchStatus;
  travelerGroups: Array<{
    id: string;
    name: string;
    travelerIds: string[];
  }>;
  selectedTravelerIds: string[];
  selectedGroupId: string;
  selectedGroup: string;
  tripMode: string;
  origins: string;
  destination: string;
  destinationMode: "fixed" | "flexible";
  flexibleRegion: string;
  flexibleTheme: string;
  departDateFrom: string;
  departDateTo: string;
  returnDateFrom: string;
  returnDateTo: string;
  tripMinNights: string;
  tripMaxNights: string;
  cabinClass: string;
  maxStops: string;
  maxLayoverMinutes: string;
  minConnectionMinutes: string;
  preferredAirlines: string;
  preferredAlliances: string;
  budgetCurrency: string;
  flightBudget: string;
  hotelBudget: string;
  luxuryVsSavings: number;
  hotelMinRating: string;
  preferRefundable: boolean;
  avoidRedeye: boolean;
  includeAirbnb: boolean;
  wantCar: boolean;
  notifyChannel: string;
  refreshInterval: string;
  idealPrice: string;
  glideStartDays: string;
  glideEndDays: string;
}

export interface DealData {
  id: string;
  watchId?: string;
  route: string;
  cabin: string;
  price: string;
  wasPrice: string;
  context: string;
  breakdown: string;
  score: number;
  details: string[];
  loyaltyPlan: string[];
  warnings: string[];
  coverage: string[];
  provider?: string;
  expiresAt?: string;
  dealStatus?: string;
  bookingStatus?: string;
  cancellationStatus?: string;
  refundStatus?: string;
  refundAmount?: string;
  approvalDetail?: string;
  readiness?: ReadinessState;
  badges: SemanticBadge[];
  ctaActions: CtaAction[];
  timeline?: DealTimeline;
}

export interface BookingSummary {
  id: string;
  title: string;
  when: string;
  status: string;
  amount: string;
  provider: string;
  actions: string[];
  dealId?: string;
  watchId?: string;
  bookingStatus?: string;
  cancellationStatus?: string;
  refundStatus?: string;
  refundAmount?: string;
  providerReference?: string;
  statusDetail?: string;
  approvalDetail?: string;
  bookedAt?: string;
  calendarDetail?: string;
  notificationStatuses?: string[];
  disruptionStatuses?: string[];
  disruptions?: Array<{
    id: string;
    status: string;
    type: string;
  }>;
}

export interface DealViewData {
  deal: DealData;
  source: "live" | "watch-derived" | "mock";
  fallbackNote?: string;
  approvalAvailable: boolean;
}

export interface BookingsViewData {
  items: BookingSummary[];
  source: "live" | "mock";
  fallbackNote?: string;
}

export interface DealApprovalResult {
  dealId: string;
  bookingId?: string;
  bookingStatus?: string;
  provider?: string;
  amount?: string;
  confirmationNote: string;
  cancellationStatus?: string;
  refundStatus?: string;
  refundAmount?: string;
  trampStampsAwarded: number;
  trampStampBalance: number;
}

export interface BookingAttemptReconciliation {
  idempotencyKey: string;
  dealId: string;
  paymentMethodId: string;
  status: string;
  code: string;
  message: string;
  safeToRetry: boolean;
  recoveryRequired: boolean;
  booking: DealApprovalResult | null;
  startedAt: string;
  finishedAt?: string;
}

export interface BookDealRequest {
  dealId: string;
  approvalToken: string;
  paymentMethodId: string;
  totpCode: string;
  masterKeyPassphrase: string;
  idempotencyKey: string;
}

export interface DealIntentResult {
  dealId: string;
  status: string;
  detail: string;
  actionTaken?: Record<string, unknown>;
}

export interface ProfileData {
  travelers: Array<{
    name: string;
    meta: string;
    notes: string[];
  }>;
  groups: string[];
  preferences: Array<{
    label: string;
    value: string;
  }>;
  paymentSummary: string;
  guardrails: Array<{
    label: string;
    value: string;
  }>;
}

export interface CurrentUser {
  id: string;
  email: string;
  role: string;
  onboardingCompleted: boolean;
  defaultNotifyChannel: string;
  telegramChatId: string | null;
  totpEnabled: boolean;
}

export interface SignupStartSession {
  email: string;
  pendingToken: string;
  totpSecret: string;
  provisioningUri: string;
  manualEntryKey: string;
}

export interface TotpEnrollmentSession {
  pendingToken: string;
  totpSecret: string;
  provisioningUri: string;
  manualEntryKey: string;
}

export interface LoyaltyProgramProfile {
  programType: string;
  programCode: string;
  accountNumber: string;
  alliance: string;
  statusTier: string;
  isFavorite: boolean;
}

export interface TravelerProfile {
  id: string;
  displayName: string;
  relationship: string;
  legalFirstName: string;
  legalLastName: string;
  dob: string;
  nationality: string;
  residencyCountry: string;
  passportNumber: string;
  passportCountry: string;
  passportExpiry: string;
  knownTravelerNumber: string;
  redressNumber: string;
  seatPreference: string;
  mealPreference: string;
  loyaltyProgramCode: string;
  loyaltyAccountNumber: string;
  loyaltyAlliance: string;
  loyaltyStatusTier: string;
  preferredEarningForAlliance: boolean;
  loyaltyPrograms: LoyaltyProgramProfile[];
  accessibilityNeeds: string;
  infantOnLap: boolean;
}

export interface UserPreferencesProfile {
  homeAirports: string[];
  defaultCabin: string;
  defaultLuxuryVsSavings: number;
  preferredAlliances: string[];
  preferredAirlines: string[];
  avoidedAirlines: string[];
  preferredHotelBrands: string[];
  avoidedHotelBrands: string[];
  quietHoursStart: string;
  quietHoursEnd: string;
  defaultNotifyChannel: string;
  avoidRedeye: boolean;
  preferRefundable: boolean;
  seatAutoSelect: boolean;
  defaultHotelMinRating: string;
  maxLayoverMinutes: string;
  minConnectionMinutes: string;
}

export interface PaymentMethodProfile {
  id: string;
  label: string;
  brand: string;
  cardholderName: string;
  cardNumber: string;
  last4: string;
  expMonth: string;
  expYear: string;
  providerToken: string;
  billingAddressLine1: string;
  billingAddressCity: string;
  billingAddressPostalCode: string;
  billingCountry: string;
}

export interface TripTemplateProfile {
  id: string;
  name: string;
  travelerGroup: string;
  origin: string;
  destination: string;
  flightBudgetMax: string;
  hotelBudgetPerNightMax: string;
  notes: string;
}

export interface ProfileWorkspace {
  currentUser: CurrentUser | null;
  travelers: TravelerProfile[];
  travelerGroups: string[];
  travelerGroupOptions: Array<{
    id: string;
    name: string;
    travelerIds: string[];
  }>;
  preferences: UserPreferencesProfile;
  paymentMethods: PaymentMethodProfile[];
  templates: TripTemplateProfile[];
  householdSummary: {
    travelerCount: number;
    travelerGroupCount: number;
    paymentMethodCount: number;
    templateCount: number;
    passportGapCount: number;
    hasSelfTraveler: boolean;
    hasPaymentMethod: boolean;
    totpEnabled: boolean;
    setupWarnings: string[];
    readinessLabel: string;
  };
}

export interface DealTimelinePoint {
  observedAt: string;
  price: string;
  rawPrice: number;
  label: string;
  source: string;
  percentile?: number;
}

export interface DealTimeline {
  currentPrice?: string;
  targetPrice?: string;
  glideLimit?: string;
  trendSummary: string;
  points: DealTimelinePoint[];
}

export interface IntegrationFlag {
  label: string;
  enabled: boolean;
}

export interface IntegrationProvider {
  key: string;
  name: string;
  category: string;
  providerKey?: string;
  supportsSharedProfile: boolean;
  compatibleProfileProviderKeys: string[];
  environment: IntegrationEnvironment | string;
  status: IntegrationState;
  detail: string;
  enabled: boolean;
  credentialSource?: string;
  updatedAt?: string;
  updatedBy?: string;
  validationHelp?: string;
  credentialProfileId?: string;
  credentialProfileLabel?: string;
  credentialState: {
    configured: boolean;
    label: string;
    maskedValue?: string;
  };
  credentialFields: Array<{
    key: string;
    label: string;
    placeholder?: string;
    helpText?: string;
    sensitive?: boolean;
  }>;
  credentialsMasked?: Record<string, unknown>;
  featureFlags: IntegrationFlag[];
  featureFlagDefinitions: Array<{
    key: string;
    label: string;
    defaultEnabled?: boolean;
    description?: string;
  }>;
}

export interface IntegrationCredentialProfile {
  id: string;
  providerKey: string;
  label: string;
  credentialsMasked: Record<string, unknown>;
  updatedAt?: string;
  updatedBy?: string;
  usageIntegrationKeys: string[];
}

export interface IntegrationCategory {
  id: string;
  title: string;
  description: string;
}

export interface IntegrationData {
  categories: IntegrationCategory[];
  providers: IntegrationProvider[];
  credentialProfiles: IntegrationCredentialProfile[];
  featureFlags: IntegrationFlag[];
  healthNotes: string[];
  runtimeSettings: {
    mockDataEnabled: boolean;
    liveInventoryAvailable: boolean;
    currentInventoryMode: "mock" | "live" | "empty";
  };
}

export interface IntegrationTestResult {
  providerKey: string;
  status: "connected" | "attention";
  message: string;
  testedAt?: string;
}
