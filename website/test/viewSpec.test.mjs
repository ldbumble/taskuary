// A VIEW THE AGENT SHOWS IN ITS CHAT (agenttools `show`): the page draws only what the catalog allows, reads the server's checked spec off
// the call's answer, and turns a bad one into null (ViewSpec.jsx shows it as JSON). Invented people and numbers.
import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { MARK, buttonOf, colName, columnsOf, evalExpr, fencedView, fillIn, fmtAs, labels, normalise, placesOf, specIn, verbOf, viewOf } from "../src/viewSpec.js";
import { eventsOf, turnParts } from "../src/chatStream.js";

const SPEC = {
  title: "Northwind renewals",
  root: "top",
  elements: {
    top: { type: "text", props: { text: "Three renewals are due; **Payworth** is the largest." }, children: ["kpis", "t", "c", "todo", "go"] },
    kpis: { type: "stats", props: { items: [{ label: "Due", value: 3 }, { label: "Total", value: "$18,420", note: "this quarter" }] } },
    t: { type: "table", props: { columns: ["vendor", "amount"], rows: [["Payworth", 9310], { vendor: "Trainly", amount: 5100 }, ["Spendly"]] } },
    c: { type: "chart", props: { kind: "bar", title: "By vendor", points: [{ label: "Payworth", value: 9310 }, { label: "Trainly", value: 5100 }] } },
    todo: { type: "checklist", props: { items: [{ text: "Ask Erin Blake for the quote", done: true }, "Book the call"] } },
    go: { type: "button", props: { label: "Mark it done", verb: "done" } },
  },
};

test("a good spec comes back whole, rows squared to the columns, a row id read as its verb", () => {
  const v = normalise(SPEC);
  assert.equal(v.title, "Northwind renewals");
  assert.deepEqual(v.elements.t.props.rows, [["Payworth", 9310], ["Trainly", 5100], ["Spendly", null]]);
  assert.deepEqual(v.elements.todo.props.items, [{ text: "Ask Erin Blake for the quote", done: true }, { text: "Book the call", done: false }]);
  assert.equal(v.elements.go.props.verb, "close");
  assert.deepEqual(buttonOf(v.elements.go.props), { label: "Mark it done", verb: "close", lights: "Mark done" });
  assert.equal(verbOf("remind"), "defer");
  assert.equal(verbOf("not_a_button"), null);
});

test("only what the root reaches is kept", () => {
  const v = normalise({ ...SPEC, elements: { ...SPEC.elements, stray: { type: "text", props: { text: "never drawn" } } } });
  assert.ok(!("stray" in v.elements));
});

test("anything outside the catalog is null, never half drawn", () => {
  const bad = (els, root = "a") => normalise({ root, elements: els });
  assert.equal(bad({ a: { type: "iframe", props: { src: "https://vendor.example" } } }), null);           // no such type
  assert.equal(bad({ a: { type: "text", props: { text: "hi", color: "red" } } }), null);                  // no such prop
  assert.equal(bad({ a: { type: "text", props: {} } }), null);                                            // a required prop missing
  assert.equal(bad({ a: { type: "chart", props: { kind: "radar", points: [{ label: "x", value: 1 }] } } }), null);
  assert.equal(bad({ a: { type: "chart", props: { points: [{ label: "x", value: "1" }] } } }), null);      // a point's value is a number
  assert.equal(bad({ a: { type: "table", props: { columns: ["a"], rows: [[1, 2]] } } }), null);            // wider than its columns
  assert.equal(bad({ a: { type: "button", props: { label: "Send", verb: "pay_now" } } }), null);           // no such button
  assert.equal(bad({ a: { type: "button", props: { label: "Go" } } }), null);                              // lights nothing
  assert.equal(bad({ a: { type: "button", props: { label: "Go", verb: "close", open: "#settings" } } }), null);
  assert.equal(bad({ a: { type: "button", props: { label: "Go", open: "https://vendor.example" } } }), null);   // only the app's pages
  assert.equal(bad({ a: { type: "text", props: { text: "x" }, children: ["a"] } }), null);                  // contains itself
  assert.equal(bad({ a: { type: "text", props: { text: "x" }, children: ["b"] } }), null);                  // a missing child
  assert.equal(bad({ a: { type: "list", props: { items: Array(51).fill("x") } } }), null);                  // past the cap
  assert.equal(bad({ a: { type: "text", props: { text: "x" } } }, "z"), null);                             // root not an element
  assert.equal(normalise("not a view"), null);
});

test("the server's checked spec rides the answer after its mark; a refusal or a stranger's `show` is no view", () => {
  const call = (name, args = {}) => ({ type: "tool_call", name, detail: { tool_call_id: "c1", args } });
  const res = (result, is_error = false) => ({ type: "tool_result", name: "c1", detail: { tool_call_id: "c1", result, is_error } });
  const answer = `Shown in the owner's chat. ${MARK}${JSON.stringify(SPEC)}`;
  assert.deepEqual(specIn(answer), SPEC);
  assert.equal(specIn("no mark here"), undefined);
  const v = viewOf(call("mcp__taskuary__show"), res(answer));
  assert.equal(v.type, "view"); assert.equal(v.spec.root, "top");
  assert.equal(viewOf(call("mcp__taskuary__show", SPEC), res("TypeError: bad", true)), null);
  assert.equal(viewOf(call("show", SPEC), res("done")), null);                         // someone else's tool called show
  assert.equal(viewOf(call("mcp__taskuary__show", { summary: "{\"root\":…" })), null); // its arguments cut in the trace
  assert.equal(viewOf(call("mcp__taskuary__show", SPEC)).spec.title, "Northwind renewals");   // live: drawn from its arguments
  // ...but AN ANSWER WITHOUT THE MARK IS A REFUSAL (2026-11-17): the server says why in plain text, not is_error, so a table it refused was
  // drawn from the arguments over the one it then accepted - the price table twice. Only a call with no answer at all draws its arguments
  const twice = { title: "Prices", root: "t", elements: { t: { type: "table", props: { columns: ["Plan", "Price"], rows: [["Basic", 10]] }, columns: ["Plan", "Price"], rows: [["Basic", 10]] } } };
  assert.equal(viewOf(call("mcp__taskuary__show", twice), res("elements.t has columns, rows - an element is type, props, children")), null);
  assert.equal(viewOf({ ...call("mcp__taskuary__show", twice), detail: { ...call("", twice).detail, output: "elements.t has columns, rows - an element is type, props, children" } }), null);
  assert.equal(viewOf(call("mcp__taskuary__show", twice), res("")).spec.title, "Prices");     // a log that kept no answer
  // ...and A VIEW IS DRAWN OR IT STAYS A STEP, NEVER ITS JSON (the owner, 2026-11-15: "did you also fix the json render of the charts/visuals?"):
  // a spec the page cannot draw - a live call's own arguments outside the catalog (a pie, a Vega object) - was printed as JSON in the chat
  assert.equal(viewOf(call("mcp__taskuary__show"), res(`${MARK}{"root":"a","elements":{"a":{"type":"marquee"}}}`)), null);
  assert.equal(viewOf(call("mcp__taskuary__show", { root: "p", elements: { p: { type: "chart", props: { kind: "pie", points: [] } } } })), null);
});

test("in the chat a view is its own part, between the words around it", () => {
  const parts = turnParts([
    { type: "progress", name: "text", detail: "Here is where the renewals stand." },
    { type: "tool_call", name: "mcp__taskuary__show", detail: { tool_call_id: "v1", args: SPEC } },
    { type: "tool_result", name: "v1", detail: { tool_call_id: "v1", result: `Shown in the owner's chat. ${MARK}${JSON.stringify(SPEC)}` } },
    { type: "progress", name: "text", detail: "Payworth is the one to chase." },
  ]);
  assert.deepEqual(parts.map((p) => p.type), ["said", "view", "said"]);
  assert.equal(parts[1].spec.elements.c.props.kind, "bar");
});

// grid, badge and note; a title and a description on every block; a tile's trend and format, a column's format, a highlighted point
const NEW = { root: "g", elements: {
  g: { type: "grid", props: { cols: 2, title: "Plans", description: "For 40 people" }, children: ["k", "c", "t", "b", "n"] },
  k: { type: "stats", props: { items: [{ label: "Top tier", value: 540, format: "currency", trend: { dir: "up", text: "+$340 vs Basic" } }] } },
  c: { type: "chart", props: { kind: "bar", format: "currency", points: [{ label: "Payworth Basic", value: 200, highlight: true }, { label: "Payworth Pro", value: 540 }] } },
  t: { type: "table", props: { title: "Costs", columns: ["Plan", { label: "Per month", format: "currency" }], rows: [{ Plan: "Payworth Basic", "Per month": 200 }, ["Payworth Pro", 540]] } },
  b: { type: "badge", props: { text: "Cheapest", variant: "success" } },
  n: { type: "note", props: { tone: "warning", title: "Before you switch", text: "Two reports are still open." } },
} };

test("the new blocks and props pass, and the server's answer to them passes again", () => {
  const v = normalise(NEW);
  assert.deepEqual(v.elements.g.props, { cols: 2, title: "Plans", description: "For 40 people" });
  assert.deepEqual(v.elements.k.props.items[0].trend, { dir: "up", text: "+$340 vs Basic" });
  assert.deepEqual(v.elements.c.props.points.map((p) => !!p.highlight), [true, false]);
  assert.deepEqual(v.elements.t.props.rows, [["Payworth Basic", 200], ["Payworth Pro", 540]]);
  assert.deepEqual(labels(v.elements.t.props.columns), ["Plan", "Per month"]);
  assert.deepEqual(normalise(v), v);
  assert.equal(normalise({ root: "a", elements: { a: { type: "grid", props: { cols: "3" } } } }).elements.a.props.cols, 3);
});

test("the new blocks outside the catalog are null", () => {
  const bad = (type, props) => assert.equal(normalise({ root: "a", elements: { a: { type, props } } }), null, JSON.stringify(props));
  bad("grid", { cols: 5 }); bad("grid", { cols: true });
  bad("badge", { text: "x", variant: "danger" }); bad("badge", {});
  bad("note", { tone: "error", text: "x" });
  bad("text", { text: "x", title: "y".repeat(201) });
  bad("stats", { items: [{ label: "a", value: 1, trend: { dir: "sideways" } }] });
  bad("stats", { items: [{ label: "a", value: 1, format: "euro" }] });
  bad("stats", { items: [{ label: "a", value: 1, colour: "red" }] });
  bad("table", { columns: [{ label: "a", format: "money" }], rows: [[1]] });
  bad("table", { columns: [{ name: "a" }], rows: [[1]] });
});

test("a number in its format: money with none or two decimals, counts grouped, a percent as written", () => {
  assert.equal(fmtAs(540, "currency"), "$540");
  assert.equal(fmtAs(13.5, "currency", placesOf([0, 5, 13.5], "currency")), "$13.50");
  assert.equal(fmtAs(0, "currency", 2), "$0.00");
  assert.equal(fmtAs(-40, "currency"), "-$40");
  assert.equal(fmtAs(6480, "number"), "6,480");
  assert.equal(fmtAs(12.5, "percent"), "12.5%");
  assert.equal(fmtAs(null, "currency"), "");
  assert.equal(fmtAs("n/a", "currency"), "n/a");
});

// ...and a FILED turn draws it too (2026-11-09): its kept step carries the tool's answer as `output` (sessionrecord.keep_turn)
test("a filed turn's show step draws its view from the answer it kept", () => {
  const steps = [{ k: "tool", name: "mcp__taskuary__show", text: "", output: `Shown in the owner's chat. ${MARK}${JSON.stringify(SPEC)}` }, { k: "said", text: "Three are due." }];
  const view = turnParts(eventsOf(steps, false)).find((p) => p.type === "view");
  assert.equal(view?.spec.title, "Northwind renewals");
});


// the owner, 2026-11-15: "of course chart should be in chat, wasn't that the whole idea of the json render?" - an agent that writes its chart
// as a fenced spec in its answer, not through `show`, had it drawn as a code block. Same check, same renderer; anything else stays code
test("a fenced block in an answer that is a view is the view the show road draws; anything else stays its code", () => {
  const chart = { root: "c", elements: { c: { type: "chart", props: { kind: "bar", title: "Signups by month",
    points: [{ label: "Jan", value: 120 }, { label: "Feb", value: 145 }, { label: "Mar", value: 98 }] } } } };
  assert.deepEqual(fencedView(`\n${JSON.stringify(chart, null, 2)}\n`), normalise(chart));
  assert.deepEqual(fencedView(JSON.stringify(SPEC)), normalise(SPEC));
  for (const code of ["npm run build", '{"name": "Erin Blake", "age": 41}', "[1, 2, 3]", '{"root": "c", "elements": {"c": {"type": "chart"', "",
    JSON.stringify({ root: "c", elements: { c: { type: "pie", props: {} } } })]) assert.equal(fencedView(code), null, code);
  // ...and the chat's markdown draws it through the view's own renderer, at the code block's place
  const md = readFileSync(new URL("../src/md.jsx", import.meta.url), "utf8");
  assert.match(md, /const Pre = [^;]*;\n[^\n]*fencedView\(/);
  assert.match(md, /if \(view\) return <ViewSpec spec=\{view\} \/>;/);
});

// A VIEW KEEPS THE CHAT'S FLOW (the owner, 2026-11-23: "isn't so big it takes up the whole screen - you lose the flow"): twelve months as ranked
// bars stood a row each, 538px in a 409px chat at 1366x768 - a run of short labels is drawn as columns (the chart's height whatever their
// count), in the view's own figures, its highlighted month picked out; a few, or long names, stay ranked bars
test("a bar chart of many short labels is columns in the view's own figures; a few long names stay ranked bars", async () => {
  const mark = (key, value, on = false) => ({ key, value, rows: [], on });
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"].map((m, i) => mark(m, 40000 + 2500 * i, m === "Dec"));
  const st = columnsOf(months);
  assert.deepEqual(st.keys, months.map((m) => m.key));
  assert.deepEqual([...st.on], ["Dec"]);
  assert.equal(columnsOf(months.slice(0, 6)), null, "six bars stay bars");
  assert.equal(columnsOf([...months.slice(0, 11), mark("Northwind Logistics", 1)]), null, "a long name stays a ranked bar");
  // ...drawn by the dashboard's columns in the view's money, December picked out
  const { build } = await import("esbuild");
  const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
    import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser"; import { Stacked } from "./src/dashboard/charts.jsx";
    export const html = (c, st) => renderToStaticMarkup(<Stacked c={c} st={st} slots={{ value: 0 }} onDrill={() => {}} />);` },
    bundle: true, write: false, format: "esm", jsx: "automatic", platform: "browser", logLevel: "silent", define: { "process.env.NODE_ENV": '"production"' } });
  const { html } = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString("base64")}`);
  const h = html({ title: "Revenue", fmt: (n) => fmtAs(n, "currency", 0) }, st);
  assert.equal(h.match(/class="tq-dash-col( pick)?"/g).length, 12, "a column a month");
  assert.equal(h.match(/class="tq-dash-col pick"/g).length, 1, "December picked out");
  assert.match(h, /class="tq-dash-cols hi"/);
  assert.match(h, /aria-label="Dec: \$67,500"/, "each column says its value in the view's figures");
  assert.match(h, />\$100,000</, "the axis too");
});

// ── WHAT-IF AND ANSWERS (the owner, 2026-11-24, after json-render's state and actions) ─────────────────────────────────────────────
const WHAT_IF = { title: "Payworth seats", state: { seats: 40 }, root: "g", elements: {
  g: { type: "grid", props: { cols: 1 }, children: ["s", "k", "t", "go"] },
  s: { type: "slider", props: { label: "Seats", value: { $bindState: "/seats" }, min: 5, max: 200, step: 5 } },
  k: { type: "stats", props: { items: [{ label: "Per month", format: "currency", value: { $expr: "seats * 12" } }] } },
  t: { type: "table", props: { rows: [{ Plan: "Basic", "Per seat": 12, Total: { $expr: "per_seat * seats" } }] } },
  go: { type: "button", props: { label: "Go with this" }, on: { press: { action: "answer", params: { text: "{seats} seats" } } } } } };

test("a slider's value is what the tile is worked out from: moved, the tile reads the new figure", () => {
  const v = normalise(WHAT_IF), tile = v.elements.k.props.items[0].value;
  assert.equal(v.elements.s.props.value, "seats");
  assert.deepEqual(tile, { $expr: "seats * 12" });
  assert.equal(evalExpr(tile.$expr, v.state).value, 480);
  assert.equal(evalExpr(tile.$expr, { ...v.state, seats: 55 }).value, 660, "the slider moved to 55: the tile reads $660");
  // ...a cell reads its own row's columns too, and the answer's words are filled in as he presses
  assert.deepEqual(v.elements.t.props.columns, ["Plan", "Per seat", "Total"]);
  assert.equal(evalExpr("per_seat * seats", { seats: 10, [colName("Per seat")]: 12 }).value, 120);
  assert.deepEqual(fillIn(v.elements.go.on.press.params.text, { seats: 25 }), { value: "25 seats" });
  assert.ok(v.id, "a view he can answer is named, so his pick is kept against it");
});

test("the grammar is small and safe: what it cannot work out is a plain error, never a throw and never eval", () => {
  const ok = (src, scope, want) => assert.deepEqual(evalExpr(src, scope), { value: want }, src);
  ok("1 + 2 * 3", {}, 7); ok("(1 + 2) * 3", {}, 9); ok("10 - 2 - 3", {}, 5); ok("-x + 1", { x: 4 }, -3);
  ok("annual ? seats * 10 : seats * 12", { annual: true, seats: 3 }, 30); ok("plan == 'Pro' && n > 2", { plan: "Pro", n: 3 }, true);
  ok("round(x / 3, 2)", { x: 10 }, 3.33); ok("max(a, b, 7)", { a: 1, b: 9 }, 9); ok("!on", { on: false }, true);
  for (const bad of ["seats *", "seat * 2", "constructor", "alert(1)", "x.y", "1 +* 2", "", "1 / 0", "__proto__"]) {
    const r = evalExpr(bad, { seats: 1, x: { y: 1 } });
    assert.ok(r.error && !("value" in r), `${bad} -> ${JSON.stringify(r)}`);
  }
  assert.match(evalExpr("seat * 2", { seats: 1 }).error, /no value named seat/);
  assert.match(fillIn("{nope} seats", {}).error, /no value named nope/);
});

test("controls, a choice and records pass; an action that is not answer or setState is no view", () => {
  const bad = (els) => normalise({ root: "a", elements: els });
  assert.ok(bad({ a: { type: "choice", props: { label: "Which plan?", options: ["Basic", "Pro"] } } }).id);
  assert.deepEqual(bad({ a: { type: "toggle", props: { label: "Yearly", value: "annual" } } }).state, { annual: false });
  assert.deepEqual(bad({ a: { type: "chart", props: { kind: "pie", rows: [{ plan: "Basic", n: 2 }, { plan: "Pro", n: 5 }] } } }).elements.a.props.points,
    [{ label: "Basic", value: 2 }, { label: "Pro", value: 5 }]);
  assert.equal(bad({ a: { type: "button", props: { label: "Pay" }, on: { press: { action: "pay" } } } }), null);
  assert.equal(bad({ a: { type: "text", props: { text: "x" }, on: { press: { action: "answer", params: { text: "x" } } } } }), null);
  assert.equal(bad({ a: { type: "slider", props: { label: "n", value: "n", min: 5, max: 5 } } }), null);
  assert.equal(normalise({ ...WHAT_IF, id: "abc123" }).id, "abc123", "the server's own id is kept");
});

test("drawn, the tile reads the slider's value; a bad expression is a line in the view and the rest still draws", async () => {
  const { build } = await import("esbuild");
  const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
    import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser"; import ViewSpec from "./src/ViewSpec.jsx";
    export const html = (spec) => renderToStaticMarkup(<ViewSpec spec={spec} />);` }, loader: { ".css": "empty" },
    bundle: true, write: false, format: "esm", jsx: "automatic", platform: "browser", conditions: ["worker"] /* Md's entity decoder reads `document` in its browser build */, logLevel: "silent", define: { "process.env.NODE_ENV": '"production"' } });
  const { html } = await import(`data:text/javascript;base64,${Buffer.from(out.outputFiles[0].text).toString("base64")}`);
  const at = (seats) => html(normalise({ ...WHAT_IF, state: { seats } }));
  assert.match(at(40), /data-tq-view-value="">\$480</); assert.match(at(55), /data-tq-view-value="">\$660</);
  assert.match(at(55), />55</, "the slider says where it stands");
  const broken = html(normalise({ ...WHAT_IF, elements: { ...WHAT_IF.elements,
    k: { type: "stats", props: { items: [{ label: "Per month", value: { $expr: "seats * pric" } }] } } } }));
  assert.match(broken, /data-tq-view-err="">Could not work out &quot;seats \* pric&quot; - no value named pric</);
  assert.match(broken, /Per seat/, "the table beside it still draws");
  assert.doesNotMatch(broken, /data-tq-view-failed/, "never the whole view lost");
  // ...off a task there is no agent to answer: its buttons are drawn, greyed
  assert.match(at(40), /data-tq-view-pick="Go with this"[^>]*disabled|disabled[^>]*data-tq-view-pick="Go with this"/);
});
