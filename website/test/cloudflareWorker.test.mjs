import { test } from "node:test";
import assert from "node:assert";
import { randomBytes } from "node:crypto";
import worker, { StatsStore } from "../../worker.mjs";
import { createStatsSession, setStatsCookie } from "../../functions/lib/statsAuth.js";

const assets = { fetch: async (request) => new Response(`asset:${new URL(request.url).pathname}`) };
const configured = () => ({ STATS_PASSWORD: randomBytes(24).toString("hex"), STATS_SESSION_SECRET: randomBytes(32).toString("hex") });
const authorized = (session, url = "https://taskuary.com/api/ev?days=30") => new Request(url, { headers: { Cookie: setStatsCookie(session).split(";")[0] } });
const storage = () => {
  const counts = { reads: 0, writes: 0 };
  return { counts, ctx: { storage: { sql: { exec(query) {
    if (query.startsWith("SELECT")) counts.reads++;
    if (query.startsWith("INSERT")) counts.writes++;
    return [];
  } } } } };
};

test("the Workers deployment runs the stats APIs before static assets", async () => {
  const session = await worker.fetch(new Request("https://taskuary.com/api/stats-auth"), { ASSETS: assets });
  assert.equal(session.status, 200);
  assert.deepStrictEqual(await session.json(), { authenticated: false, username: null });
  assert.equal((await worker.fetch(new Request("https://taskuary.com/api/ev"), { ASSETS: assets })).status, 401);
  const login = await worker.fetch(new Request("https://taskuary.com/api/stats-auth", { method: "POST", body: "{}" }), { ASSETS: assets });
  assert.equal(login.status, 503);
  assert.equal(login.headers.get("Set-Cookie"), null);
  const beacon = await worker.fetch(new Request("https://taskuary.com/api/ev", {
    method: "POST", body: JSON.stringify({ events: [{ kind: "open" }] }),
  }), { ASSETS: assets });
  assert.equal(beacon.status, 204);
});

test("the Worker rejects readers before forwarding to its built-in store", async () => {
  const env = { ...configured(), ASSETS: assets };
  const session = await createStatsSession("admin", env);
  let forwarded = 0;
  const ANALYTICS_STORE = { idFromName() { forwarded++; return "object-id"; }, get() { throw new Error("anonymous request reached analytics"); } };
  assert.equal((await worker.fetch(new Request("https://taskuary.com/api/ev"), { ...env, ANALYTICS_STORE })).status, 401);
  assert.equal((await worker.fetch(authorized(session), { ASSETS: assets, ANALYTICS_STORE })).status, 401);
  assert.equal((await worker.fetch(authorized(session), { ...env, STATS_PASSWORD: randomBytes(24).toString("hex"), ANALYTICS_STORE })).status, 401);
  assert.equal(forwarded, 0);
});

test("authenticated analytics forwards to the configured Durable Object", async () => {
  const env = { ...configured(), ASSETS: assets }, backing = storage(), object = new StatsStore(backing.ctx, env);
  let objectName = "", forwarded = "";
  env.ANALYTICS_STORE = {
    idFromName(name) { objectName = name; return "object-id"; },
    get(id) { assert.equal(id, "object-id"); return { fetch(request) { forwarded = request.url; return object.fetch(request); } }; },
  };
  const response = await worker.fetch(authorized(await createStatsSession("admin", env)), env);
  assert.equal(response.status, 200);
  assert.equal(objectName, "taskuary.com");
  assert.equal(forwarded, "https://taskuary.com/api/ev?days=30");
  assert.equal((await response.json()).days, 30);
  assert.equal(backing.counts.reads, 7);
});

test("Durable Object readers independently require secrets and a valid cookie", async () => {
  const env = configured(), session = await createStatsSession("admin", env), backing = storage();
  const unconfigured = new StatsStore(backing.ctx);
  assert.equal((await unconfigured.fetch(authorized(session))).status, 401);
  const object = new StatsStore(backing.ctx, env);
  assert.equal((await object.fetch(new Request("https://taskuary.com/api/ev"))).status, 401);
  assert.equal(backing.counts.reads, 0);
  assert.equal((await object.fetch(authorized(session))).status, 200);
  assert.equal(backing.counts.reads, 7);
  const beacon = await unconfigured.fetch(new Request("https://taskuary.com/api/ev", {
    method: "POST", body: JSON.stringify({ sid: "invented-session", events: [{ kind: "open" }] }),
  }));
  assert.equal(beacon.status, 204);
  assert.equal(backing.counts.writes, 1);
});

test("configured Worker login also authorizes the compatibility D1 reader", async () => {
  let reads = 0;
  const DEMO_EVENTS = { prepare: () => ({ bind() { return this; }, all: async () => { reads++; return { results: [] }; } }) };
  const env = { ...configured(), STATS_USERNAME: "operator", ASSETS: assets, DEMO_EVENTS };
  const response = await worker.fetch(new Request("https://taskuary.com/api/stats-auth", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: env.STATS_USERNAME, password: env.STATS_PASSWORD }),
  }), env);
  assert.equal(response.status, 200);
  assert.match(response.headers.get("Set-Cookie"), /HttpOnly/);
  const request = new Request("https://taskuary.com/api/ev", { headers: { Cookie: response.headers.get("Set-Cookie").split(";")[0] } });
  assert.equal((await worker.fetch(request, env)).status, 200);
  assert.equal(reads, 7);
  assert.equal((await worker.fetch(request, { ...env, STATS_SESSION_SECRET: randomBytes(32).toString("hex") })).status, 401);
  assert.equal(reads, 7);
});

test("everything outside the API stays a static asset and unsupported methods fail", async () => {
  const page = await worker.fetch(new Request("https://taskuary.com/stats"), { ASSETS: assets });
  assert.equal(await page.text(), "asset:/stats");
  for (const path of ["stats-auth", "ev"]) {
    const response = await worker.fetch(new Request(`https://taskuary.com/api/${path}`, { method: "PUT" }), { ASSETS: assets });
    assert.equal(response.status, 405);
    assert.match(response.headers.get("Allow"), /POST/);
  }
});
