import test from "node:test";
import assert from "node:assert/strict";
import { arrange, filters, marks, terms, kindOf } from "../src/searchHits.js";

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
