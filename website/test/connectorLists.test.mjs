import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";
import { readLists, takeLists } from "../src/connectorLists.js";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

// A COLD LINK TO CONNECTIONS ASKS FOR ITS LISTS WITH THE PAGE (the 2026-10-19 UI walk, G8): the reads went out only once two lazy
// chunks had come in and Connections mounted, ~1.4 s after the page was asked for. They go out when the address is read now.
test("the lists read ahead are asked once, spent once by the view's first load, and never stand in for a later load", async () => {
  const calls = [], api = { get: async (u) => { calls.push(u); return { data: { data: [u] } }; } };
  const p = readLists(api); readLists(api);
  assert.deepEqual(calls, ["/api/connectors", "/api/sources", "/api/report-types"], "one read of each, however often it is asked");
  assert.equal(takeLists(), p, "the view's first load takes the read ahead");
  assert.equal(takeLists(), null, "...once: a reload after a save reads anew");
});

test("the address and the sidebar both start the read, and Connections' first load takes it", () => {
  assert.match(src("TaskHubPage.jsx"), /const readAhead = \(req\) => \{ if \(req\?\.kind === "browse" && req\.area === "connections"\) readLists\(api\); \};/);
  assert.match(src("TaskHubPage.jsx"), /canvasRequestFromHash\(window\.location\.hash \|\| "", 1\); readAhead\(r\);/);
  assert.match(src("AssistantView.jsx"), /if \(area === "connections"\) readLists\(api\);/);
  assert.match(src("ConnectorsView.jsx"), /await \(takeLists\(\) \|\| Promise\.all\(\[api\.get\("\/api\/connectors"\), api\.get\("\/api\/sources"\), api\.get\("\/api\/report-types"\)\]\)\)/);
});
