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
