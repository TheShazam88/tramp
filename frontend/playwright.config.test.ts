import { dirname } from "node:path";

import { describe, expect, it } from "vitest";

const frontendDirectory = process.cwd();
const repositoryDirectory = dirname(frontendDirectory);

describe("Playwright web server configuration", () => {
  it("uses the frontend directory when loaded from another working directory", async () => {
    const originalDirectory = process.cwd();
    process.chdir(repositoryDirectory);

    try {
      const { default: config } = await import("./playwright.config");
      const webServer = Array.isArray(config.webServer)
        ? config.webServer[0]
        : config.webServer;

      expect(webServer?.cwd).toBe(frontendDirectory);
    } finally {
      process.chdir(originalDirectory);
    }
  });
});
