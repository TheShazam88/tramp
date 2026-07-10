import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, apiClient } from "@/api/client";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import type { TestDataPurgeResult } from "@/api/types";
import { PurgeTestDataPanel } from "@/components/admin/PurgeTestDataPanel";

const confirmationPhrase = "PURGE TEST DATA";
const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");
const originalApiMode = apiClient.mode;
const originalInnerWidth = Object.getOwnPropertyDescriptor(window, "innerWidth");

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((resolvePromise) => {
    resolve = resolvePromise;
  });
  return { promise, resolve };
}

function purgeResult(
  overrides: Partial<TestDataPurgeResult> = {},
): TestDataPurgeResult {
  return {
    dryRun: true,
    deletedCounts: {
      bookings: 2,
      deals: 3,
      price_observations: 4,
    },
    resetWatchCount: 1,
    planDigest: "a".repeat(64),
    warnings: ["One retained record needs review."],
    unrevertedFeedbackCount: 0,
    unknownCancellationCount: 0,
    ...overrides,
  };
}

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <PurgeTestDataPanel />
    </QueryClientProvider>,
  );

  return queryClient;
}

function setClipboard(value: { writeText: (text: string) => Promise<void> } | undefined) {
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value,
  });
}

async function loadPreview(
  user: ReturnType<typeof userEvent.setup>,
  result = purgeResult(),
) {
  vi.spyOn(travelWatchApi, "previewTestDataPurge").mockResolvedValue(result);
  await user.click(
    screen.getByRole("button", { name: "Preview purge" }),
  );
  return screen.findByRole("region", { name: "Purge preview" });
}

afterEach(() => {
  vi.restoreAllMocks();
  apiClient.mode = originalApiMode;
  if (originalClipboard) {
    Object.defineProperty(navigator, "clipboard", originalClipboard);
  } else {
    Reflect.deleteProperty(navigator, "clipboard");
  }
  if (originalInnerWidth) {
    Object.defineProperty(window, "innerWidth", originalInnerWidth);
  } else {
    Reflect.deleteProperty(window, "innerWidth");
  }
});

describe("PurgeTestDataPanel", () => {
  it("does not mutate on render and displays the complete preview", async () => {
    const user = userEvent.setup();
    const previewCall = vi
      .spyOn(travelWatchApi, "previewTestDataPurge")
      .mockResolvedValue(purgeResult());
    const purge = vi.spyOn(travelWatchApi, "purgeTestData");
    renderPanel();

    expect(previewCall).not.toHaveBeenCalled();
    expect(purge).not.toHaveBeenCalled();

    await user.click(
      screen.getByRole("button", { name: "Preview purge" }),
    );
    const preview = await screen.findByRole("region", {
      name: "Purge preview",
    });
    const previewQueries = within(preview);

    expect(
      previewQueries.getByText("Bookings").parentElement,
    ).toHaveTextContent("2");
    expect(
      previewQueries.getByText("Deals").parentElement,
    ).toHaveTextContent("3");
    expect(
      previewQueries.getByText("Price observations").parentElement,
    ).toHaveTextContent("4");
    expect(
      previewQueries.getByText("Watches reset").parentElement,
    ).toHaveTextContent("1");
    expect(
      previewQueries.getByText("Unknown cancellation provenance").parentElement,
    ).toHaveTextContent("0");
    expect(
      previewQueries.getByText("Unreverted feedback").parentElement,
    ).toHaveTextContent("0");
    expect(
      previewQueries.getByText("One retained record needs review."),
    ).toBeInTheDocument();
    expect(
      previewQueries.getByText(
        /Users, traveler profiles, preferences, payment methods, loyalty accounts, credential profiles, and live provider activity are preserved\./,
      ),
    ).toBeInTheDocument();
    expect(purge).not.toHaveBeenCalled();
  });

  it("announces and focuses a successful preview", async () => {
    const user = userEvent.setup();
    renderPanel();

    await loadPreview(user, purgeResult({ warnings: [] }));

    const status = screen.getByRole("status", {
      name: "Purge preview ready",
    });
    expect(status).toHaveAttribute("aria-live", "polite");
    await waitFor(() => expect(status).toHaveFocus());
  });

  it("keeps every count accessible by keyboard at a small viewport", async () => {
    Object.defineProperty(window, "innerWidth", {
      configurable: true,
      value: 320,
    });
    window.dispatchEvent(new Event("resize"));
    const user = userEvent.setup();
    const deletedCounts = {
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
    renderPanel();

    const preview = await loadPreview(
      user,
      purgeResult({ deletedCounts, warnings: [] }),
    );
    const countList = within(preview).getByRole("group", {
      name: "Purge counts",
    });

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
    ]) {
      expect(within(countList).getByText(label)).toBeVisible();
    }

    const status = screen.getByRole("status", {
      name: "Purge preview ready",
    });
    await waitFor(() => expect(status).toHaveFocus());
    await user.tab();
    expect(
      screen.getByRole("textbox", {
        name: "Required purge confirmation phrase",
      }),
    ).toHaveFocus();
  });

  it("copies the read-only confirmation phrase and reports success", async () => {
    const user = userEvent.setup();
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard({ writeText });
    renderPanel();
    await loadPreview(user);

    const phrase = screen.getByRole("textbox", {
      name: "Required purge confirmation phrase",
    });
    expect(phrase).toHaveAttribute("readonly");
    expect(phrase).toHaveValue(confirmationPhrase);

    fireEvent.click(screen.getByRole("button", { name: "Copy phrase" }));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(confirmationPhrase);
    });
    expect(
      screen.getByRole("status", { name: "Copy status" }),
    ).toHaveTextContent("Confirmation phrase copied.");
  });

  it("selects and focuses the phrase when clipboard access is unavailable", async () => {
    const user = userEvent.setup();
    setClipboard(undefined);
    renderPanel();
    await loadPreview(user);

    const phrase = screen.getByRole("textbox", {
      name: "Required purge confirmation phrase",
    }) as HTMLInputElement;
    fireEvent.click(screen.getByRole("button", { name: "Copy phrase" }));

    await waitFor(() => {
      expect(phrase).toHaveFocus();
    });
    expect(phrase.selectionStart).toBe(0);
    expect(phrase.selectionEnd).toBe(confirmationPhrase.length);
    expect(
      screen.getByRole("status", { name: "Copy status" }),
    ).toHaveTextContent(
      "Clipboard access is unavailable. The phrase is selected for manual copy.",
    );
  });

  it("requires the exact phrase before enabling the destructive action", async () => {
    const user = userEvent.setup();
    renderPanel();
    await loadPreview(user, purgeResult({ warnings: [] }));

    const purgeButton = screen.getByRole("button", {
      name: "Purge test data permanently",
    });
    const confirmation = screen.getByRole("textbox", {
      name: "Type the confirmation phrase",
    });

    expect(purgeButton).toBeDisabled();
    await user.type(confirmation, "purge test data");
    expect(purgeButton).toBeDisabled();
    await user.clear(confirmation);
    await user.type(confirmation, `${confirmationPhrase} `);
    expect(purgeButton).toBeDisabled();
    await user.clear(confirmation);
    await user.type(confirmation, confirmationPhrase);
    expect(purgeButton).toBeEnabled();
  });

  it("coalesces rapid preview activation into one request", async () => {
    const pendingPreview = deferred<TestDataPurgeResult>();
    const preview = vi
      .spyOn(travelWatchApi, "previewTestDataPurge")
      .mockReturnValue(pendingPreview.promise);
    renderPanel();
    const button = screen.getByRole("button", { name: "Preview purge" });

    act(() => {
      button.click();
      button.click();
    });

    await waitFor(() => {
      expect(preview).toHaveBeenCalledTimes(1);
      expect(button).toBeDisabled();
    });

    await act(async () => {
      pendingPreview.resolve(purgeResult({ warnings: [] }));
      await pendingPreview.promise;
    });
    expect(
      await screen.findByRole("status", { name: "Purge preview ready" }),
    ).toBeInTheDocument();
  });

  it("coalesces rapid purge activation into one request", async () => {
    const user = userEvent.setup();
    const pendingPurge = deferred<TestDataPurgeResult>();
    const purge = vi
      .spyOn(travelWatchApi, "purgeTestData")
      .mockReturnValue(pendingPurge.promise);
    renderPanel();
    await loadPreview(user, purgeResult({ warnings: [] }));
    await user.type(
      screen.getByRole("textbox", { name: "Type the confirmation phrase" }),
      confirmationPhrase,
    );
    const button = screen.getByRole("button", {
      name: "Purge test data permanently",
    });

    act(() => {
      button.click();
      button.click();
    });

    await waitFor(() => {
      expect(purge).toHaveBeenCalledTimes(1);
      expect(button).toBeDisabled();
    });

    await act(async () => {
      pendingPurge.resolve(purgeResult({ dryRun: false, warnings: [] }));
      await pendingPurge.promise;
    });
    expect(
      await screen.findByRole("status", { name: "Purge succeeded" }),
    ).toBeInTheDocument();
  });

  it("keeps mock frontend mode preview-only", async () => {
    apiClient.mode = "mock";
    const preview = vi
      .spyOn(travelWatchApi, "previewTestDataPurge")
      .mockResolvedValue(
        purgeResult({
          deletedCounts: { bookings: 0, deals: 0 },
          resetWatchCount: 0,
          planDigest: "0".repeat(64),
          warnings: ["Demo preview only. No backend data was changed."],
        }),
      );
    const purge = vi.spyOn(travelWatchApi, "purgeTestData");
    renderPanel();

    expect(
      screen.getByRole("status", { name: "Mock purge mode" }),
    ).toHaveTextContent(
      "Switch the frontend to live API mode to run a real purge.",
    );
    await userEvent
      .setup()
      .click(screen.getByRole("button", { name: "Preview purge" }));

    expect(preview).toHaveBeenCalledTimes(1);
    expect(
      await screen.findByRole("status", { name: "Purge preview ready" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: "Type the confirmation phrase" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Purge test data permanently" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(
        "Test data purge completed. The exact backend result appears below.",
      ),
    ).not.toBeInTheDocument();
    expect(purge).not.toHaveBeenCalled();
  });

  it("allows purge while clearly retaining unknown provenance and unreverted feedback", async () => {
    const user = userEvent.setup();
    const warningResult = purgeResult({
      unknownCancellationCount: 1,
      unrevertedFeedbackCount: 2,
      warnings: [
        "One cancellation has unknown provenance.",
        "Two feedback records could not be safely reverted.",
      ],
    });
    const purge = vi
      .spyOn(travelWatchApi, "purgeTestData")
      .mockResolvedValue({ ...warningResult, dryRun: false });
    renderPanel();
    const preview = await loadPreview(user, warningResult);

    await user.type(
      screen.getByRole("textbox", { name: "Type the confirmation phrase" }),
      confirmationPhrase,
    );

    expect(
      within(preview).getByText("One cancellation has unknown provenance."),
    ).toBeInTheDocument();
    expect(
      within(preview).getByText(
        "Two feedback records could not be safely reverted.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("status", { name: "Retained evidence notice" }),
    ).toHaveTextContent(
      "These records will remain after the purge.",
    );
    const purgeButton = screen.getByRole("button", {
      name: "Purge test data permanently",
    });
    expect(purgeButton).toBeEnabled();

    await user.click(purgeButton);

    expect(purge).toHaveBeenCalledWith({
      confirmation: confirmationPhrase,
      planDigest: warningResult.planDigest,
    });
  });

  it("clears a stale preview and focuses the safe error", async () => {
    const user = userEvent.setup();
    vi.spyOn(travelWatchApi, "purgeTestData").mockRejectedValue(
      new ApiError("Request failed with status 400", 400, {
        detail:
          "Purge preview changed. Request a new preview and confirm that plan_digest.",
      }),
    );
    renderPanel();
    await loadPreview(user, purgeResult({ warnings: [] }));
    await user.type(
      screen.getByRole("textbox", { name: "Type the confirmation phrase" }),
      confirmationPhrase,
    );
    await user.click(
      screen.getByRole("button", { name: "Purge test data permanently" }),
    );

    const alert = await screen.findByRole("alert", {
      name: "Purge error",
    });
    expect(alert).toHaveTextContent(
      "The purge preview is stale. Request a new preview before trying again.",
    );
    await waitFor(() => expect(alert).toHaveFocus());
    expect(
      screen.queryByRole("region", { name: "Purge preview" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: "Type the confirmation phrase" }),
    ).not.toBeInTheDocument();
  });

  it.each([
    {
      label: "network failure",
      error: new TypeError("Failed to fetch confidential-url"),
    },
    {
      label: "server failure",
      error: new ApiError("Request failed with status 503", 503, {
        detail: "Internal failure for secret_record_123.",
      }),
    },
  ])(
    "resets unsafe state and refreshes all queries after an ambiguous $label",
    async ({ error }) => {
      const user = userEvent.setup();
      vi.spyOn(travelWatchApi, "purgeTestData").mockRejectedValue(error);
      const queryClient = renderPanel();
      const invalidate = vi
        .spyOn(queryClient, "invalidateQueries")
        .mockResolvedValue(undefined);
      await loadPreview(user, purgeResult({ warnings: [] }));
      await user.type(
        screen.getByRole("textbox", { name: "Type the confirmation phrase" }),
        confirmationPhrase,
      );

      await user.click(
        screen.getByRole("button", { name: "Purge test data permanently" }),
      );

      const alert = await screen.findByRole("alert", {
        name: "Purge outcome unknown",
      });
      expect(alert).toHaveTextContent(
        "TRAMP could not confirm whether the purge completed.",
      );
      expect(alert).toHaveTextContent(
        "Request a fresh preview before trying again.",
      );
      expect(alert).not.toHaveTextContent(/confidential-url|secret_record_123/);
      await waitFor(() => expect(alert).toHaveFocus());
      expect(
        screen.queryByRole("region", { name: "Purge preview" }),
      ).not.toBeInTheDocument();
      expect(
        screen.queryByRole("textbox", {
          name: "Type the confirmation phrase",
        }),
      ).not.toBeInTheDocument();
      expect(invalidate).toHaveBeenCalledTimes(1);
      expect(invalidate).toHaveBeenCalledWith({ refetchType: "all" });
      expect(
        screen.getByRole("button", { name: "Preview purge" }),
      ).toBeEnabled();
    },
  );

  it("shows the exact execution summary and invalidates every affected query", async () => {
    const user = userEvent.setup();
    const executed = purgeResult({
      dryRun: false,
      deletedCounts: {
        bookings: 7,
        deals: 8,
      },
      resetWatchCount: 2,
      planDigest: "c".repeat(64),
      warnings: ["One live-linked record was preserved."],
    });
    vi.spyOn(travelWatchApi, "purgeTestData").mockResolvedValue(executed);
    const queryClient = renderPanel();
    queryClient.setQueryData(queryKeys.watchDraft("watch-1"), {
      id: "watch-1",
    });
    queryClient.setQueryData(
      queryKeys.approvalToken("deal-1", "approval-token"),
      { valid: true },
    );
    const invalidate = vi
      .spyOn(queryClient, "invalidateQueries")
      .mockResolvedValue(undefined);
    await loadPreview(
      user,
      purgeResult({
        warnings: [],
        planDigest: "c".repeat(64),
      }),
    );
    await user.type(
      screen.getByRole("textbox", { name: "Type the confirmation phrase" }),
      confirmationPhrase,
    );
    await user.click(
      screen.getByRole("button", { name: "Purge test data permanently" }),
    );

    const success = await screen.findByRole("status", {
      name: "Purge succeeded",
    });
    await waitFor(() => expect(success).toHaveFocus());

    const summary = screen.getByRole("region", {
      name: "Purge execution summary",
    });
    const summaryQueries = within(summary);
    expect(summaryQueries.getByText("Dry run").parentElement).toHaveTextContent(
      "No",
    );
    expect(
      summaryQueries.getByText("Bookings").parentElement,
    ).toHaveTextContent("7");
    expect(summaryQueries.getByText("Deals").parentElement).toHaveTextContent(
      "8",
    );
    expect(
      summaryQueries.getByText("Watches reset").parentElement,
    ).toHaveTextContent("2");
    expect(
      summaryQueries.getByText("One live-linked record was preserved."),
    ).toBeInTheDocument();
    expect(
      summaryQueries.getByText("c".repeat(64)),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("region", { name: "Purge preview" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: "Type the confirmation phrase" }),
    ).not.toBeInTheDocument();

    await waitFor(() => {
      expect(invalidate).toHaveBeenCalledTimes(1);
      expect(invalidate).toHaveBeenCalledWith({ refetchType: "all" });
    });
  });

  it.each([
    {
      detail: "Confirmation must exactly match 'PURGE TEST DATA'.",
      expected:
        "The backend rejected the confirmation phrase. Request a new preview and enter the phrase exactly.",
    },
    {
      detail:
        "Unknown cancellation provenance blocks execution for secret_record_123.",
      expected:
        "The backend blocked this purge because cancellation provenance is unknown. Review the preview before continuing.",
    },
  ])("handles structured backend errors without exposing raw payloads", async ({
    detail,
    expected,
  }) => {
    const user = userEvent.setup();
    vi.spyOn(travelWatchApi, "purgeTestData").mockRejectedValue(
      new ApiError("Request failed with status 400", 400, { detail }),
    );
    renderPanel();
    await loadPreview(user, purgeResult({ warnings: [] }));
    await user.type(
      screen.getByRole("textbox", { name: "Type the confirmation phrase" }),
      confirmationPhrase,
    );
    await user.click(
      screen.getByRole("button", { name: "Purge test data permanently" }),
    );

    const alert = await screen.findByRole("alert", {
      name: "Purge error",
    });
    expect(alert).toHaveTextContent(expected);
    expect(alert).not.toHaveTextContent("secret_record_123");
    await waitFor(() => expect(alert).toHaveFocus());
  });

  it("reports network failures safely and focuses the alert", async () => {
    const user = userEvent.setup();
    vi.spyOn(travelWatchApi, "previewTestDataPurge").mockRejectedValue(
      new TypeError("Failed to fetch confidential-url"),
    );
    renderPanel();

    await user.click(
      screen.getByRole("button", { name: "Preview purge" }),
    );

    const alert = await screen.findByRole("alert", {
      name: "Purge error",
    });
    expect(alert).toHaveTextContent(
      "Unable to reach the backend. Check the connection and try again.",
    );
    expect(alert).not.toHaveTextContent("confidential-url");
    await waitFor(() => expect(alert).toHaveFocus());
  });
});
