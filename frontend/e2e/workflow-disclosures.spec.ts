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
  const quietHours = {
    quiet_hours_start: null as string | null,
    quiet_hours_end: null as string | null,
    quiet_hours_timezone: null as string | null,
  };

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
            quiet_hours_start: quietHours.quiet_hours_start,
            quiet_hours_end: quietHours.quiet_hours_end,
            quiet_hours_timezone: quietHours.quiet_hours_timezone,
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
          tramp_stamp_balance: 1,
          tramp_stamp_history: [
            {
              id: "stamp-1",
              booking_id: "booking-1",
              awarded_at: "2026-10-06T01:00:00Z",
              provider: "Amadeus",
              route: "HND to SIN",
              amount: 1,
            },
          ],
        },
      });
      return;
    }
    if (pathname === "/api/v1/deals/deal-1") {
      await route.fulfill({
        json: {
          id: "deal-1",
          watch_id: "watch-1",
          route: "HND to SIN",
          currency: "JPY",
          total_price: 118400,
          source: "amadeus",
          summary_text: "Live fare",
          status: "proposed",
        },
      });
      return;
    }
    if (pathname === "/api/v1/deals/deal-1/timeline") {
      await route.fulfill({ status: 404, json: { detail: "No timeline yet." } });
      return;
    }
    if (pathname === "/api/v1/watches/dashboard") {
      await route.fulfill({
        json: {
          highlights: [{ label: "Active watches", value: "1", note: "One trip is being watched." }],
          watches: [
            {
              id: "watch-1",
              route: "HND to SIN",
              dates: "12 to 19 Apr",
              travelers: "Alex",
              cabin: "Business",
              status: "active",
              framing: "best_value",
              best_now: "¥118,400",
              insight: "Stored fare",
              cadence: "Daily refresh",
              last_searched_at: "2026-10-06T01:00:00Z",
            },
            {
              id: "watch-2",
              route: "HND to DPS",
              dates: "Dates flexible",
              travelers: "Alex",
              cabin: "Economy",
              status: "paused",
              cadence: "Hourly refresh",
            },
          ],
        },
      });
      return;
    }
    if (pathname === "/api/v1/profile/preferences" && route.request().method() === "PUT") {
      const body = route.request().postDataJSON() as {
        quiet_hours_start: string | null;
        quiet_hours_end: string | null;
        quiet_hours_timezone: string | null;
      };
      quietHours.quiet_hours_start = body.quiet_hours_start;
      quietHours.quiet_hours_end = body.quiet_hours_end;
      quietHours.quiet_hours_timezone = body.quiet_hours_timezone;
      await route.fulfill({ json: { ok: true } });
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
    await expect(page.getByText("Watch", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0);
    await expect(page.getByText(/Screen \d/)).toHaveCount(0);

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

test("trip, household, and admin navigation use the live workspace", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await mockWorkflowApi(page);
  await page.goto("/watches");

  await expect(page.getByText("Trips", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "HND to SIN" })).toBeVisible();
  await expect(page.getByText(/Last search/)).toBeVisible();
  await expect(page.getByText(/No search yet/)).toBeVisible();
  await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0);
  await expect(page.getByText("Live provider inventory is active.")).toBeVisible();

  await page.goto("/deals/deal-1");
  await expect(page.getByText("Deal", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "HND to SIN" })).toBeVisible();

  await page.goto("/profile");
  await expect(page.getByText("Household", { exact: true })).toBeVisible();
  await expect(page.getByText("HND to SIN")).toBeVisible();
  await expect(page.getByText(/Amadeus/)).toBeVisible();
  await expect(page.getByText("1 stamp")).toBeVisible();
  await expect(page.getByText("Managed by an admin")).toBeVisible();
  await expect(page.getByText("Not set").first()).toBeVisible();

  await page.getByRole("link", { name: "Open presets page" }).click();
  await expect(page.getByLabel("Quiet hours timezone")).toBeVisible();
  await page.getByLabel("Quiet hours start").fill("22:00");
  await page.getByLabel("Quiet hours end").fill("07:00");
  await page.getByLabel("Quiet hours timezone").selectOption("Asia/Tokyo");
  const saved = page.waitForRequest(
    (request) =>
      request.method() === "PUT" && request.url().includes("/api/v1/profile/preferences"),
  );
  await page.getByRole("button", { name: "Save watch presets" }).click();
  expect((await saved).postDataJSON()).toMatchObject({
    quiet_hours_start: "22:00",
    quiet_hours_end: "07:00",
    quiet_hours_timezone: "Asia/Tokyo",
  });

  await page.goto("/profile");
  await expect(page.getByText("22:00 - 07:00 Asia/Tokyo")).toBeVisible();

  await page.goto("/admin/integrations");
  await expect(page.getByText("Trips", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Admin" })).toHaveCount(0);
});
