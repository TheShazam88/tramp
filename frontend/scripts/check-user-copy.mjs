import { lstat, readdir, readFile } from "node:fs/promises";
import { dirname, extname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const forbidden = /[\u2013\u2014]/;
const textExtensions = new Set([
  ".ts",
  ".tsx",
  ".js",
  ".jsx",
  ".css",
  ".html",
  ".svg",
  ".json",
  ".md",
]);
const frontendDirectory = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "..",
);
const defaults = [
  resolve(frontendDirectory, "src"),
  resolve(frontendDirectory, "index.html"),
];
const requested = process.argv.slice(2);
const roots = requested.length
  ? requested.map((item) => resolve(item))
  : defaults;
const files = [];
let hadFilesystemError = false;

function reportFilesystemError(action, path, error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`Unable to ${action} "${path}": ${message}`);
  hadFilesystemError = true;
}

async function collect(path, { explicitFile = false } = {}) {
  let info;
  try {
    info = await lstat(path);
  } catch (error) {
    reportFilesystemError("inspect", path, error);
    return;
  }

  if (info.isSymbolicLink()) return;
  if (info.isFile()) {
    if (explicitFile || textExtensions.has(extname(path).toLowerCase())) {
      files.push(path);
    }
    return;
  }
  if (!info.isDirectory()) return;

  let entries;
  try {
    entries = await readdir(path, { withFileTypes: true });
  } catch (error) {
    reportFilesystemError("read directory", path, error);
    return;
  }

  for (const entry of entries) {
    if (
      entry.isSymbolicLink() ||
      entry.name.startsWith(".") ||
      entry.name === "node_modules"
    ) {
      continue;
    }
    await collect(resolve(path, entry.name));
  }
}

for (const root of roots) {
  await collect(root, { explicitFile: requested.length > 0 });
}

const failures = [];
let scannedFileCount = 0;
for (const file of files) {
  let content;
  try {
    content = await readFile(file);
  } catch (error) {
    reportFilesystemError("read file", file, error);
    continue;
  }

  if (content.includes(0)) continue;

  scannedFileCount += 1;
  const text = content.toString("utf8");
  text.split(/\r?\n/).forEach((line, index) => {
    if (forbidden.test(line)) {
      failures.push(`${file}:${index + 1}: ${line.trim()}`);
    }
  });
}

if (failures.length) {
  console.error("User-facing copy contains an em dash or en dash:");
  console.error(failures.join("\n"));
}

if (failures.length || hadFilesystemError) {
  process.exitCode = 1;
} else {
  console.log(`Copy check passed across ${scannedFileCount} files.`);
}
