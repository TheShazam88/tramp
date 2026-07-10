import { afterEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "@/api/client";
import { travelWatchApi } from "@/api/travelWatchApi";

describe("travelWatchApi booking execution", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("maps the top-level profile stamp balance", async () => {
    const get = vi.spyOn(apiClient, "get").mockImplementation(async (path) => {
      if (path === "/auth/me") {
        return {
          user: {
            id: "user-1",
            email: "traveler@example.com",
            role: "user",
            onboarding_completed: true,
            default_notify_channel: "email",
            telegram_chat_id: null,
            totp_enabled: true,
          },
        } as never;
      }
      if (path === "/profile") {
        return {
          settings: {
            id: "user-1",
            email: "traveler@example.com",
            role: "user",
            onboarding_completed: true,
            default_notify_channel: "email",
            telegram_chat_id: null,
            totp_enabled: true,
          },
          preferences: {
            home_airports: [],
            default_cabin: "business",
            default_luxury_vs_savings: 0.5,
            preferred_alliances: [],
            preferred_airlines: [],
            avoided_airlines: [],
            preferred_hotel_brands: [],
            avoided_hotel_brands: [],
            quiet_hours_start: null,
            quiet_hours_end: null,
            default_notify_channel: "email",
            avoid_redeye: false,
            prefer_refundable: true,
            seat_auto_select: false,
            default_hotel_min_rating: null,
            default_max_layover_minutes: null,
            default_min_connection_minutes: null,
          },
          travelers: [],
          traveler_groups: [],
          payment_methods: [],
          trip_templates: [],
          tramp_stamp_balance: 7,
        } as never;
      }
      throw new Error(`Unexpected API path: ${path}`);
    });

    const workspace = await travelWatchApi.getProfileWorkspace();

    expect(get).toHaveBeenCalledWith("/profile");
    expect(workspace.trampStampBalance).toBe(7);
  });

  it("maps provider acquisition guides from the admin response", async () => {
    vi.spyOn(apiClient, "get").mockResolvedValue({
      categories: [],
      providers: [
        {
          key: "flights_amadeus",
          label: "Flights · Amadeus",
          category: "flights",
          enabled: true,
          environment: "test",
          credentials_masked: {},
          credential_fields: [],
          feature_flags: {},
          feature_flag_definitions: [],
          guide: {
            signup_url: "https://developers.amadeus.com/quick-start",
            application_url: "https://developers.amadeus.com/production",
            account_requirements: ["Developer account"],
            steps: ["Create an app", "Copy the test credentials"],
            environment_notes: ["Use test credentials first"],
            enables: ["Amadeus credential configuration"],
          },
        },
      ],
      credential_profiles: [],
      feature_flags: [],
      health_notes: [],
      runtime_settings: {
        mock_data_enabled: true,
        live_inventory_available: false,
        current_inventory_mode: "mock",
      },
    } as never);

    const integrations = await travelWatchApi.getIntegrations();

    expect(integrations.providers[0].guide).toEqual({
      signupUrl: "https://developers.amadeus.com/quick-start",
      applicationUrl: "https://developers.amadeus.com/production",
      accountRequirements: ["Developer account"],
      steps: ["Create an app", "Copy the test credentials"],
      environmentNotes: ["Use test credentials first"],
      enables: ["Amadeus credential configuration"],
    });
  });

  it("posts the caller-owned approval token and idempotency key unchanged", async () => {
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      id: "booking-1",
      deal_id: "deal-1",
      provider: "duffel",
      status: "ticketed",
      amount_charged: "640.00",
      currency: "USD",
      cancellation: null,
      tramp_stamps_awarded: 1,
      tramp_stamp_balance: 4,
    } as never);

    await travelWatchApi.bookDeal({
      dealId: "deal-1",
      approvalToken: "linked-or-minted-token",
      paymentMethodId: "payment-1",
      totpCode: "123456",
      masterKeyPassphrase: "",
      idempotencyKey: "00000000-0000-4000-8000-000000000001",
    });

    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith("/bookings/approve", {
      deal_id: "deal-1",
      approval_token: "linked-or-minted-token",
      totp_code: "123456",
      master_key_passphrase: undefined,
      payment_method_id: "payment-1",
      idempotency_key: "00000000-0000-4000-8000-000000000001",
    });
  });

  it("maps the authenticated attempt reconciliation response", async () => {
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      idempotency_key: "attempt-key-123",
      deal_id: "deal-1",
      payment_method_id: "payment-1",
      status: "booked",
      code: "booked",
      message: "Booking confirmed from the saved booking record.",
      safe_to_retry: false,
      recovery_required: true,
      started_at: "2030-01-01T00:00:00Z",
      finished_at: "2030-01-01T00:01:00Z",
      booking: {
          id: "booking-1",
          deal_id: "deal-1",
          provider: "duffel",
          status: "ticketed",
          amount_charged: "640.00",
          currency: "USD",
          cancellation: null,
          tramp_stamps_awarded: 1,
          tramp_stamp_balance: 4,
      },
    } as never);

    const attempt = await travelWatchApi.reconcileBookingAttempt("attempt-key-123");

    expect(get).toHaveBeenCalledWith("/bookings/attempts/attempt-key-123");
    expect(attempt).toEqual(
      expect.objectContaining({
        idempotencyKey: "attempt-key-123",
        dealId: "deal-1",
        paymentMethodId: "payment-1",
        code: "booked",
        safeToRetry: false,
        recoveryRequired: true,
        booking: expect.objectContaining({
          bookingId: "booking-1",
          trampStampsAwarded: 1,
          trampStampBalance: 4,
        }),
      }),
    );
  });
});
