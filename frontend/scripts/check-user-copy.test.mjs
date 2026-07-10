import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import {
  mkdir,
  mkdtemp,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { promisify } from "node:util";
import { fileURLToPath } from "node:url";

const execFileAsync = promisify(execFile);
const scriptsDirectory = dirname(fileURLToPath(import.meta.url));
const frontendDirectory = resolve(scriptsDirectory, "..");
const scriptPath = resolve(scriptsDirectory, "check-user-copy.mjs");

async function makeFixture(t) {
  const directory = await mkdtemp(join(tmpdir(), "check-user-copy-"));
  t.after(() => rm(directory, { force: true, recursive: true }));
  return directory;
}

async function runCopyCheck(...paths) {
  try {
    const { stderr, stdout } = await execFileAsync(
      process.execPath,
      [scriptPath, ...paths],
      {
        cwd: frontendDirectory,
        encoding: "utf8",
        timeout: 5_000,
      },
    );
    return { code: 0, stderr, stdout };
  } catch (error) {
    return {
      code: typeof error.code === "number" ? error.code : null,
      signal: error.signal,
      stderr: error.stderr ?? "",
      stdout: error.stdout ?? "",
    };
  }
}

test("reports an em dash with its one-based line", async (t) => {
  const directory = await makeFixture(t);
  const file = join(directory, "copy.txt");
  await writeFile(file, "clean\nbad — copy\n", "utf8");

  const result = await runCopyCheck(file);

  assert.equal(result.code, 1);
  assert.match(result.stderr, /User-facing copy contains/);
  assert.ok(result.stderr.includes(`${file}:2: bad — copy`));
});

test("reports an en dash with its one-based line", async (t) => {
  const directory = await makeFixture(t);
  const file = join(directory, "copy.txt");
  await writeFile(file, "bad – copy\n", "utf8");

  const result = await runCopyCheck(file);

  assert.equal(result.code, 1);
  assert.ok(result.stderr.includes(`${file}:1: bad – copy`));
});

test("passes clean UTF-8 text", async (t) => {
  const directory = await makeFixture(t);
  const file = join(directory, "copy.txt");
  await writeFile(file, "clean copy\n", "utf8");

  const result = await runCopyCheck(file);

  assert.equal(result.code, 0);
  assert.match(result.stdout, /Copy check passed across 1 files\./);
});

test("scans unsupported-extension text inside an explicit directory", async (t) => {
  const directory = await makeFixture(t);
  const file = join(directory, "copy.custom");
  await writeFile(file, "bad — copy\n", "utf8");

  const result = await runCopyCheck(directory);

  assert.equal(result.code, 1);
  assert.ok(result.stderr.includes(`${file}:1: bad — copy`));
});

test("scans an explicit symlink to a UTF-8 text file", async (t) => {
  const directory = await makeFixture(t);
  const target = join(directory, "target.custom");
  const link = join(directory, "copy-link");
  await writeFile(target, "bad — copy\n", "utf8");
  await symlink(target, link);

  const result = await runCopyCheck(link);

  assert.equal(result.code, 1);
  assert.ok(result.stderr.includes(`${link}:1: bad — copy`));
});

test("scans symlinks to files inside an explicit directory", async (t) => {
  const directory = await makeFixture(t);
  const scanDirectory = join(directory, "scan");
  const target = join(directory, "target.custom");
  const link = join(scanDirectory, "copy-link");
  await mkdir(scanDirectory);
  await writeFile(target, "bad — copy\n", "utf8");
  await symlink(target, link);

  const result = await runCopyCheck(scanDirectory);

  assert.equal(result.code, 1);
  assert.ok(result.stderr.includes(`${link}:1: bad — copy`));
});

test("rejects an empty explicit directory", async (t) => {
  const directory = await makeFixture(t);

  const result = await runCopyCheck(directory);

  assert.equal(result.code, 1);
  assert.match(result.stderr, /No scannable UTF-8 text files found/);
  assert.ok(result.stderr.includes(directory));
});

test("rejects an explicit binary file", async (t) => {
  const directory = await makeFixture(t);
  const file = join(directory, "copy.bin");
  await writeFile(file, Buffer.from([0x00, 0xff, 0x01]));

  const result = await runCopyCheck(file);

  assert.equal(result.code, 1);
  assert.match(result.stderr, /No scannable UTF-8 text files found/);
  assert.ok(result.stderr.includes(file));
});

test("skips hidden descendants", async (t) => {
  const directory = await makeFixture(t);
  const hiddenDirectory = join(directory, ".hidden");
  await mkdir(hiddenDirectory);
  await writeFile(join(directory, "visible.txt"), "clean copy\n", "utf8");
  await writeFile(join(directory, ".hidden.txt"), "bad — copy\n", "utf8");
  await writeFile(join(hiddenDirectory, "copy.txt"), "bad — copy\n", "utf8");

  const result = await runCopyCheck(directory);

  assert.equal(result.code, 0);
  assert.match(result.stdout, /Copy check passed across 1 files\./);
});

test("skips node_modules descendants", async (t) => {
  const directory = await makeFixture(t);
  const dependencies = join(directory, "node_modules");
  await mkdir(dependencies);
  await writeFile(join(directory, "visible.txt"), "clean copy\n", "utf8");
  await writeFile(join(dependencies, "copy.txt"), "bad — copy\n", "utf8");

  const result = await runCopyCheck(directory);

  assert.equal(result.code, 0);
  assert.match(result.stdout, /Copy check passed across 1 files\./);
});

test("does not follow symlinks to directories", async (t) => {
  const directory = await makeFixture(t);
  await writeFile(join(directory, "visible.txt"), "clean copy\n", "utf8");
  await symlink(directory, join(directory, "loop"));

  const result = await runCopyCheck(directory);

  assert.equal(result.code, 0);
  assert.equal(result.signal, undefined);
  assert.match(result.stdout, /Copy check passed across 1 files\./);
});
