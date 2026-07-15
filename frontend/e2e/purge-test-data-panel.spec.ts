import { expect, test, type Page } from "@playwright/test";

const user = {
  id: "admin-1",
  email: "admin@example.com",
  role: "admin",
  onboarding_completed: true,
  default_notify_channel: "email",
  telegram_chat_id: null,
  totp_enabled: true,
};

const previewCounts = {
  audit_log: 1,
  booking_attempts: 2,
  bookings: 3,
  cancellations: 4,
  deal_feedback: 5,
  deals: 6,
  disruptions: 7,
  notification_deliveries: 8,
  price_observations: 9,
  price_stats: 10,
  rejected_fingerprints: 11,
  spend_ledger: 12,
  suppressed_attributes: 13,
};

type PurgeRequest = {
  confirmation: string;
  plan_digest: string;
};

async function mockAdminApi(page: Page) {
  const purgeRequests: PurgeRequest[] = [];

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
    if (pathname === "/api/v1/admin/integrations") {
      await route.fulfill({
        json: {
          categories: [
            {
              id: "runtime",
              title: "Runtime",
              description: "Runtime operations",
            },
          ],
          providers: [],
          credential_profiles: [],
          feature_flags: [],
          health_notes: [],
          runtime_settings: {
            mock_data_enabled: false,
            live_inventory_available: true,
            current_inventory_mode: "live",
          },
        },
      });
      return;
    }
    if (pathname === "/api/v1/admin/test-data/purge-preview") {
      await route.fulfill({
        json: {
          dry_run: true,
          deleted_counts: previewCounts,
          reset_watch_count: 14,
          plan_digest: "a".repeat(64),
          warnings: ["Two retained records will remain."],
          unreverted_feedback_count: 15,
          unknown_cancellation_count: 16,
        },
      });
      return;
    }
    if (pathname === "/api/v1/admin/test-data/purge") {
      purgeRequests.push(route.request().postDataJSON() as PurgeRequest);
      await route.fulfill({
        json: {
          dry_run: false,
          deleted_counts: previewCounts,
          reset_watch_count: 14,
          plan_digest: "a".repeat(64),
          warnings: [],
          unreverted_feedback_count: 0,
          unknown_cancellation_count: 0,
        },
      });
      return;
    }

    await route.fulfill({
      status: 404,
      json: { detail: "Unhandled browser test route." },
    });
  });

  return { purgeRequests };
}

test.use({ viewport: { width: 320, height: 700 } });

test("purge preview stays reachable at a narrow viewport", async ({ page }) => {
  const { purgeRequests } = await mockAdminApi(page);
  await page.goto("/admin/integrations/runtime");

  await expect(
    page.getByRole("heading", { name: "Purge test data" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Preview purge" }).click();

  const previewStatus = page.getByRole("status", {
    name: "Purge preview ready",
  });
  await expect(previewStatus).toBeFocused();

  const countGroup = page.getByRole("group", { name: "Purge counts" });
  for (const label of [
    "Audit log",
    "Booking attempts",
    "Bookings",
    "Cancellations",
    "Deal feedback",
    "Deals",
    "Disruptions",
    "Notification deliveries",
    "Price observations",
    "Price stats",
    "Rejected fingerprints",
    "Spend ledger",
    "Suppressed attributes",
    "Watches reset",
    "Unknown cancellation provenance",
    "Unreverted feedback",
  ]) {
    const count = countGroup.getByText(label, { exact: true });
    await count.scrollIntoViewIfNeeded();
    await expect(count).toBeVisible();
  }

  const overflow = await countGroup.locator("dl").evaluate((element) => {
    const style = window.getComputedStyle(element);
    return {
      clientHeight: element.clientHeight,
      maxHeight: style.maxHeight,
      overflowY: style.overflowY,
      scrollHeight: element.scrollHeight,
    };
  });
  expect(overflow.maxHeight).toBe("none");
  expect(overflow.overflowY).toBe("visible");
  expect(overflow.scrollHeight).toBeLessThanOrEqual(overflow.clientHeight + 1);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(320);

  await previewStatus.focus();
  await page.keyboard.press("Tab");
  await expect(
    page.getByRole("textbox", {
      name: "Required purge confirmation phrase",
    }),
  ).toBeFocused();
  await expect(
    page.getByRole("textbox", {
      name: "Required purge confirmation phrase",
    }),
  ).toHaveValue("PURGE TEST DATA");
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Copy phrase" })).toBeFocused();
  await page.keyboard.press("Tab");
  const confirmation = page.getByRole("textbox", {
    name: "Type the confirmation phrase",
  });
  await expect(confirmation).toBeFocused();

  const purge = page.getByRole("button", {
    name: "Purge test data permanently",
  });
  await purge.scrollIntoViewIfNeeded();
  await expect(purge).toBeVisible();
  await confirmation.fill("purge test data");
  await expect(purge).toBeDisabled();
  await confirmation.fill("PURGE TEST DATA ");
  await expect(purge).toBeDisabled();
  await confirmation.fill("PURGE TEST DATA");
  await expect(purge).toBeEnabled();
  await purge.click();

  await expect(
    page.getByRole("status", { name: "Purge succeeded" }),
  ).toBeFocused();
  expect(purgeRequests).toEqual([
    {
      confirmation: "PURGE TEST DATA",
      plan_digest: "a".repeat(64),
    },
  ]);
});
