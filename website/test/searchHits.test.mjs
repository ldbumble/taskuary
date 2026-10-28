import test from "node:test";
import assert from "node:assert/strict";
import { arrange, asks, filters, marks, meta, personHits, terms, kindOf, nothingMatches, totalOf } from "../src/searchHits.js";
import { readFileSync } from "node:fs";

const hits = [
  { type: "email", id: "msg:1", title: "Your certificate expires" },
  { type: "task", id: "task:7", title: "Renew the certificate" },
  { type: "pr", id: "msg:2", title: "#12 fix the build" },
  { type: "source", id: "src:email:alex@northwind.example", title: "alex@northwind.example" },
  { type: "email", id: "msg:3", title: "Fw: Your certificate expires" },
];

test("hits are grouped by kind, tasks first, the server's order kept inside a group", () => {
  const { groups, flat } = arrange(hits);
  assert.deepEqual(groups.map((g) => g.group), ["Tasks", "Email", "Code", "Sources"]);
  assert.deepEqual(flat.map((h) => h.id), ["task:7", "msg:1", "msg:3", "msg:2", "src:email:alex@northwind.example"]);
});

test("a filter narrows to one kind, and the strip counts only kinds that have something", () => {
  assert.deepEqual(arrange(hits, "Email").flat.map((h) => h.id), ["msg:1", "msg:3"]);
  assert.deepEqual(filters(hits).map((f) => [f.label, f.n]), [["All", 5], ["Tasks", 1], ["Email", 2], ["Pull requests", 1], ["Sources", 1]]);
});

test("a match is marked from the start of a word, as the index matched it", () => {
  const w = terms("cert exp");
  assert.deepEqual(marks("Your certificate expires; concert", w).filter((p) => p.hit).map((p) => p.t), ["cert", "exp"]);
  assert.deepEqual(marks("nothing here", w), [{ t: "nothing here", hit: false }]);
});

test("a kind the page does not know still gets a pill", () => {
  assert.equal(kindOf({ type: "whatever" }).label, "Item");
});

// the 2026-10-19 UI walk (G9): the footer said "15 of 15" over a list cut at eight tasks
test("the count is the server's whole count, past the cap, and '+' where the mail index stopped counting", () => {
  const res = { q: "certificate", hits, totals: { task: 23, email: 2, pr: 1, source: 1 }, capped: false };
  assert.deepEqual(totalOf(res), { n: 27, more: false });
  assert.deepEqual(totalOf(res, "Tasks"), { n: 23, more: false });
  assert.deepEqual(filters(hits, res).map((f) => [f.label, f.n]), [["All", "27"], ["Tasks", "23"], ["Email", "2"], ["Pull requests", "1"], ["Sources", "1"]]);
  assert.deepEqual(totalOf({ ...res, capped: true }, "Email"), { n: 2, more: true });
  assert.deepEqual(totalOf({ ...res, capped: true }, "Tasks"), { n: 23, more: false });       // the task count is exact
  assert.deepEqual(totalOf({ q: "x", hits }), { n: 5, more: false });                          // an older server: what came back
});

test("a status is asked for by name, and is no word to mark", () => {
  assert.deepEqual(terms("invoice status:open"), ["invoice"]);
  assert.ok(asks("status:done")); assert.ok(!asks("status:")); assert.ok(!asks(" a "));
});

test("every page's box says nothing was found the same way, and where else to look", () => {
  assert.equal(nothingMatches(" zzq "), "Nothing matches “zzq”.");
  assert.equal(nothingMatches("zzq", "Settings"), "Nothing matches “zzq” in Settings. The search at the top looks through everything.");
  for (const f of ["SettingsView.jsx", "ConnectorsView.jsx", "HubView.jsx", "SearchEverything.jsx"])
    assert.match(readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8"), /nothingMatches\(/, f);
});

test("settings and connections are kinds of their own", () => {
  assert.deepEqual(arrange([{ type: "setting", id: "set:a" }, { type: "connector", id: "con:gmail" }]).groups.map((g) => g.group), ["Connections", "Settings"]);
});

// Enter is spent on the answer to the words in the box - never on rows left from earlier words (SearchEverything.jsx)
test("Enter opens what was typed: held until its own answer lands", () => {
  const f = readFileSync(new URL("../src/SearchEverything.jsx", import.meta.url), "utf8");
  assert.match(f, /const settled = !!res && res\.q === q\.trim\(\) && !busy;/);
  assert.match(f, /if \(settled && res\.q === t\) pick\(shown\.flat\[at\]\);\s*else if \(asks\(t\)\) held\.current = t;/);
  assert.match(f, /disableRestoreFocus/);
});

// PEOPLE IN THE ONE BOX (the owner, 2026-10-28): the directory the To and Cc pickers search answers here too, under People, an address once
test("the directory's people are a group of their own, after Tasks, each address once", () => {
  const ps = personHits([{ to: "gmoreno@northwind.example", name: "Gail Moreno", company: "Northwind" }, { to: "GMoreno@northwind.example", name: "Gail" },
    { to: "lortiz@dynamo.example", name: "", org: "Dynamo Freight" }, { name: "no address" }]);
  assert.deepEqual(ps.map((h) => [h.title, h.to, h.company]), [["Gail Moreno", "gmoreno@northwind.example", "Northwind"], ["lortiz@dynamo.example", "lortiz@dynamo.example", "Dynamo Freight"]]);
  assert.deepEqual(arrange([{ type: "email", id: "m1" }, ...ps, { type: "task", id: "t1" }]).groups.map((g) => g.group), ["Tasks", "People", "Email"]);
  assert.deepEqual(meta(ps[1]), ["lortiz@dynamo.example", "Dynamo Freight"]);
  assert.equal(kindOf(ps[0]).label, "Person");
  const f = readFileSync(new URL("../src/SearchEverything.jsx", import.meta.url), "utf8");
  assert.match(f, /api\.get\("\/api\/people\/search", \{ params: \{ q: t \} \}\)/, "the pickers' own search");
});
