import { test } from "node:test";
import assert from "node:assert";
import worker from "../../worker.mjs";
import { STATS_PASSWORD, STATS_USERNAME } from "../../functions/lib/statsAuth.js";

const assets = {
  fetch: async (request) => new Response(`asset:${new URL(request.url).pathname}`),
};

test("the Workers deployment runs the stats APIs before static assets", async () => {
  const session = await worker.fetch(new Request("https://taskuary.com/api/stats-auth"), { ASSETS: assets });
  assert.equal(session.status, 200);
  assert.deepStrictEqual(await session.json(), { authenticated: false, username: null });

  const denied = await worker.fetch(new Request("https://taskuary.com/api/ev"), { ASSETS: assets });
  assert.equal(denied.status, 401);

  const beacon = await worker.fetch(new Request("https://taskuary.com/api/ev", {
    method: "POST", body: JSON.stringify({ events: [{ kind: "open" }] }),
  }), { ASSETS: assets });
  assert.equal(beacon.status, 204);
});

test("analytics uses the built-in store without a dashboard database binding", async () => {
  let objectName = "", forwarded = "";
  const ANALYTICS_STORE = {
    idFromName(name) { objectName = name; return "object-id"; },
    get(id) {
      assert.equal(id, "object-id");
      return { fetch: async (request) => { forwarded = request.url; return Response.json({ visits: [] }); } };
    },
  };
  const response = await worker.fetch(new Request("https://taskuary.com/api/ev?days=30"), {
    ASSETS: assets, ANALYTICS_STORE,
  });
  assert.equal(response.status, 200);
  assert.equal(objectName, "taskuary.com");
  assert.equal(forwarded, "https://taskuary.com/api/ev?days=30");
});

test("the hardcoded admin account signs in through the Worker", async () => {
  const response = await worker.fetch(new Request("https://taskuary.com/api/stats-auth", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: STATS_USERNAME, password: STATS_PASSWORD }),
  }), { ASSETS: assets });
  assert.equal(response.status, 200);
  assert.match(response.headers.get("Set-Cookie"), /HttpOnly/);
});

test("everything outside the API stays a static asset", async () => {
  const page = await worker.fetch(new Request("https://taskuary.com/stats"), { ASSETS: assets });
  assert.equal(await page.text(), "asset:/stats");

  const wrongMethod = await worker.fetch(new Request("https://taskuary.com/api/stats-auth", {
    method: "PUT",
  }), { ASSETS: assets });
  assert.equal(wrongMethod.status, 405);
  assert.match(wrongMethod.headers.get("Allow"), /POST/);
});
