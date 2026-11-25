// THE BUILT-IN DASHBOARD (dashboards.TEMPLATES, "Taskuary at a glance"): New dashboard offers it beside the composer in one press,
// drawn over the install's own rows - what the End of day checkup is to reports (the owner, 2026-10-23). And the slices it leans on:
// a funnel's stages kept in order, a median, and a component's own fixed window (a weekly target) whatever range the page is on.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { aggregate, componentRows, daysAgo, groupBy, snapshotOf, spanOf } from "../src/dashboard/slice.js";
import { DASH } from "../src/words.js";

const src = (p) => readFileSync(new URL(`../src/${p}`, import.meta.url), "utf8");
const NOW = new Date("2026-10-23T10:00:00");

test("New dashboard offers the ready ones under the composer, and Use this draws one without a preview round-trip", () => {
  const ed = src("DashboardEditor.jsx");
  const setup = ed.slice(ed.indexOf("if (!spec) return ("), ed.indexOf("data-tq-dashboard-editor"));
  // ...under Set up with AI, the describe box's door to the chat (2026-10-30)
  assert.match(setup, /<SetupWithAi kind="dashboard"[\s\S]*<Templates onUse=\{takeTemplate\} \/>/, "the ready ones sit under the door, in the New flow");
  assert.match(setup, /sourceId == null \?/, "...only on a NEW dashboard, never over a saved one");
  assert.match(ed, /api\.get\("\/api\/dashboards\/templates"\)/);
  assert.match(ed, /api\.get\(`\/api\/dashboards\/templates\/\$\{encodeURIComponent\(key\)\}`\)/);
  assert.match(ed, /data-tq-dashboard-template=\{t\.key\}/);
  // the template came drawn: the preview effect does not run it again (the demo refuses /preview, and it would be the same rows)
  assert.match(ed, /read\.current = sigOf\(t\.config\);/);
  assert.match(ed, /sig === read\.current/);
  for (const k of ["or_start", "use", "using", "to_go", "target_met", "no_change", "right_now"]) assert.ok(DASH[k], `words.json dashboard.${k}`);
});

test("a funnel keeps its stages in order, a missing stage at zero; without an order the bars still rank", () => {
  const rows = [{ s: "Came in" }, { s: "Came in" }, { s: "Came in" }, { s: "On a task" }, { s: "Triaged" }, { s: "Triaged" }];
  const order = ["Came in", "Triaged", "On a task", "Task closed"];
  assert.deepEqual(groupBy(rows, "s", "count", null, { order }).map((g) => [g.key, g.value]),
    [["Came in", 3], ["Triaged", 2], ["On a task", 1], ["Task closed", 0]]);
  assert.deepEqual(groupBy(rows, "s").map((g) => g.key), ["Came in", "Triaged", "On a task"]);
});

test("the median is the middle value, and the mean of the middle two", () => {
  assert.equal(aggregate([{ h: 1 }, { h: 9 }, { h: 3 }], "median", "h"), 3);
  assert.equal(aggregate([{ h: 1 }, { h: 4 }], "median", "h"), 2.5);
  assert.equal(aggregate([], "median", "h"), null);
});

test("a component's own range is its window whatever the page's, and its unit rides on the shared lines", () => {
  const spec = { filters: { range: 30 }, sources: [{ key: "t", date: "closed" }],
    components: [{ kind: "progress", title: "Closed this week", source: "t", range: 7, target: 15 },
      { kind: "stat", title: "Median reply time", source: "r", agg: "median", y: "hours", unit: "h" }] };
  const data = { sources: { t: { rows: [{ closed: daysAgo(1, NOW) }, { closed: daysAgo(12, NOW) }] }, r: { rows: [{ hours: 2 }, { hours: 4 }] } } };
  assert.equal(spanOf(spec.components[0], 90), 7);
  assert.equal(spanOf({ range: false }, 90), 90);
  assert.equal(componentRows(spec, data, spec.components[0], { days: 90, now: NOW }).length, 1);
  assert.match(snapshotOf(spec, data, NOW).text, /Median reply time: 3 h/);
});

// WHAT THE AI SPENT, DRAWN (the owner, 2026-11-24): the built-in's spend tiles over invented rows - a slider beside the range's presets, a
// legend whose entries switch their series, a pie of who used the tokens with its whole in the middle, and tokens per task as a number
test("drawn, the spend tiles show the slider, the switchable legend, the pie's shares and tokens per task", async () => {
  const { build } = await import("esbuild");
  const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
    import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser"; import Dashboard from "./src/dashboard/Dashboard.jsx";
    import ViewSpec from "./src/ViewSpec.jsx";
    export const html = (spec, data, now) => renderToStaticMarkup(<Dashboard spec={spec} data={data} now={now} onOpen={() => {}} />);
    export const view = (spec) => renderToStaticMarkup(<ViewSpec spec={spec} />);` }, loader: { ".css": "empty" },
    bundle: true, write: false, format: "esm", jsx: "automatic", platform: "browser", conditions: ["worker"], logLevel: "silent",
    define: { "process.env.NODE_ENV": '"production"' } });
  const { html, view } = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString("base64")}`);
  const day = (n) => daysAgo(n, NOW);
  const rows = [
    { day: day(0), who: "Triage", kind: "one call", task_id: null, tokens: 3000 }, { day: day(1), who: "Advisor", kind: "one call", task_id: null, tokens: 1000 },
    { day: day(1), who: "Tasks", kind: "agent run", task_id: 4, tokens: 60000 }, { day: day(3), who: "Tasks", kind: "agent run", task_id: 4, tokens: 20000 },
    { day: day(2), who: "Tasks", kind: "agent run", task_id: 9, tokens: 40000 }, { day: day(2), who: "Assistant", kind: "one call", task_id: null, tokens: 16000 }];
  const spec = { title: "t", filters: { range: 7 }, sources: [{ key: "ai", date: "day" }], components: [
    { kind: "stacked", title: "Per day", source: "ai", x: "day", series: "who", agg: "sum", y: "tokens" },
    { kind: "pie", title: "By who", source: "ai", x: "who", agg: "sum", y: "tokens", order: ["Triage", "Advisor", "Tasks", "Assistant"] },
    { kind: "stat", title: "Tokens per task", source: "ai", agg: "sum", y: "tokens", per: "task_id", where: { kind: "agent run" } }] };
  const got = html(spec, { sources: { ai: { rows, columns: Object.keys(rows[0]) } } }, NOW);
  assert.match(got, /<input type="range" min="1" max="90" step="1" aria-label="Days back" style="--p:[\d.]+%" value="7"\/>/);
  assert.match(got, /Last 7 days/);
  for (const s of ["Triage", "Advisor", "Tasks", "Assistant"]) assert.match(got, new RegExp(`<button type="button" aria-pressed="true"[^>]*><i [^>]*></i>${s}</button>`));
  assert.match(got, /class="mid"><b>140\.0K<\/b>/, "the pie's whole in its middle");
  assert.match(got, /<span title="Tasks">Tasks<\/span><b>120\.0K<\/b><em>86%<\/em>/);
  assert.match(got, /<div class="tq-dash-value">60\.0K/, "80K and 40K over two tasks");
  // ...and an agent's pie in its chat is the same pie
  const pie = view({ root: "p", elements: { p: { type: "chart", props: { kind: "pie", points: [{ label: "Basic", value: 1 }, { label: "Pro", value: 3 }] } } } });
  assert.match(pie, /class="tq-dash-pie"/);
  assert.match(pie, /<span title="Pro">Pro<\/span><b>3<\/b><em>75%<\/em>/);
});
