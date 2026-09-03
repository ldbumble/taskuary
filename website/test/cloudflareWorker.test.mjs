import { test } from "node:test";
import assert from "node:assert";
import worker from "../../worker.mjs";

const assets = {
  fetch: async (request) => new Response(`asset:${new URL(request.url).pathname}`),
};

test("the Workers deployment runs the public stats API before static assets", async () => {
  const analytics = await worker.fetch(new Request("https://taskuary.com/api/ev"), { ASSETS: assets });
  assert.equal(analytics.status, 200);
  assert.deepStrictEqual(await analytics.json(), { visits: 0, note: "no D1 binding" });

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

test("everything outside the API stays a static asset", async () => {
  const page = await worker.fetch(new Request("https://taskuary.com/stats"), { ASSETS: assets });
  assert.equal(await page.text(), "asset:/stats");

  const wrongMethod = await worker.fetch(new Request("https://taskuary.com/api/ev", {
    method: "PUT",
  }), { ASSETS: assets });
  assert.equal(wrongMethod.status, 405);
  assert.match(wrongMethod.headers.get("Allow"), /GET/);
});
