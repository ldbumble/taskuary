import { test } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (path) => readFileSync(`${root}${path}`, "utf8");
const authSource = read("functions/lib/statsAuth.js");
const auth = await import(`data:text/javascript;base64,${Buffer.from(authSource).toString("base64")}`);

test("stats credentials are the explicit hardcoded admin pair", () => {
  assert.deepStrictEqual(auth.statsCredentials(), {
    username: auth.STATS_USERNAME, password: auth.STATS_PASSWORD,
  });
});

test("the stats password check accepts only the configured pair", async () => {
  assert.equal(await auth.credentialsMatch(auth.STATS_USERNAME, auth.STATS_PASSWORD), true);
  assert.equal(await auth.credentialsMatch(auth.STATS_USERNAME, "wrong"), false);
  assert.equal(await auth.credentialsMatch("someone-else", auth.STATS_PASSWORD), false);
});

test("stats sessions are signed, expire, and travel only in a secure HttpOnly cookie", async () => {
  const now = Date.UTC(2026, 8, 2, 12);
  const session = await auth.createStatsSession(auth.STATS_USERNAME, now);
  assert.equal(await auth.verifyStatsSession(session, now + 1000), true);
  assert.equal(await auth.verifyStatsSession(`${session.slice(0, -1)}x`, now + 1000), false);
  assert.equal(await auth.verifyStatsSession(session, now + (auth.SESSION_SECONDS + 1) * 1000), false);
  const cookie = auth.setStatsCookie(session);
  assert.match(cookie, /HttpOnly/);
  assert.match(cookie, /Secure/);
  assert.match(cookie, /SameSite=Strict/);
  const request = new Request("https://taskuary.com/api/ev", { headers: { Cookie: cookie.split(";")[0] } });
  assert.equal(await auth.hasStatsSession(request), true);
});

test("the stats page uses a normal login and never stores or sends the old token", () => {
  const page = read("site/stats.html");
  const reader = read("functions/api/ev.js");
  assert.match(page, /Admin sign in/);
  assert.match(page, /autocomplete="username"/);
  assert.match(page, /autocomplete="current-password"/);
  assert.match(page, /fetch\('\/api\/stats-auth'/);
  assert.doesNotMatch(page, /tq_stats_token|localStorage|[?&]token=/);
  assert.match(reader, /hasStatsSession/);
  assert.doesNotMatch(reader, /searchParams\.get\("token"\)/);
});
