import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { defineConfig } from "@playwright/test";

const frontendDirectory = dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  testDir: "./e2e",
  outputDir: join(tmpdir(), "tramp-playwright-results"),
  fullyParallel: false,
  workers: 1,
  reporter: "line",
  use: {
    baseURL: "http://127.0.0.1:4173",
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173",
    cwd: frontendDirectory,
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
  },
});
