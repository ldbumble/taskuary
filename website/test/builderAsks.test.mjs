// The builder's questions are drawn by the kind the model gave each one (compose.ask_of) - a repository question as the repository
// list, never by reading its words; an older answer's bare strings stay text boxes.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { OTHER, asksOf, blanks, pickRows } from "../src/builderAsks.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("the server's asks carry their kind; bare strings are text questions", () => {
  assert.deepEqual(asksOf({ asks: [{ q: "Which repository?", kind: "repo" }, { q: "Which site?", kind: "choice", options: ["North", "South"] }, { q: "x", kind: "colour" }] }),
    [{ q: "Which repository?", kind: "repo", options: [] }, { q: "Which site?", kind: "choice", options: ["North", "South"] }, { q: "x", kind: "text", options: [] }]);
  assert.deepEqual(asksOf({ questions: ["Where is the file?"] }), [{ q: "Where is the file?", kind: "text", options: [] }]);
  assert.deepEqual(asksOf(null), []);
});

test("blanks counts what is still unanswered", () => {
  const asks = asksOf({ questions: ["a", "b"] });
  assert.equal(blanks(asks, {}), 2);
  assert.equal(blanks(asks, { a: "  ", b: "yes" }), 1);
});

test("a typed answer that is not in the list stays a row of its own", () => {
  assert.deepEqual(pickRows(["northwind/ledger"], ""), ["northwind/ledger"]);
  assert.deepEqual(pickRows(["northwind/ledger"], "northwind/portal"), ["northwind/ledger", "northwind/portal"]);
  assert.deepEqual(pickRows(["northwind/ledger"], OTHER), ["northwind/ledger"]);
});

test("a repository question reads the coding picker's list, and both builders draw the same questions", () => {
  const src = read("BuilderAsks.jsx");
  assert.match(src, /api\.get\("\/api\/repos"\)/);
  assert.match(src, /a\.kind === "repo"/);
  assert.match(src, /<SchedulePicker /);
  for (const f of ["Composer.jsx", "ReportsView.jsx"]) assert.match(read(f), /<BuilderAsks asks=\{asks\} answers=\{answers\} setAnswers=\{setAnswers\}/);
  assert.doesNotMatch(read("BuilderAsks.jsx"), /\/repositor|\.test\(a\.q|a\.q\.(includes|match)/i, "the question's words decide nothing");
});
