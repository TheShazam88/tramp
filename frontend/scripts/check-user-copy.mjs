import { lstat, readdir, readFile, stat } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { TextDecoder } from "node:util";
import { fileURLToPath } from "node:url";

const forbidden = /[\u2013\u2014]/;
const utf8Decoder = new TextDecoder("utf-8", { fatal: true });
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
const rootFiles = [];
let hadFilesystemError = false;
let hadUnscannableRoot = false;

function reportFilesystemError(action, path, error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`Unable to ${action} "${path}": ${message}`);
  hadFilesystemError = true;
}

async function collect(path, files) {
  let info;
  try {
    info = await lstat(path);
  } catch (error) {
    reportFilesystemError("inspect", path, error);
    return;
  }

  if (info.isSymbolicLink()) {
    try {
      info = await stat(path);
    } catch (error) {
      reportFilesystemError("inspect symlink target", path, error);
      return;
    }

    if (info.isDirectory()) return;
  }

  if (info.isFile()) {
    files.push(path);
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
    if (entry.name.startsWith(".") || entry.name === "node_modules") {
      continue;
    }
    await collect(resolve(path, entry.name), files);
  }
}

for (const root of roots) {
  const files = [];
  await collect(root, files);
  rootFiles.push({ files, root });
}

const failures = [];
let scannedFileCount = 0;
for (const { files, root } of rootFiles) {
  let rootScannedFileCount = 0;
  for (const file of files) {
    let content;
    try {
      content = await readFile(file);
    } catch (error) {
      reportFilesystemError("read file", file, error);
      continue;
    }

    if (content.includes(0)) continue;

    let text;
    try {
      text = utf8Decoder.decode(content);
    } catch {
      continue;
    }

    scannedFileCount += 1;
    rootScannedFileCount += 1;
    text.split(/\r?\n/).forEach((line, index) => {
      if (forbidden.test(line)) {
        failures.push(`${file}:${index + 1}: ${line.trim()}`);
      }
    });
  }

  if (requested.length && rootScannedFileCount === 0) {
    console.error(
      `No scannable UTF-8 text files found for explicit path "${root}".`,
    );
    hadUnscannableRoot = true;
  }
}

if (failures.length) {
  console.error("User-facing copy contains an em dash or en dash:");
  console.error(failures.join("\n"));
}

if (failures.length || hadFilesystemError || hadUnscannableRoot) {
  process.exitCode = 1;
} else {
  console.log(`Copy check passed across ${scannedFileCount} files.`);
}
