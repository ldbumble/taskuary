// EVERY DASHBOARD IS CONFIGURABLE (the owner, 2026-10-24: "it should be configurable, with a new tab in Reports named Dashboards with
// sources layout like reports"): its sources are a report's source cards, its components are cards beside them, and the built-in
// Taskuary at a glance is an ordinary row, opened and edited in the same editor as any other. The conversions are in setup.js.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { BINDS, freshKey, orphans, sigOf, whereOf, whereText, windowOf, withField, withKind, withWindow } from "../src/dashboard/setup.js";
import { DASH } from "../src/words.js";

const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");
const words = JSON.parse(readFileSync(new URL("../../taskuary/words.json", import.meta.url), "utf8"));

test("a where is typed the way it reads, and only whole pairs are kept", () => {
  assert.deepEqual(whereOf("state=open, kind = reply"), { state: "open", kind: "reply" });
  assert.equal(whereOf("state="), undefined);
  assert.equal(whereOf(""), undefined);
  assert.equal(whereText({ state: "open", kind: "reply" }), "state=open, kind=reply");
  assert.deepEqual(whereOf(whereText({ status: "open" })), { status: "open" });
});

test("a component's own window: the page's range, a fixed window, or what is true now", () => {
  const c = { kind: "progress", target: 15 };
  assert.equal(windowOf(c), "");
  assert.deepEqual(withWindow(c, "7"), { ...c, range: 7 });
  assert.deepEqual(withWindow(c, "now"), { ...c, range: false });
  assert.equal(windowOf({ range: false }), "now");
  assert.deepEqual(withWindow({ ...c, range: 7 }, ""), c, "the page's range is no key at all");
  for (const v of ["", "7", "30", "90", "now"]) assert.ok(DASH.windows[v], `words.json dashboard.windows.${v}`);
});

test("a field set to nothing is a key gone; a changed preset keeps what every kind reads", () => {
  assert.deepEqual(withField({ kind: "bar", x: "kind", limit: 8 }, "limit", ""), { kind: "bar", x: "kind" });
  assert.deepEqual(withField({ kind: "table" }, "columns", []), { kind: "table" });
  const bar = { kind: "bar", title: "Open work", source: "tasks", x: "kind", where: { state: "open" }, range: false, agg: "count", limit: 6 };
  assert.deepEqual(withKind(bar, "stat"), { kind: "stat", title: "Open work", source: "tasks", where: { state: "open" }, range: false, agg: "count" });
  assert.deepEqual(withKind(bar, "list"), { kind: "list", title: "Open work", source: "tasks", where: { state: "open" }, range: false });
  for (const k of Object.keys(BINDS)) assert.ok(DASH.kinds[k], `words.json dashboard.kinds.${k}`);
  for (const f of new Set(Object.values(BINDS).flat())) assert.ok(DASH.fields[f], `words.json dashboard.fields.${f}`);
});

test("a new source gets a key no other wears; a component reading a gone source is said before Save", () => {
  assert.equal(freshKey([{ key: "mail" }, { key: "s3" }]), "s4");
  assert.equal(freshKey([{ key: "s2" }, { key: "s3" }]), "s4");
  const spec = { sources: [{ key: "mail" }], components: [{ title: "In", source: "mail" }, { title: "Gone", source: "tasks" }] };
  assert.deepEqual(orphans(spec).map((c) => c.title), ["Gone"]);
  assert.notEqual(sigOf(spec), sigOf({ ...spec, sources: [{ key: "mail", days: 30 }] }));
  assert.equal(sigOf(spec), sigOf({ ...spec, components: [] }), "a component edit is not a source edit: the same rows redraw");
});

test("the editor lays its sources out as a report does, and every dashboard - the built-in one too - has the same editor", () => {
  const ed = src("DashboardEditor.jsx"), rv = src("ReportsView.jsx");
  assert.match(ed, /import \{ SourceCard \} from "\.\/ReportsView\.jsx";/, "a report's own source cards, not a second kind");
  assert.match(ed, /<Section title=\{DASH\.sources\}[\s\S]*<SourceCard [\s\S]*<Section title=\{DASH\.shows\}[\s\S]*<ComponentCard /);
  assert.doesNotMatch(ed, /Owner|template'/, "nothing in the editor tells the built-in one apart");
  assert.match(rv, /<DashboardEditor [^\n]*types=\{types\} connectors=\{connectors\}/);
  assert.match(rv, /taskuary_data: \[\["what it reads", "dataset", "taskuary_dataset", ""\]/);
  // the shelf lists dashboards with the reports' own row, under the Dashboards section
  assert.match(rv, /section === "dashboards" \? dashboardSources/);
  assert.match(rv, /\.\.\.sectionRows\.map\(\(x\) => \(\{ key: String\(x\.SourceId\), node: row\(x\) \}\)\)/);
  // the dataset picker lists what the server serves (dashboards.DATASETS: test_dashboards holds the other half)
  assert.deepEqual(Object.keys(words.dashboard.datasets).sort(), ["agent_runs", "flow", "mail", "replies", "tasks"]);
});
