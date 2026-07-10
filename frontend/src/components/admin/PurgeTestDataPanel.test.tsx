import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/api/client";
import { queryKeys, travelWatchApi } from "@/api/travelWatchApi";
import type { TestDataPurgeResult } from "@/api/types";
import { PurgeTestDataPanel } from "@/components/admin/PurgeTestDataPanel";

const confirmationPhrase = "PURGE TEST DATA";
const originalClipboard = Object.getOwnPropertyDescriptor(navigator, "clipboard");

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
  if (originalClipboard) {
    Object.defineProperty(navigator, "clipboard", originalClipboard);
  } else {
    Reflect.deleteProperty(navigator, "clipboard");
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

  it("blocks execution when unknown provenance or feedback cannot be reverted", async () => {
    const user = userEvent.setup();
    const purge = vi.spyOn(travelWatchApi, "purgeTestData");
    renderPanel();
    await loadPreview(
      user,
      purgeResult({
        unknownCancellationCount: 1,
        unrevertedFeedbackCount: 2,
        warnings: [
          "One cancellation has unknown provenance.",
          "Two feedback records could not be safely reverted.",
        ],
      }),
    );

    await user.type(
      screen.getByRole("textbox", { name: "Type the confirmation phrase" }),
      confirmationPhrase,
    );

    expect(
      screen.getByRole("alert", { name: "Purge blocked" }),
    ).toHaveTextContent(
      "Purge is blocked while unknown cancellation provenance or unreverted feedback remains.",
    );
    expect(
      screen.getByRole("button", { name: "Purge test data permanently" }),
    ).toBeDisabled();
    expect(purge).not.toHaveBeenCalled();
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
      expect(invalidate).toHaveBeenCalledWith({
        queryKey: queryKeys.integrations,
      });
      expect(invalidate).toHaveBeenCalledWith({
        queryKey: queryKeys.systemStatus,
      });
      expect(invalidate).toHaveBeenCalledWith({
        queryKey: queryKeys.dashboard,
      });
      expect(invalidate).toHaveBeenCalledWith({
        queryKey: queryKeys.bookings,
      });
      expect(invalidate).toHaveBeenCalledWith({
        queryKey: queryKeys.profile,
      });
      expect(invalidate).toHaveBeenCalledWith({
        queryKey: ["deal"],
      });
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
