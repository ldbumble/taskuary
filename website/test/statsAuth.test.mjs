import { test } from "node:test";
import assert from "node:assert";
import { randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { onRequestGet as readSession, onRequestPost as signIn, onRequestDelete as signOut } from "../../functions/api/stats-auth.js";
import { onRequestGet as readEvents, onRequestPost as recordEvents } from "../../functions/api/ev.js";

const root = fileURLToPath(new URL("../../", import.meta.url));
const read = (path) => readFileSync(`${root}${path}`, "utf8");
const authSource = read("functions/lib/statsAuth.js");
const auth = await import(`data:text/javascript;base64,${Buffer.from(authSource).toString("base64")}`);
const configured = () => ({ STATS_PASSWORD: randomBytes(24).toString("hex"), STATS_SESSION_SECRET: randomBytes(32).toString("hex") });
const loginRequest = (env, username = "admin", password = env.STATS_PASSWORD) => new Request("https://taskuary.com/api/stats-auth", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ username, password }),
});
const cookieRequest = (session, path = "api/ev") => new Request(`https://taskuary.com/${path}`, {
  headers: { Cookie: auth.setStatsCookie(session).split(";")[0] },
});

test("missing or incomplete secrets cannot authenticate or issue sessions", async () => {
  const env = configured();
  for (const missing of [{}, { STATS_PASSWORD: env.STATS_PASSWORD }, { STATS_SESSION_SECRET: env.STATS_SESSION_SECRET },
    { ...env, STATS_PASSWORD: "" }, { ...env, STATS_SESSION_SECRET: "short" }, { ...env, STATS_SESSION_SECRET: 32 }]) {
    assert.equal(auth.statsCredentials(missing), null);
    assert.equal(await auth.credentialsMatch("admin", env.STATS_PASSWORD, missing), false);
    assert.equal(await auth.verifyStatsSession("invented.cookie", missing), false);
    await assert.rejects(auth.createStatsSession("admin", missing), /not configured/);
    const response = await signIn({ request: loginRequest(env), env: missing });
    assert.equal(response.status, 503);
    assert.equal(response.headers.get("Set-Cookie"), null);
  }
  assert.doesNotMatch(authSource, /export const STATS_PASSWORD\s*=/);
});

test("the stats password check accepts the configured pair and optional username", async () => {
  const env = configured();
  assert.equal(auth.statsCredentials(env).username, "admin");
  assert.equal(await auth.credentialsMatch("admin", env.STATS_PASSWORD, env), true);
  assert.equal(await auth.credentialsMatch("admin", "wrong", env), false);
  assert.equal(await auth.credentialsMatch("someone-else", env.STATS_PASSWORD, env), false);
  const renamed = { ...env, STATS_USERNAME: "operator" };
  assert.equal(await auth.credentialsMatch("operator", env.STATS_PASSWORD, renamed), true);
  assert.equal(await auth.credentialsMatch("admin", env.STATS_PASSWORD, renamed), false);
});

test("session secret minimum is measured in UTF-8 bytes", () => {
  const env = configured();
  assert.equal(auth.statsCredentials({ ...env, STATS_SESSION_SECRET: "x".repeat(31) }), null);
  assert.ok(auth.statsCredentials({ ...env, STATS_SESSION_SECRET: "x".repeat(32) }));
  assert.ok(auth.statsCredentials({ ...env, STATS_SESSION_SECRET: "\u00e9".repeat(16) }));
});

test("stats sessions reject tampering and expire at the boundary", async () => {
  const env = configured(), now = Date.UTC(2026, 8, 2, 12);
  const session = await auth.createStatsSession("admin", env, now);
  assert.equal(await auth.verifyStatsSession(session, env, now + 1000), true);
  const [body, signature] = session.split(".");
  const tampered = `${body}.${signature[0] === "a" ? "b" : "a"}${signature.slice(1)}`;
  assert.equal(await auth.verifyStatsSession(tampered, env, now), false);
  assert.equal(await auth.verifyStatsSession(`${session}.extra`, env, now), false);
  assert.equal(await auth.verifyStatsSession(session, env, now + auth.SESSION_SECONDS * 1000), false);
  const cookie = auth.setStatsCookie(session);
  assert.match(cookie, /HttpOnly/);
  assert.match(cookie, /Secure/);
  assert.match(cookie, /SameSite=Strict/);
  const currentSession = await auth.createStatsSession("admin", env);
  assert.equal(await auth.hasStatsSession(cookieRequest(currentSession), env), true);
});

test("rotating either secret or the username invalidates every old session", async () => {
  const env = configured();
  const session = await auth.createStatsSession("admin", env);
  assert.equal(await auth.verifyStatsSession(session, env), true);
  for (const rotated of [{ ...env, STATS_PASSWORD: randomBytes(24).toString("hex") },
    { ...env, STATS_SESSION_SECRET: randomBytes(32).toString("hex") }, { ...env, STATS_USERNAME: "operator" }, {}])
    assert.equal(await auth.verifyStatsSession(session, rotated), false);
});

test("Pages login validates credentials and returns only session metadata", async () => {
  const env = { ...configured(), STATS_USERNAME: "operator" };
  const rejected = await signIn({ request: loginRequest(env, "operator", "wrong"), env });
  assert.equal(rejected.status, 401);
  const malformed = await signIn({ request: new Request("https://taskuary.com/api/stats-auth", { method: "POST", body: "{" }), env });
  assert.equal(malformed.status, 400);
  const response = await signIn({ request: loginRequest(env, "operator"), env });
  assert.equal(response.status, 200);
  assert.deepStrictEqual(await response.json(), { authenticated: true, username: "operator" });
  assert.equal(response.headers.get("Cache-Control"), "no-store");
  const request = new Request("https://taskuary.com/api/stats-auth", { headers: { Cookie: response.headers.get("Set-Cookie").split(";")[0] } });
  assert.deepStrictEqual(await (await readSession({ request, env })).json(), { authenticated: true, username: "operator" });
  assert.deepStrictEqual(await (await readSession({ request, env: {} })).json(), { authenticated: false, username: null });
  assert.match((await signOut()).headers.get("Set-Cookie"), /Max-Age=0/);
});

test("Pages D1 readers require configuration and a session while collection stays public", async () => {
  let reads = 0, writes = 0;
  const db = { prepare: () => ({ bind() { return this; }, all: async () => { reads++; return { results: [] }; } }),
    batch: async (rows) => { writes += rows.length; } };
  const env = { ...configured(), DEMO_EVENTS: db }, session = await auth.createStatsSession("admin", env);
  for (const [request, readerEnv] of [[new Request("https://taskuary.com/api/ev"), env], [cookieRequest(session), { DEMO_EVENTS: db }]]) {
    assert.equal((await readEvents({ request, env: readerEnv })).status, 401);
    assert.equal(reads, 0);
  }
  assert.equal((await readEvents({ request: cookieRequest(session), env })).status, 200);
  assert.equal(reads, 7);
  assert.equal((await recordEvents({ request: new Request("https://taskuary.com/api/ev", {
    method: "POST", body: JSON.stringify({ sid: "invented-session", events: [{ kind: "open" }] }),
  }), env: { DEMO_EVENTS: db } })).status, 204);
  assert.equal(writes, 1);
});

test("the stats page uses a normal login and never stores or sends the old token", () => {
  const page = read("site/stats.html"), reader = read("functions/api/ev.js");
  assert.match(page, /Admin sign in/);
  assert.match(page, /autocomplete="username"/);
  assert.match(page, /autocomplete="current-password"/);
  assert.match(page, /fetch\('\/api\/stats-auth'/);
  assert.match(page, /stats login service is not deployed/);
  assert.match(page, /if \(!r\.ok\) throw new Error\('HTTP ' \+ r\.status\)/);
  assert.doesNotMatch(page, /tq_stats_token|localStorage|[?&]token=/);
  assert.match(reader, /hasStatsSession\(request, env\)/);
  assert.doesNotMatch(reader, /searchParams\.get\("token"\)/);
});
