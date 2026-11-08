// A VIEW THE AGENT SHOWS IN ITS CHAT (agenttools `show`): the page draws only what the catalog allows, reads the server's checked spec off
// the call's answer, and turns a bad one into null (ViewSpec.jsx shows it as JSON). Invented people and numbers.
import assert from "node:assert/strict";
import test from "node:test";
import { MARK, buttonOf, fmtAs, labels, normalise, placesOf, specIn, verbOf, viewOf } from "../src/viewSpec.js";
import { turnParts } from "../src/chatStream.js";

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
  assert.equal(bad({ a: { type: "chart", props: { kind: "pie", points: [{ label: "x", value: 1 }] } } }), null);
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
  const broken = viewOf(call("mcp__taskuary__show"), res(`${MARK}{"root":"a","elements":{"a":{"type":"marquee"}}}`));
  assert.equal(broken.spec, null); assert.equal(broken.raw.root, "a");               // drawn as its JSON
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
