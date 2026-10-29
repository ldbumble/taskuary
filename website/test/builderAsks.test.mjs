// The builder's questions are drawn by the kind the model gave each one (compose.ask_of) - a repository question as the repository
// list, never by reading its words; an older answer's bare strings stay text boxes.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { OTHER, answerState, answersFor, asksOf, blanks, pickRows } from "../src/builderAsks.js";

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

// ANSWER & BUILD LOOKED FROZEN (the owner, 2026-10-29): greyed until every box was filled, and nothing moved once pressed
test("Answer & build presses with some questions blank, and says why when it cannot", () => {
  const asks = asksOf({ questions: ["Which repository?", "Which sites?"] });
  assert.equal(answerState(asks, {}, "").disabled, true);
  assert.match(answerState(asks, {}, "").hint, /Answer at least one/);
  const one = answerState(asks, { "Which repository?": "northwind/ledger" }, "");
  assert.equal(one.disabled, false); assert.equal(one.left, 1); assert.match(one.hint, /1 left blank/);
  assert.deepEqual(answerState(asks, { "Which repository?": "a", "Which sites?": "b" }, ""), { disabled: false, left: 0, hint: "" });
  assert.equal(answerState(asks, { "Which repository?": "a" }, "answer").disabled, true, "never twice while it builds");
  assert.deepEqual(answersFor(asks, { "Which repository?": " northwind/ledger " }), { "Which repository?": "northwind/ledger", "Which sites?": "" });
});

test("while it builds the button spins and a status line says so; a miss keeps the questions with Try again", () => {
  const src = read("Composer.jsx");
  assert.match(src, /if \(running\.current\) return;/);
  assert.match(src, /busy === "answer" \? <CircularProgress/);
  assert.match(src, /role="status"[^>]*>Building it from your answers…/);
  assert.match(src, /data-tq-composer-retry=""[\s\S]*?onClick=\{\(\) => go\(last\.current\)\}>\{btnLabel\("try_again"\)\}</);
  assert.match(src, /asks: o\?\.asks, questions: o\?\.questions/);
  assert.match(src, /<Tooltip title=\{can\.hint\}/);
});
