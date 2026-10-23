import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";
import { jsonRows } from "../src/reportRows.js";

test("a data report's JSON lines read as rows; anything else stays text", () => {
  assert.deepEqual(jsonRows('{"site": "Lakeview", "headcount": 112}\n{"site": "Riverside", "headcount": 98}\n'),
    [{ site: "Lakeview", headcount: 112 }, { site: "Riverside", headcount: 98 }]);
  assert.equal(jsonRows("Three things came in.\n{\"a\": 1}"), null);
  assert.equal(jsonRows('{"nested": {"a": 1}}'), null);
  assert.equal(jsonRows(""), null);
});

// a new report started on SQL Server whether or not there was one, and its warning was a sentence with no way to act
// (the UX walk, 2026-10-22): it starts on the first connected source, and the warning is a button to that card
test("a new report starts on the first connected source, and an unconnected one is a button to its card", async () => {
  const { firstConnected } = await import("../src/sourceShape.js");
  const ok = { LastSyncAt: "2026-10-22 09:00", LastError: null };
  assert.equal(firstConnected(["mssql", "s3_object", "rss"], [{ Type: "aws", ...ok }], { s3_object: "aws" }), "s3_object");
  assert.equal(firstConnected(["mssql", "rss"], [{ Type: "mssql", LastSyncAt: "x", LastError: "login failed" }]), null);
  assert.equal(firstConnected(["mssql"], [{ Type: "mssql" }]), null);   // never read: not connected
  const s = readFileSync(fileURLToPath(new URL("../src/ReportsView.jsx", import.meta.url)), "utf8");
  assert.match(s, /\.\.\.\(live \? \{ type: live \} : \{\}\), \.\.\.\(draft \|\| \{\}\) \}/);
  assert.match(s, /onClick=\{\(\) => openAppLink\(`#connector=\$\{cardType\}`\)\}/);
  assert.match(s, /\{btnLabel\("fix", "card"\)\}/);
  assert.doesNotMatch(s, /in Connections first`/);
  const { label } = await import("../src/buttons.js");
  assert.equal(label("fix", "card"), "Open the card");
});
