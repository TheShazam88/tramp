import { readdir, readFile, stat } from "node:fs/promises";
import { resolve } from "node:path";

const forbidden = /[\u2013\u2014]/;
const defaults = ["src", "index.html"];
const requested = process.argv.slice(2);
const roots = (requested.length ? requested : defaults).map((item) => resolve(item));
const files = [];

async function collect(path) {
  const info = await stat(path);
  if (info.isFile()) {
    files.push(path);
    return;
  }
  if (!info.isDirectory()) return;

  const entries = await readdir(path, { withFileTypes: true });
  for (const entry of entries) {
    if (
      entry.isDirectory() &&
      (entry.name.startsWith(".") || entry.name === "node_modules")
    ) {
      continue;
    }
    await collect(resolve(path, entry.name));
  }
}

for (const root of roots) await collect(root);

const failures = [];
for (const file of files) {
  const text = await readFile(file, "utf8");
  text.split(/\r?\n/).forEach((line, index) => {
    if (forbidden.test(line)) {
      failures.push(`${file}:${index + 1}: ${line.trim()}`);
    }
  });
}

if (failures.length) {
  console.error("User-facing copy contains an em dash or en dash:");
  console.error(failures.join("\n"));
  process.exit(1);
}

console.log(`Copy check passed across ${files.length} files.`);
