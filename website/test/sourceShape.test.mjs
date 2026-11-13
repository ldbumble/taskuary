/* The source card holds text; the executors take lists. A composed filter used to survive right
   up to the moment you touched the box: [["WHENDUE","<=","08/31/2026"]] rendered as
   "WHENDUE,<=,08/31/2026", and the parser dropped that line on the floor. */
import test from "node:test";
import assert from "node:assert/strict";
import { NL, addField, asFilters, filterLines, showValue, toShape, toSources } from "../src/sourceShape.js";

test("a typed filter line becomes a filter", () => {
  assert.deepEqual(asFilters("WHENDUE <= 08/31/2026"), [["WHENDUE", "<=", "08/31/2026"]]);
});

test("the longest operator wins, so >= is never > with a stray =", () => {
  assert.deepEqual(asFilters("TOTALDUE >= 10000"), [["TOTALDUE", ">=", "10000"]]);
});

test("in takes a list", () => {
  assert.deepEqual(asFilters("STATE in Posted, Draft"), [["STATE", "in", ["Posted", "Draft"]]]);
});

test("a composed filter shows as lines and survives a round trip", () => {
  const written = [["WHENDUE", "<=", "08/31/2026"], ["STATE", "in", ["Posted", "Draft"]]];
  const shown = filterLines(written);
  assert.equal(shown, "WHENDUE <= 08/31/2026" + NL + "STATE in Posted, Draft");
  assert.deepEqual(asFilters(shown), written);
});

test("showValue knows a filter list from any other list", () => {
  assert.equal(showValue([["A", "=", "1"]], "filter_lines"), "A = 1");
  assert.equal(showValue(["RECORDNO", "VENDORID"], "csv_list"), "RECORDNO, VENDORID");
  assert.equal(showValue(["a", "b"], "multiline"), "a" + NL + "b");
  assert.equal(showValue({ Authorization: "Bearer x" }, "multiline"), '{"Authorization":"Bearer x"}');
  assert.equal(showValue(undefined, "text"), "");
});

test("toShape turns the boxes into what an executor takes", () => {
  const c = toShape({ type: "intacct", object: "APBILL", fields: "RECORDNO, TOTALDUE",
    filters: "WHENDUE <= 08/31/2026", max_rows: "50", label: "" });
  assert.deepEqual(c.fields, ["RECORDNO", "TOTALDUE"]);
  assert.deepEqual(c.filters, [["WHENDUE", "<=", "08/31/2026"]]);
  assert.equal(c.max_rows, 50);
  assert.equal("label" in c, false);          // blank keys are dropped, not saved as ""
});

test("toShape leaves an already-shaped source alone", () => {
  const src = { type: "intacct", object: "APBILL", fields: ["TOTALDUE"], filters: [["STATE", "=", "Posted"]] };
  assert.deepEqual(toShape(src), src);
});

test("an old single-source config still loads as one card", () => {
  assert.deepEqual(toSources({ type: "intacct", object: "VENDOR", title: "Vendors" }),
    [{ type: "intacct", object: "VENDOR" }]);
});

// the visual audit, 2026-11-13: "every Monday list my open tasks older than a week" - Set up with AI wrote {type: taskuary_data, dataset:
// "tasks"}, the builder dropped the dataset, and its Test said "no Taskuary dataset called ''"
test("a composed report on Taskuary's own tables keeps which table it reads", () => {
  assert.deepEqual(toSources({ type: "taskuary_data", title: "Open tasks older than a week", dataset: "tasks", days: 90, cron: "0 8 * * 1" }),
    [{ type: "taskuary_data", dataset: "tasks", days: 90 }]);
});

test("sources[] wins when it is there", () => {
  const cfg = { type: "assistant", sources: [{ type: "mssql", query: "SELECT 1" }] };
  assert.deepEqual(toSources(cfg), cfg.sources);
});

test("picking a field appends it, whether the box holds a list or typed text", () => {
  assert.deepEqual(addField(["TOTALDUE"], "VENDORID"), ["TOTALDUE", "VENDORID"]);
  assert.deepEqual(addField("TOTALDUE, WHENDUE", "VENDORID"), ["TOTALDUE", "WHENDUE", "VENDORID"]);
  assert.deepEqual(addField("", "VENDORID"), ["VENDORID"]);
  assert.deepEqual(addField(["VENDORID"], "VENDORID"), ["VENDORID"]);   // clicking twice is not two columns
});
