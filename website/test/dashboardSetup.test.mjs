// EVERY DASHBOARD IS CONFIGURABLE (the owner, 2026-10-24: "it should be configurable, with a new tab in Reports named Dashboards with
// sources layout like reports"): its sources are a report's source cards, its components are cards beside them, and the built-in
// Taskuary at a glance is an ordinary row, opened and edited in the same editor as any other. The conversions are in setup.js.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { MAX_COMPONENTS, OWN_KEYS, copyTile, runCfg, freshKey, moveTile, orphans, saidOf, sigOf, swapTile, tileAsk, wantsDrawing, withField } from "../src/dashboard/setup.js";
import { DASH } from "../src/words.js";

const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");
const words = JSON.parse(readFileSync(new URL("../../taskuary/words.json", import.meta.url), "utf8"));

// A TILE IS ONE SENTENCE (the owner, 2026-11-06: "it's not generalized ... maybe we should just use text to say what it shows")
test("a tile is its sentence: Enter or leaving the line draws it only when the words changed", () => {
  const c = { kind: "stat", title: "Open now", said: "How many tasks are open right now", source: "tasks" };
  assert.equal(saidOf(c), "How many tasks are open right now");
  assert.equal(saidOf({ kind: "stat", title: "Open now" }), "Open now", "a tile with no sentence yet shows its title, never a blank line");
  assert.equal(wantsDrawing("How many tasks are open right now ", c), false, "the same words are the same tile: no AI is asked");
  assert.equal(wantsDrawing("   ", c), false);
  assert.equal(wantsDrawing("Open tasks by kind", c), true);
  assert.equal(wantsDrawing("Tokens per model per day, stacked", null), true, "the add box draws any words");
});

test("the server is asked with the dashboard's sources, the words and the tile they rewrite", () => {
  const spec = { type: "dashboard", title: "Desk", sources: [{ key: "tasks", type: "taskuary_data", dataset: "tasks" }], components: [{ kind: "stat" }] };
  const c = spec.components[0];
  assert.deepEqual(tileAsk(spec, " open tasks ", c), { config: { type: "dashboard", title: "Desk", sources: spec.sources }, said: "open tasks", current: c });
  assert.equal("current" in tileAsk(spec, "open tasks"), false, "a new tile rewrites nothing");
});

test("the answer lands on the tile asked about, wherever it was dragged since, and on none once removed", () => {
  const a = { said: "a" }, b = { said: "b" }, drawn = { said: "b, redrawn" };
  const moved = moveTile([a, b], 1, 0);
  assert.deepEqual(moved, [b, a]);
  assert.deepEqual(swapTile(moved, b, drawn), [drawn, a]);
  assert.deepEqual(swapTile([a], b, drawn), [a], "removed while drawing: nothing comes back");
  assert.deepEqual(moveTile([a, b], 0, 5), [a, b]);
  const two = copyTile([a, b], 0);
  assert.deepEqual(two, [a, { said: "a" }, b]); assert.notEqual(two[1], a, "a copy is its own tile");
  const full = Array.from({ length: MAX_COMPONENTS }, (_, i) => ({ said: String(i) }));
  assert.equal(copyTile(full, 0), full, "one screen: no copy past the cap");
  assert.deepEqual(withField({ kind: "bar", x: "kind", limit: 8 }, "limit", ""), { kind: "bar", x: "kind" });
});

test("the field grid is gone: each tile is drawn in the dashboard under its sentence, with one add box and the no-AI line", () => {
  const ed = src("DashboardEditor.jsx"), dash = src("dashboard/Dashboard.jsx");
  assert.doesNotMatch(ed, /ComponentCard|DASH\.fields|DASH\.kinds|DASH\.aggs|withKind|whereOf/, "deleted, not hidden");
  assert.match(ed, /<Dashboard [^>]*frame=\{frame\} after=\{addTile\} \/>/);
  assert.match(ed, /<SaidLine c=\{c\} canAsk=\{canAsk\} ask=\{\(t\) => tileAsk\(spec, t, c\)\} onDrawn=\{\(n\) => setComps\(\(cur\) => swapTile\(cur, c, n\)\)\} \/>/);
  assert.match(ed, /api\.post\("\/api\/dashboards\/tile", ask\(text\.trim\(\)\)\)/);
  assert.match(ed, /const addTile = canAsk && /, "no AI: no add box");
  assert.match(ed, /InputProps=\{\{ readOnly: !canAsk/, "...and no sentence changed");
  assert.match(ed, /!canAsk && <Typography data-tq-dashboard-no-ai=""/);
  assert.match(dash, /frame \? <React\.Fragment key=\{i\}>\{frame\(c, i, draw\(c, i\), spanOf4\(c\)\)\}/);
  for (const k of ["add_tile", "drawing", "no_ai_tiles", "said", "copy", "remove_tile", "move", "shows_hint"]) assert.ok(DASH[k], `words.json dashboard.${k}`);
  for (const k of ["fields", "kinds", "aggs", "goods", "windows", "widths"]) assert.equal(DASH[k], undefined, `dashboard.${k} went with the grid`);
});

test("a new source gets a key no other wears; a component reading a gone source is said before Save", () => {
  assert.equal(freshKey([{ key: "mail" }, { key: "s3" }]), "s4");
  assert.equal(freshKey([{ key: "s2" }, { key: "s3" }]), "s4");
  const spec = { sources: [{ key: "mail" }], components: [{ title: "In", source: "mail" }, { title: "Gone", source: "tasks" }] };
  assert.deepEqual(orphans(spec).map((c) => c.title), ["Gone"]);
  assert.notEqual(sigOf(spec), sigOf({ ...spec, sources: [{ key: "mail", days: 30 }] }));
  assert.equal(sigOf(spec), sigOf({ ...spec, components: [] }), "a component edit is not a source edit: the same rows redraw");
});

test("an S3 source on a dashboard keeps its path as object_key: its card's field and its Test hand the executor its key", () => {
  const s = { key: "s1", label: "Exports", type: "s3_object", bucket: "northwind-exports", object_key: "reports/latest.jsonl", date: "day" };
  assert.deepEqual(runCfg(s), { label: "Exports", type: "s3_object", bucket: "northwind-exports", key: "reports/latest.jsonl", date: "day" });
  assert.equal(runCfg({ key: "reports/old.jsonl", type: "s3_object", bucket: "b" }).key, "reports/old.jsonl", "a path an older save kept in key");
  assert.equal(runCfg({ key: "listing", type: "s3_object", bucket: "b", prefix: "reports/" }).key, undefined, "a listing reads no object");
  assert.deepEqual(runCfg({ key: "tasks", type: "taskuary_data", dataset: "tasks" }), { type: "taskuary_data", dataset: "tasks" });
  const ed = src("DashboardEditor.jsx"), rv = src("ReportsView.jsx");
  assert.match(ed, /renames=\{OWN_KEYS\[s\.type\] \|\| \{\}\} test=\{<SourceTest src=\{runCfg\(s\)\} \/>\}/);
  assert.match(rv, /\.map\(\(\[l, key, \.\.\.rest\]\) => \[l, renames\[key\] \|\| key, \.\.\.rest\]\)/);
  assert.deepEqual(OWN_KEYS, { s3_object: { key: "object_key" } }, "dashboards.OWN_KEYS says the same");
});

test("the editor lays its sources out as a report does, and every dashboard - the built-in one too - has the same editor", () => {
  const ed = src("DashboardEditor.jsx"), rv = src("ReportsView.jsx");
  assert.match(ed, /import \{ SourceCard, SourceTest \} from "\.\/ReportsView\.jsx";/, "a report's own source cards, not a second kind");
  assert.match(ed, /<Section title=\{DASH\.sources\}[\s\S]*<SourceCard [\s\S]*<Section title=\{DASH\.shows\}[\s\S]*<Dashboard /);
  assert.doesNotMatch(ed, /Owner|template'/, "nothing in the editor tells the built-in one apart");
  assert.match(rv, /<DashboardEditor [^\n]*types=\{types\} connectors=\{connectors\}/);
  assert.match(rv, /taskuary_data: \[\["what it reads", "dataset", "taskuary_dataset", ""\]/);
  // the shelf lists dashboards with the reports' own row, under the Dashboards section
  assert.match(rv, /section === "dashboards" \? dashboardSources/);
  assert.match(rv, /\.\.\.sectionRows\.map\(\(x\) => \(\{ key: String\(x\.SourceId\), node: row\(x\) \}\)\)/);
  // the dataset picker lists what the server serves (dashboards.DATASETS: test_dashboards holds the other half)
  assert.deepEqual(Object.keys(words.dashboard.datasets).sort(), ["agent_runs", "ai_usage", "flow", "mail", "replies", "tasks"]);
});
