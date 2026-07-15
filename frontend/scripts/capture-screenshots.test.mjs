import assert from "node:assert/strict";
import { test } from "node:test";

import {
  SCREENSHOTS,
  validatePngBuffer,
} from "./capture-screenshots.mjs";

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
