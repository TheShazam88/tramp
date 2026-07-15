import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { readFile, mkdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "@playwright/test";

const VIEWPORT = { width: 1440, height: 1000 };
const HOST = "127.0.0.1";
const PORT = 4174;
const BASE_URL = `http://${HOST}:${PORT}`;
const FIXED_TIME = "2026-07-15T04:40:00.000Z";
const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

const scriptPath = fileURLToPath(import.meta.url);
const scriptsDirectory = path.dirname(scriptPath);
const frontendDirectory = path.resolve(scriptsDirectory, "..");
const screenshotsDirectory = path.resolve(frontendDirectory, "../docs/screenshots");
const viteModuleUrl = import.meta.resolve("vite");
const childLifecycles = new WeakMap();
const VITE_BOOTSTRAP_SOURCE = `
  import { createServer } from ${JSON.stringify(viteModuleUrl)};

  const host = process.env.TRAMP_SCREENSHOT_HOST;
  const port = Number(process.env.TRAMP_SCREENSHOT_PORT);
  const readyMarker = process.env.TRAMP_SCREENSHOT_READY_MARKER;
  const server = await createServer({
    root: process.cwd(),
    server: { host, port, strictPort: true },
  });
  let shuttingDown = false;
  const shutdown = async () => {
    if (shuttingDown) return;
    shuttingDown = true;
    try {
      await server.close();
      process.exit(0);
    } catch (error) {
      console.error(error);
      process.exit(1);
    }
  };
  process.once("SIGINT", () => void shutdown());
  process.once("SIGTERM", () => void shutdown());
  await server.listen();
  process.stdout.write(readyMarker + "\\n");
`;

export const SCREENSHOTS = [
  {
    path: "/watches",
    filename: "01-watches-dashboard.png",
    heading: "Your trips",
  },
  {
    path: "/deals/deal-118400?watchId=tokyo-singapore",
    filename: "02-deal-review.png",
    heading: "Tokyo -> Singapore · Business",
  },
  {
    path: "/admin/integrations/flights",
    filename: "03-admin-integrations.png",
    heading: "Flights",
  },
  {
    path: "/profile",
    filename: "04-household-workspace.png",
    heading: "Profile and settings",
  },
];

export const ADMIN_GUIDANCE_CAPTURE = {
  parentSummary: "Profile fields",
  guideSummary: "How to get Flights · Duffel credentials",
};

export function validatePngBuffer(
  buffer,
  expectedDimensions = VIEWPORT,
) {
  if (buffer.length < 24 || !buffer.subarray(0, PNG_SIGNATURE.length).equals(PNG_SIGNATURE)) {
    throw new Error("file does not have a valid PNG signature");
  }
  if (buffer.readUInt32BE(8) !== 13 || buffer.subarray(12, 16).toString("ascii") !== "IHDR") {
    throw new Error("file does not begin with a valid PNG IHDR chunk");
  }

  const width = buffer.readUInt32BE(16);
  const height = buffer.readUInt32BE(20);
  if (width !== expectedDimensions.width || height !== expectedDimensions.height) {
    throw new Error(
      `expected ${expectedDimensions.width}x${expectedDimensions.height}, received ${width}x${height}`,
    );
  }

  return { width, height };
}

function screenshotPath(definition) {
  return path.join(screenshotsDirectory, definition.filename);
}

async function validateScreenshotFile(definition) {
  const outputPath = screenshotPath(definition);
  const [metadata, buffer] = await Promise.all([stat(outputPath), readFile(outputPath)]);
  if (!metadata.isFile() || metadata.size <= 24) {
    throw new Error(`${definition.filename} is empty`);
  }

  const dimensions = validatePngBuffer(buffer);
  const finalChunkType = buffer.subarray(-8, -4).toString("ascii");
  if (finalChunkType !== "IEND") {
    throw new Error(`${definition.filename} does not end with a PNG IEND chunk`);
  }

  return {
    filename: definition.filename,
    bytes: metadata.size,
    ...dimensions,
  };
}

async function validateAllScreenshots() {
  const results = [];
  for (const definition of SCREENSHOTS) {
    results.push(await validateScreenshotFile(definition));
  }
  for (const result of results) {
    console.log(
      `Validated ${result.filename}: ${result.width}x${result.height}, ${result.bytes} bytes`,
    );
  }
}

function sanitizedViteEnvironment() {
  const allowedKeys = [
    "PATH",
    "HOME",
    "TMPDIR",
    "TMP",
    "TEMP",
    "LANG",
    "LC_ALL",
    "SHELL",
    "USER",
    "LOGNAME",
    "SystemRoot",
    "ComSpec",
    "PATHEXT",
  ];
  const environment = {};
  for (const key of allowedKeys) {
    if (process.env[key]) {
      environment[key] = process.env[key];
    }
  }
  return {
    ...environment,
    FORCE_COLOR: "0",
    NODE_ENV: "development",
    VITE_API_MODE: "mock",
  };
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function timeoutAfter(milliseconds, value) {
  let timeoutId;
  return {
    promise: new Promise((resolve) => {
      timeoutId = setTimeout(() => resolve(value), milliseconds);
    }),
    cancel() {
      clearTimeout(timeoutId);
    },
  };
}

function observeChild(server) {
  const closePromise =
    server.exitCode !== null || server.signalCode !== null
      ? Promise.resolve({
          type: "close",
          code: server.exitCode,
          signal: server.signalCode,
        })
      : new Promise((resolve) => {
          server.once("close", (code, signal) => {
            resolve({ type: "close", code, signal });
          });
        });
  const errorPromise = new Promise((resolve) => {
    server.once("error", (error) => {
      resolve({ type: "error", error });
    });
  });
  const lifecycle = {
    closePromise,
    terminalPromise: Promise.race([closePromise, errorPromise]),
  };
  childLifecycles.set(server, lifecycle);
  return lifecycle;
}

function startupFailure(event, getOutput) {
  if (event.type === "error") {
    return new Error(`Vite failed to start: ${event.error.message}.\n${getOutput()}`);
  }
  const result =
    event.code !== null ? `code ${event.code}` : `signal ${event.signal ?? "unknown"}`;
  return new Error(`Vite exited before becoming ready (${result}).\n${getOutput()}`);
}

async function waitForVite(
  server,
  lifecycle,
  getOutput,
  {
    baseUrl = BASE_URL,
    fetchImplementation = fetch,
    readyMarker,
    readyPromise,
    timeoutMs = 20_000,
  } = {},
) {
  const deadline = Date.now() + timeoutMs;
  const startupTimeout = timeoutAfter(timeoutMs, { type: "timeout" });
  const initialEvent = await Promise.race([
    readyPromise,
    lifecycle.terminalPromise,
    startupTimeout.promise,
  ]);
  startupTimeout.cancel();
  if (initialEvent.type === "error" || initialEvent.type === "close") {
    throw startupFailure(initialEvent, getOutput);
  }
  if (initialEvent.type === "timeout") {
    throw new Error(
      `Timed out waiting for Vite child marker ${readyMarker} at ${baseUrl}.\n${getOutput()}`,
    );
  }

  while (Date.now() < deadline) {
    if (server.exitCode !== null || server.signalCode !== null) {
      throw startupFailure(
        {
          type: "close",
          code: server.exitCode,
          signal: server.signalCode,
        },
        getOutput,
      );
    }
    const remainingMs = Math.max(1, deadline - Date.now());
    const request = Promise.resolve()
      .then(() =>
        fetchImplementation(baseUrl, {
          signal: AbortSignal.timeout(Math.min(750, remainingMs)),
        }),
      )
      .then(
        (response) => ({ type: "response", response }),
        () => ({ type: "retry" }),
      );
    const event = await Promise.race([request, lifecycle.terminalPromise]);
    if (event.type === "error" || event.type === "close") {
      throw startupFailure(event, getOutput);
    }
    if (event.type === "response" && event.response.ok) {
      await delay(0);
      if (server.exitCode === null && server.signalCode === null) {
        return;
      }
    }
    await delay(100);
  }
  throw new Error(`Timed out waiting for ${baseUrl}.\n${getOutput()}`);
}

export async function startVite({
  fetchImplementation = fetch,
  host = HOST,
  port = PORT,
  spawnProcess = spawn,
  timeoutMs = 20_000,
} = {}) {
  const baseUrl = `http://${host}:${port}`;
  const readyMarker = `TRAMP_SCREENSHOT_READY:${randomUUID()}`;
  const server = spawnProcess(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      VITE_BOOTSTRAP_SOURCE,
    ],
    {
      cwd: frontendDirectory,
      env: {
        ...sanitizedViteEnvironment(),
        TRAMP_SCREENSHOT_HOST: host,
        TRAMP_SCREENSHOT_PORT: String(port),
        TRAMP_SCREENSHOT_READY_MARKER: readyMarker,
      },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );

  const lifecycle = observeChild(server);
  let output = "";
  let resolveReady;
  const readyPromise = new Promise((resolve) => {
    resolveReady = resolve;
  });
  const recordOutput = (chunk) => {
    output = `${output}${chunk.toString()}`.slice(-12_000);
    if (output.includes(readyMarker)) {
      resolveReady({ type: "ready" });
    }
  };

  try {
    server.stdout.on("data", recordOutput);
    server.stderr.on("data", recordOutput);
    await waitForVite(server, lifecycle, () => output, {
      baseUrl,
      fetchImplementation,
      readyMarker,
      readyPromise,
      timeoutMs,
    });
    return server;
  } catch (error) {
    await stopProcess(server);
    throw error;
  }
}

async function stopProcess(server) {
  if (!server) {
    return;
  }
  const lifecycle = childLifecycles.get(server) ?? observeChild(server);
  if (server.exitCode === null && server.signalCode === null) {
    server.kill("SIGTERM");
  }
  const shutdownTimeout = timeoutAfter(2_000, null);
  const terminalEvent = await Promise.race([
    lifecycle.terminalPromise,
    shutdownTimeout.promise,
  ]);
  shutdownTimeout.cancel();
  if (terminalEvent) {
    await lifecycle.closePromise;
    return;
  }
  if (server.exitCode === null && server.signalCode === null) {
    server.kill("SIGKILL");
  }
  await lifecycle.closePromise;
}

async function installDeterministicPageState(page) {
  await page.addInitScript(
    ({ fixedTime }) => {
      const NativeDate = Date;
      const fixedTimestamp = NativeDate.parse(fixedTime);
      class FixedDate extends NativeDate {
        constructor(...args) {
          super(...(args.length === 0 ? [fixedTimestamp] : args));
        }

        static now() {
          return fixedTimestamp;
        }
      }

      Object.defineProperty(window, "Date", {
        configurable: true,
        value: FixedDate,
      });
      Math.random = () => 0.3141592653589793;
      window.localStorage.clear();
      window.sessionStorage.clear();
    },
    { fixedTime: FIXED_TIME },
  );
}

async function stabilizePage(page) {
  await page.addStyleTag({
    content: `
      *,
      *::before,
      *::after {
        animation-delay: 0s !important;
        animation-duration: 0s !important;
        caret-color: transparent !important;
        scroll-behavior: auto !important;
        transition-delay: 0s !important;
        transition-duration: 0s !important;
      }
    `,
  });
  await page.evaluate(async () => {
    if (document.fonts?.ready) {
      await document.fonts.ready;
    }
  });
}

async function positionPage(page, definition) {
  if (definition.filename === "03-admin-integrations.png") {
    for (const summaryText of [
      ADMIN_GUIDANCE_CAPTURE.parentSummary,
      ADMIN_GUIDANCE_CAPTURE.guideSummary,
    ]) {
      const summary = page.getByText(summaryText, { exact: true }).first();
      await summary.waitFor({ state: "visible" });
      const disclosure = summary.locator("xpath=ancestor::details[1]");
      if (!(await disclosure.evaluate((element) => element.open))) {
        await summary.click();
      }
    }
    await page
      .getByText("Account requirements", { exact: true })
      .first()
      .waitFor({ state: "visible" });
    await page
      .getByText(ADMIN_GUIDANCE_CAPTURE.guideSummary, { exact: true })
      .first()
      .evaluate((element) => {
        const top = element.getBoundingClientRect().top + window.scrollY - 480;
        window.scrollTo(0, Math.max(0, top));
      });
    return;
  }

  if (definition.filename !== "04-household-workspace.png") {
    await page.evaluate(() => window.scrollTo(0, 0));
    return;
  }

  const workspaceHeading = page.getByRole("heading", {
    name: "Household booking readiness",
    exact: true,
  });
  await workspaceHeading.waitFor({ state: "visible" });
  await workspaceHeading.evaluate((element) => {
    const top = element.getBoundingClientRect().top + window.scrollY - 24;
    window.scrollTo(0, Math.max(0, top));
  });
}

async function assertNoVisibleSecrets(page, definition) {
  const populatedPasswordInputs = await page
    .locator('input[type="password"]')
    .evaluateAll((inputs) =>
      inputs
        .map((input) => input.value)
        .filter((value) => value.trim().length > 0),
    );
  if (populatedPasswordInputs.length > 0) {
    throw new Error(`${definition.filename} contains a populated password field`);
  }

  const bodyText = await page.locator("body").innerText();
  const secretPatterns = [
    /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
    /\bAKIA[0-9A-Z]{16}\b/,
    /\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b/i,
    /\bgh[opurs]_[A-Za-z0-9]{20,}\b/,
  ];
  const match = secretPatterns.find((pattern) => pattern.test(bodyText));
  if (match) {
    throw new Error(`${definition.filename} matched a secret-like value (${match})`);
  }
}

async function captureScreenshots() {
  await mkdir(screenshotsDirectory, { recursive: true });
  const server = await startVite();
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      colorScheme: "light",
      deviceScaleFactor: 1,
      locale: "en-US",
      reducedMotion: "reduce",
      screen: VIEWPORT,
      serviceWorkers: "block",
      timezoneId: "UTC",
      viewport: VIEWPORT,
    });
    const allowedOrigin = new URL(BASE_URL).origin;
    await context.route("**/*", async (route) => {
      const requestUrl = new URL(route.request().url());
      if (["http:", "https:"].includes(requestUrl.protocol) && requestUrl.origin !== allowedOrigin) {
        await route.abort("blockedbyclient");
        return;
      }
      await route.continue();
    });

    const page = await context.newPage();
    await installDeterministicPageState(page);

    for (const definition of SCREENSHOTS) {
      await page.goto(new URL(definition.path, BASE_URL).toString(), {
        waitUntil: "networkidle",
      });
      await page
        .getByRole("heading", { name: definition.heading, exact: true })
        .waitFor({ state: "visible" });
      await stabilizePage(page);
      await positionPage(page, definition);
      await assertNoVisibleSecrets(page, definition);
      await page.screenshot({
        animations: "disabled",
        caret: "hide",
        fullPage: false,
        path: screenshotPath(definition),
        scale: "css",
        type: "png",
      });
      console.log(`Captured ${definition.filename}`);
    }

    await context.close();
    await validateAllScreenshots();
  } finally {
    await browser?.close();
    await stopProcess(server);
  }
}

async function main() {
  if (process.argv.includes("--smoke")) {
    await validateAllScreenshots();
    return;
  }
  await captureScreenshots();
}

if (process.argv[1] && path.resolve(process.argv[1]) === scriptPath) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  });
}
