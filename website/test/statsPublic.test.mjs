import { test } from "node:test";
import assert from "node:assert";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (path) => readFileSync(`${root}${path}`, "utf8");

test("analytics is public and contains no credential machinery", () => {
  const page = read("site/stats.html");
  const reader = read("functions/api/ev.js");
  const worker = read("worker.mjs");
  assert.doesNotMatch(page, /password|Admin sign in|Sign out|stats-auth/i);
  assert.doesNotMatch(reader, /hasStatsSession|statsAuth|401/);
  assert.doesNotMatch(worker, /stats-auth|signIn|signOut/);
  assert.equal(existsSync(`${root}functions/lib/statsAuth.js`), false);
  assert.equal(existsSync(`${root}functions/api/stats-auth.js`), false);
});

test("the public dashboard presents decisions instead of raw event totals", () => {
  const page = read("site/stats.html");
  const reader = read("functions/api/ev.js");
  assert.match(page, /Conversion path/);
  assert.match(page, /Engaged demo/);
  assert.match(page, /What people explored/);
  assert.match(page, /Recent sessions/);
  assert.match(reader, /converted/);
  assert.match(reader, /referrers, countries, devices, recent/);
});
