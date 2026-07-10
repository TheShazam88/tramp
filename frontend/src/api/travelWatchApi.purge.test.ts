import { afterEach, describe, expect, it, vi } from "vitest";

async function loadApi(mode: "live" | "mock") {
  vi.stubEnv("VITE_API_MODE", mode);
  vi.resetModules();

  const { apiClient } = await import("@/api/client");
  const { travelWatchApi } = await import("@/api/travelWatchApi");
  return { apiClient, travelWatchApi };
}

describe("travelWatchApi test data purge", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("maps the exact purge preview response", async () => {
    const { apiClient, travelWatchApi } = await loadApi("live");
    const get = vi.spyOn(apiClient, "get").mockResolvedValue({
      dry_run: true,
      deleted_counts: {
        bookings: 2,
        deals: 3,
      },
      reset_watch_count: 1,
      plan_digest: "a".repeat(64),
      warnings: ["One retained record needs review."],
      unreverted_feedback_count: 4,
      unknown_cancellation_count: 5,
    } as never);

    const result = await travelWatchApi.previewTestDataPurge();

    expect(get).toHaveBeenCalledWith("/admin/test-data/purge-preview");
    expect(result).toEqual({
      dryRun: true,
      deletedCounts: {
        bookings: 2,
        deals: 3,
      },
      resetWatchCount: 1,
      planDigest: "a".repeat(64),
      warnings: ["One retained record needs review."],
      unrevertedFeedbackCount: 4,
      unknownCancellationCount: 5,
    });
  });

  it("posts the exact confirmation and preview digest", async () => {
    const { apiClient, travelWatchApi } = await loadApi("live");
    const post = vi.spyOn(apiClient, "post").mockResolvedValue({
      dry_run: false,
      deleted_counts: { deals: 3 },
      reset_watch_count: 1,
      plan_digest: "b".repeat(64),
      warnings: [],
      unreverted_feedback_count: 0,
      unknown_cancellation_count: 0,
    } as never);

    const result = await travelWatchApi.purgeTestData({
      confirmation: "PURGE TEST DATA",
      planDigest: "b".repeat(64),
    });

    expect(post).toHaveBeenCalledWith("/admin/test-data/purge", {
      confirmation: "PURGE TEST DATA",
      plan_digest: "b".repeat(64),
    });
    expect(result).toMatchObject({
      dryRun: false,
      deletedCounts: { deals: 3 },
      planDigest: "b".repeat(64),
    });
  });

  it("keeps mock mode isolated from every backend request", async () => {
    const { apiClient, travelWatchApi } = await loadApi("mock");
    const get = vi.spyOn(apiClient, "get");
    const post = vi.spyOn(apiClient, "post");

    const preview = await travelWatchApi.previewTestDataPurge();
    const result = await travelWatchApi.purgeTestData({
      confirmation: "PURGE TEST DATA",
      planDigest: preview.planDigest,
    });

    expect(preview).toMatchObject({
      dryRun: true,
      resetWatchCount: 0,
      planDigest: "0".repeat(64),
      unrevertedFeedbackCount: 0,
      unknownCancellationCount: 0,
    });
    expect(Object.values(preview.deletedCounts).every((count) => count === 0)).toBe(true);
    expect(result).toMatchObject({
      dryRun: true,
      resetWatchCount: 0,
      planDigest: "0".repeat(64),
    });
    expect(get).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
  });
});
