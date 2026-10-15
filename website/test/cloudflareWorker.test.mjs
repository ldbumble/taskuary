import { test } from "node:test";
import assert from "node:assert";
import worker, { StatsStore } from "../../worker.mjs";

// The stats are public to read, like they are to write (2026-10-13): no login, no cookie, no secret.
const assets = { fetch: async (request) => new Response(`asset:${new URL(request.url).pathname}`) };
const storage = () => {
  const counts = { reads: 0, writes: 0 };
  return { counts, ctx: { storage: { sql: { exec(query) {
    if (query.startsWith("SELECT")) counts.reads++;
    if (query.startsWith("INSERT")) counts.writes++;
    return [];
  } } } } };
};

test("the Workers deployment runs the stats API before static assets, and nobody signs in to read it", async () => {
  const read = await worker.fetch(new Request("https://taskuary.com/api/ev"), { ASSETS: assets });
  assert.equal(read.status, 200);
  assert.equal((await read.json()).note, "no D1 binding");
  const beacon = await worker.fetch(new Request("https://taskuary.com/api/ev", {
    method: "POST", body: JSON.stringify({ events: [{ kind: "open" }] }),
  }), { ASSETS: assets });
  assert.equal(beacon.status, 204);
  assert.equal((await worker.fetch(new Request("https://taskuary.com/api/stats-auth"), { ASSETS: assets })).status, 200);
  assert.equal(await (await worker.fetch(new Request("https://taskuary.com/api/stats-auth"), { ASSETS: assets })).text(), "asset:/api/stats-auth");
});

test("a read forwards to the configured Durable Object", async () => {
  const env = { ASSETS: assets }, backing = storage(), object = new StatsStore(backing.ctx, env);
  let objectName = "", forwarded = "";
  env.ANALYTICS_STORE = {
    idFromName(name) { objectName = name; return "object-id"; },
    get(id) { assert.equal(id, "object-id"); return { fetch(request) { forwarded = request.url; return object.fetch(request); } }; },
  };
  const response = await worker.fetch(new Request("https://taskuary.com/api/ev?days=30"), env);
  assert.equal(response.status, 200);
  assert.equal(objectName, "taskuary.com");
  assert.equal(forwarded, "https://taskuary.com/api/ev?days=30");
  assert.equal((await response.json()).days, 30);
  assert.equal(backing.counts.reads, 8);
});

test("the Durable Object reads and records with no configuration at all", async () => {
  const backing = storage(), object = new StatsStore(backing.ctx);
  assert.equal((await object.fetch(new Request("https://taskuary.com/api/ev"))).status, 200);
  assert.equal(backing.counts.reads, 8);
  const beacon = await object.fetch(new Request("https://taskuary.com/api/ev", {
    method: "POST", body: JSON.stringify({ sid: "invented-session", events: [{ kind: "open" }] }),
  }));
  assert.equal(beacon.status, 204);
  assert.equal(backing.counts.writes, 1);
});

test("the compatibility D1 binding is read the same way", async () => {
  let reads = 0;
  const DEMO_EVENTS = { prepare: () => ({ bind() { return this; }, all: async () => { reads++; return { results: [] }; } }) };
  assert.equal((await worker.fetch(new Request("https://taskuary.com/api/ev"), { ASSETS: assets, DEMO_EVENTS })).status, 200);
  assert.equal(reads, 8);
});

test("everything outside the API stays a static asset and unsupported methods fail", async () => {
  const page = await worker.fetch(new Request("https://taskuary.com/stats"), { ASSETS: assets });
  assert.equal(await page.text(), "asset:/stats");
  const response = await worker.fetch(new Request("https://taskuary.com/api/ev", { method: "PUT" }), { ASSETS: assets });
  assert.equal(response.status, 405);
  assert.match(response.headers.get("Allow"), /POST/);
});

test("the stats page draws no sign-in and reads the counts as it opens", async () => {
  const fs = await import("node:fs");
  const page = fs.readFileSync(new URL("../../site/stats.html", import.meta.url), "utf8");
  assert.doesNotMatch(page, /stats-auth|password|Sign in|loginForm/i);
  assert.match(page, /\nload\(30\);\n<\/script>/);                 // the dashboard reads the last 30 days as it opens
});
