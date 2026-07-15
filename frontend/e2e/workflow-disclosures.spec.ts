import { expect, test, type Page } from "@playwright/test";

const user = {
  id: "user-1",
  email: "traveler@example.com",
  role: "user",
  onboarding_completed: true,
  default_notify_channel: "email",
  telegram_chat_id: null,
  totp_enabled: true,
};

async function mockWorkflowApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;

    if (pathname === "/api/v1/auth/me") {
      await route.fulfill({ json: { user } });
      return;
    }
    if (pathname === "/api/v1/profile") {
      await route.fulfill({
        json: {
          settings: user,
          preferences: {
            home_airports: ["HND", "NRT"],
            default_cabin: "business",
            default_luxury_vs_savings: 0.58,
            preferred_alliances: ["Star Alliance"],
            preferred_airlines: ["ANA"],
            avoided_airlines: [],
            preferred_hotel_brands: [],
            avoided_hotel_brands: [],
            quiet_hours_start: null,
            quiet_hours_end: null,
            default_notify_channel: "email",
            avoid_redeye: false,
            prefer_refundable: true,
            seat_auto_select: false,
            default_hotel_min_rating: 4.5,
            default_max_layover_minutes: 180,
            default_min_connection_minutes: 75,
          },
          travelers: [],
          traveler_groups: [],
          payment_methods: [],
          trip_templates: [],
          tramp_stamp_balance: 0,
        },
      });
      return;
    }
    if (pathname === "/api/v1/health") {
      await route.fulfill({
        json: {
          status: "ok",
          environment: "test",
          app: "TRAMP",
          checks: {
            mock_data_enabled: false,
            live_inventory_available: true,
            inventory_mode: "live",
          },
        },
      });
      return;
    }
    if (pathname === "/api/v1/bookings") {
      await route.fulfill({
        json: [
          {
            id: "booking-1",
            deal_id: "deal-1",
            watch_id: "watch-1",
            provider: "Duffel",
            provider_booking_ref: "DUF-123",
            status: "ticketed",
            amount_charged: 118400,
            currency: "JPY",
            title: "Tokyo to Singapore",
            when: "12 to 19 Apr",
            disruptions: [
              {
                id: "disruption-1",
                type: "delay",
                status: "open",
              },
            ],
          },
          {
            id: "booking-2",
            deal_id: "deal-2",
            watch_id: "watch-2",
            provider: "Hotelbeds",
            provider_booking_ref: "HTL-456",
            status: "ticketed",
            amount_charged: 420000,
            currency: "JPY",
            title: "Family stay in Bali",
            when: "March flexible",
            disruptions: [],
          },
        ],
      });
      return;
    }

    await route.fulfill({
      status: 404,
      json: { detail: "Unhandled browser test route." },
    });
  });
}

for (const viewport of [
  { name: "mobile", width: 320, height: 700 },
  { name: "desktop", width: 1280, height: 900 },
]) {
  test(`${viewport.name} watch and booking disclosures stay usable`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await mockWorkflowApi(page);
    await page.goto("/watches/new");

    const flightDetails = page.getByRole("group", {
      name: "Advanced flight preferences",
    });
    const pricingDetails = page.getByRole("group", {
      name: "Pricing and monitoring controls",
    });
    await expect(flightDetails).not.toHaveAttribute("open");
    await expect(pricingDetails).not.toHaveAttribute("open");

    const flightSummary = flightDetails.getByLabel(
      "Advanced flight preferences toggle",
    );
    await flightSummary.focus();
    await page.keyboard.press("Enter");
    await expect(flightDetails).toHaveAttribute("open", "");

    await pricingDetails
      .getByLabel("Pricing and monitoring controls toggle")
      .click();
    const lastAdvancedField = page.getByLabel("Late-booking urgency at");
    await lastAdvancedField.scrollIntoViewIfNeeded();
    await expect(lastAdvancedField).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(viewport.width);

    await page.goto("/bookings");
    const bookingCards = page.getByRole("article");
    await expect(bookingCards).toHaveCount(2);
    for (let index = 0; index < 2; index += 1) {
      const reviewAction = bookingCards
        .nth(index)
        .getByRole("link", { name: "Open deal review" });
      await expect(reviewAction).toHaveCount(1);
      await expect(reviewAction).toBeVisible();
    }

    const bookingCard = page.getByRole("article", {
      name: "Tokyo to Singapore",
    });
    const localTools = bookingCard.getByRole("group", {
      name: "Local test tools for Tokyo to Singapore",
    });
    await expect(localTools).not.toHaveAttribute("open");
    await localTools
      .getByLabel("Local test tools toggle for Tokyo to Singapore")
      .click();
    await expect(
      bookingCard.getByRole("button", { name: "Simulate disruption" }),
    ).toBeVisible();
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(viewport.width);
  });
}
