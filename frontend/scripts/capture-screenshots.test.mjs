import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { createServer } from "node:http";
import { test } from "node:test";

import * as screenshotScript from "./capture-screenshots.mjs";

const { SCREENSHOTS, validatePngBuffer } = screenshotScript;

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

async function startStaleServer() {
  const state = { requests: 0 };
  const server = createServer((_request, response) => {
    state.requests += 1;
    response.writeHead(200, { "content-type": "text/html" });
    response.end("<!doctype html><title>stale server</title>");
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const address = server.address();
  assert.ok(address && typeof address !== "string");
  return { server, port: address.port, state };
}

async function closeServer(server) {
  if (!server.listening) {
    return;
  }
  const closed = once(server, "close");
  server.close();
  await closed;
}

async function terminateChild(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) {
    return;
  }
  const closed = once(child, "close");
  child.kill("SIGTERM");
  await Promise.race([closed, delay(2_000)]);
  if (child.exitCode === null && child.signalCode === null) {
    const killed = once(child, "close");
    child.kill("SIGKILL");
    await killed;
  }
}

const expectedScreenshots = [
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

test("defines the four deterministic documentation captures", () => {
  assert.deepEqual(SCREENSHOTS, expectedScreenshots);
});

test("exposes Vite startup for focused lifecycle tests", () => {
  assert.equal(typeof screenshotScript.startVite, "function");
});

test(
  "rejects a stale server already occupying the requested Vite port",
  { timeout: 8_000 },
  async () => {
    const stale = await startStaleServer();
    const spawned = [];
    let childClosed = false;
    let returnedChild;
    let startupError;
    const spawnProcess = (...args) => {
      const child = spawn(...args);
      child.once("close", () => {
        childClosed = true;
      });
      spawned.push(child);
      return child;
    };

    try {
      try {
        returnedChild = await screenshotScript.startVite({
          port: stale.port,
          spawnProcess,
          timeoutMs: 3_000,
        });
      } catch (error) {
        startupError = error;
      }
    } finally {
      await terminateChild(returnedChild);
      await closeServer(stale.server);
    }

    assert.equal(spawned.length, 1);
    assert.equal(
      stale.state.requests,
      0,
      "readiness must not probe the port before the child emits its marker",
    );
    assert.match(
      startupError instanceof Error ? startupError.message : "",
      /Vite exited before becoming ready/,
    );
    assert.equal(childClosed, true, "startup rejection must await the Vite child");
  },
);

test(
  "terminates and awaits the Vite child after a startup timeout",
  { timeout: 8_000 },
  async () => {
    const stale = await startStaleServer();
    const spawned = [];
    let childClosed = false;
    let returnedChild;
    let startupError;
    const spawnProcess = () => {
      const child = spawn(
        process.execPath,
        ["--eval", "setInterval(() => {}, 1000)"],
        { stdio: ["ignore", "pipe", "pipe"] },
      );
      child.once("close", () => {
        childClosed = true;
      });
      spawned.push(child);
      return child;
    };

    try {
      try {
        returnedChild = await screenshotScript.startVite({
          port: stale.port,
          spawnProcess,
          timeoutMs: 200,
        });
      } catch (error) {
        startupError = error;
      }
    } finally {
      await terminateChild(returnedChild);
      await closeServer(stale.server);
    }

    assert.equal(spawned.length, 1);
    assert.match(
      startupError instanceof Error ? startupError.message : "",
      /Timed out waiting for/,
    );
    assert.equal(childClosed, true, "timeout rejection must await the Vite child");
    assert.ok(
      spawned[0].exitCode !== null || spawned[0].signalCode !== null,
      "the timed-out Vite child must be terminated",
    );
  },
);

test("validates a 1440 by 1000 PNG header", () => {
  const buffer = Buffer.alloc(24);
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).copy(buffer);
  buffer.writeUInt32BE(13, 8);
  buffer.write("IHDR", 12, "ascii");
  buffer.writeUInt32BE(1440, 16);
  buffer.writeUInt32BE(1000, 20);

  assert.deepEqual(validatePngBuffer(buffer), {
    width: 1440,
    height: 1000,
  });
});

test("rejects a PNG with unexpected dimensions", () => {
  const buffer = Buffer.alloc(24);
  Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]).copy(buffer);
  buffer.writeUInt32BE(13, 8);
  buffer.write("IHDR", 12, "ascii");
  buffer.writeUInt32BE(800, 16);
  buffer.writeUInt32BE(600, 20);

  assert.throws(
    () => validatePngBuffer(buffer),
    /expected 1440x1000, received 800x600/,
  );
});
