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
  assert.match(got, /class="mid"><b style="font-size:20px">140\.0K<\/b>/, "the pie's whole in its middle");
  assert.match(got, /<span title="Tasks">Tasks<\/span><b>120\.0K<\/b><em>86%<\/em>/);
  assert.match(got, /<div class="tq-dash-value">60\.0K/, "80K and 40K over two tasks");
  // ...and an agent's pie in its chat is the same pie
  const pie = view({ root: "p", elements: { p: { type: "chart", props: { kind: "pie", points: [{ label: "Basic", value: 1 }, { label: "Pro", value: 3 }] } } } });
  assert.match(pie, /class="tq-dash-pie"/);
  assert.match(pie, /<span title="Pro">Pro<\/span><b>3<\/b><em>75%<\/em>/);
});

// SPEND IS DOLLARS (the owner, 2026-11-24: "spend is cost, not tokens"): a "$" tile says its figures as money, its change as a pill coloured by
// whether that way is good, and its tokens small under it; a chart in an agent's chat can be an area over its soft fill - the same Line
test("drawn, a dollar tile says money, a pill for its change and its tokens under it; an agent's area chart is the dashboard's", async () => {
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
  // this week $11.50 against $10.00 the week before; 1.2M tokens of which 400K on a plan, none with no price
  const rows = [{ day: day(1), cost: 6.5, tokens: 500000, billing: "priced" }, { day: day(3), cost: 5, tokens: 300000, billing: "priced" },
    { day: day(2), cost: null, tokens: 400000, billing: "plan" }, { day: day(9), cost: 10, tokens: 900000, billing: "priced" }];
  const spec = { title: "t", filters: { range: 7 }, sources: [{ key: "ai", date: "day" }], components: [
    { kind: "stat", title: "AI spend", source: "ai", agg: "sum", y: "cost", unit: "$", good: "down",
      also: [{ label: "tokens", agg: "sum", y: "tokens" }, { label: "on your plan", agg: "sum", y: "tokens", where: { billing: "plan" } },
             { label: "with no price", agg: "sum", y: "tokens", where: { billing: "unknown" } }] }] };
  const got = html(spec, { sources: { ai: { rows, columns: Object.keys(rows[0]) } } }, NOW);
  assert.match(got, /<div class="tq-dash-value">\$11\.50<\/div>/, "dollars, no unit after them");
  assert.match(got, /<b class="pill down">▲ 15%<\/b><span>vs last week<\/span>/, "spend up is the bad way");
  assert.match(got, /<div class="tq-dash-also"><span><b>1\.2M<\/b> tokens<\/span><span><b>400\.0K<\/b> on your plan<\/span><\/div>/);
  assert.doesNotMatch(got, /with no price/, "a figure that comes to nothing is not said");
  assert.match(got, /<linearGradient id="tq-dash-g\d+"/, "the sparkline fades under its line");
  const area = view({ root: "a", elements: { a: { type: "chart", props: { kind: "area", points: [{ label: "Mon", value: 2 }, { label: "Tue", value: 5 }] } } } });
  assert.match(area, /data-tq-dash-kind="area"/);
});

test("money reads as a person reads it", async () => {
  const { money } = await import("../src/dashboard/slice.js");
  assert.deepEqual([0.4213, 54.2, 20, 1234.4, 12345, 2.5e6, null].map(money), ["$0.42", "$54.20", "$20", "$1,234", "$12.3K", "$2.5M", "–"]);
});

// A PIE'S TOTAL FITS ITS HOLE (2026-11-24: "$34.83" touched the ring): the longer the figure, the smaller it is set - never past the hole
test("drawn, a pie's total is set to fit the ring's hole, a long one smaller", async () => {
  const { build } = await import("esbuild");
  const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
    import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser"; import { PieBody, holeFont } from "./src/dashboard/charts.jsx";
    export { holeFont };
    export const pie = (groups, f) => renderToStaticMarkup(<PieBody groups={groups} f={f} />);` }, loader: { ".css": "empty" },
    bundle: true, write: false, format: "esm", jsx: "automatic", platform: "browser", conditions: ["worker"], logLevel: "silent",
    define: { "process.env.NODE_ENV": '"production"' } });
  const { pie, holeFont } = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString("base64")}`);
  const usd = (n) => `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const long = pie([{ key: "Tasks", value: 10000 }, { key: "Triage", value: 2345.67 }], usd);
  assert.match(long, /<b style="font-size:12px">\$12,345\.67<\/b>/);
  const px = (s) => parseInt(holeFont(s), 10);
  // ...within the hole's 78px at about 0.62em a figure, whatever its length, and the short ones at the tile's full size
  for (const s of ["$1.2K", "$34.83", "$1,234", "$12,345.67", "$123,456,789.00"]) assert.ok(px(s) * 0.62 * s.length <= 78 || px(s) === 10, s);
  assert.equal(holeFont("$1.2K"), "21px");
  assert.ok(px("$34.83") < 21 && px("$34.83") >= 18, holeFont("$34.83"));
});

// ONE STORY, NOT A WALL OF CHARTS (the owner, 2026-11-25: "the same chart a bunch of times ... It can be combined on top"): the week as a strip
// of numbers, every day in ONE chart whose measure and split are switched on top, and one category said rather than charted
test("drawn, the story's strip says the week, one chart holds every day with its switches, and a lone category is a sentence", async () => {
  const { build } = await import("esbuild");
  const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
    import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser"; import Dashboard from "./src/dashboard/Dashboard.jsx";
    import { Trend } from "./src/dashboard/charts.jsx"; import { trendView } from "./src/dashboard/slice.js";
    export const html = (spec, data, now) => renderToStaticMarkup(<Dashboard spec={spec} data={data} now={now} onOpen={() => {}} />);
    export const trend = (spec, data, c, start, now) => renderToStaticMarkup(<Trend c={c} metrics={c.metrics} start={start} onDrill={() => {}}
      view={(mi, si) => trendView(spec, data, c.metrics[mi], si, { days: 7, now })} />);` }, loader: { ".css": "empty" },
    bundle: true, write: false, format: "esm", jsx: "automatic", platform: "browser", conditions: ["worker"], logLevel: "silent",
    define: { "process.env.NODE_ENV": '"production"' } });
  const { html, trend } = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString("base64")}`);
  const day = (n) => daysAgo(n, NOW);
  const data = { sources: {
    mail: { rows: [{ day: day(0), channel: "email" }, { day: day(0), channel: "teams" }, { day: day(2), channel: "email" }] },
    ai: { rows: [{ day: day(1), who: "Tasks", model: "claude-sonnet-4-5", cost: 2, tokens: 9000 }, { day: day(1), who: "Triage", model: "claude-haiku-4-5", cost: 0.25, tokens: 3000 }] },
    tasks: { rows: [{ arrived: day(0), kind: "general", state: "open" }] } } };
  const trendC = { kind: "trend", title: "Day by day", w: 4, metrics: [
    { label: "Came in", source: "mail", agg: "count", splits: [["channel", "channel"]] },
    { label: "AI spend", source: "ai", agg: "sum", y: "cost", unit: "$", splits: [["who", "who"], ["model", "model"]], order: ["Triage", "Advisor", "Tasks", "Assistant", "Other"] }] };
  const spec = { title: "t", filters: { range: 7 }, sources: [{ key: "mail", date: "day" }, { key: "ai", date: "day" }, { key: "tasks", date: "arrived" }], components: [
    { kind: "kpis", title: "This week", w: 4, items: [{ title: "Came in", source: "mail", agg: "count" }, { title: "AI spend", source: "ai", agg: "sum", y: "cost", unit: "$" }] },
    trendC, { kind: "bar", title: "Open work by kind", source: "tasks", x: "kind", w: 2 }] };
  const got = html(spec, data, NOW);
  // the strip: two numbers in one card, each its own title and figure
  assert.match(got, /data-tq-dash-kind="kpis"[\s\S]*?<div class="tq-dash-kpi-h">Came in<\/div><div class="tq-dash-value">3<\/div>[\s\S]*?<div class="tq-dash-kpi-h">AI spend<\/div><div class="tq-dash-value">\$2\.25<\/div>/);
  // the one chart: what it counts and what splits it, switched on its top - Came in by channel to begin with
  assert.match(got, /aria-label="What it counts"><button type="button" aria-pressed="true">Came in<\/button><button type="button" aria-pressed="false">AI spend<\/button>/);
  assert.match(got, /<span class="lead">split by<\/span><button type="button" aria-pressed="true">channel<\/button>/);
  assert.match(got, /<i style="background:var\(--d-s\d\)"><\/i>email<\/button>/);
  // ...one category is a sentence, not a chart
  assert.match(got, /<div class="tq-dash-onefig"><b>1<\/b><span>general<\/span><\/div>/);
  // switched to AI spend, split by model: the columns are dollars per model; by who, the owner's order and its colours
  const byModel = trend(spec, data, trendC, [1, 1], NOW);
  assert.match(byModel, /<button type="button" aria-pressed="true">AI spend<\/button>/);
  assert.match(byModel, /<button type="button" aria-pressed="true">model<\/button>/);
  assert.match(byModel, /claude-sonnet-4-5<\/button>/);
  assert.match(byModel, /aria-label="[A-Z][a-z]{2} \d+: \$2\.25"/, "a day's column says its dollars");
  const byWho = trend(spec, data, trendC, [1, 0], NOW);
  assert.match(byWho, /<i style="background:var\(--d-s1\)"><\/i>Triage<\/button><button[^>]*><i style="background:var\(--d-s3\)"><\/i>Tasks<\/button>/);
});
