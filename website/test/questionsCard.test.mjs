// THE AGENT'S QUESTIONS ARE ONE CARD (the owner, 2026-11-26: an agent that interviews him asks on one card, answered together with one press):
// the one review card every other kind is drawn by, a field a question - a pick where the agent gave choices, a line to type in always - one
// press that sends every answer, and, pressed, the same card showing what he answered. Invented bakery.
import test from "node:test";
import assert from "node:assert/strict";
import { answeredAny, answersFor, answersOf, askFields, asksOf } from "../src/questionsCard.js";
import { outcomeOf, proposalPresentation, reviewText } from "../src/reviewProposal.js";

const P = { action: "questions", title: "Before I build the site", questions: [{ question: "Who is the site for?" },
  { question: "Which pages?", choices: ["Home, Menu, Contact", "One page"] }, { question: "What tone?", choices: ["Warm", "Plain"] }] };
const rv = (over = {}) => ({ ReviewId: 12, TaskId: 7, Kind: "action", Status: "pending", CreatedAt: "2026-11-26 09:00:00", Reason: "Before I build the site",
  DraftText: JSON.stringify(P), ...over });
const pressed = rv({ Status: "approved", FinalText: JSON.stringify({ ...P, result: { answers: [{ question: "Who is the site for?", answer: "Locals" },
  { question: "Which pages?", answer: "One page" }, { question: "What tone?", answer: "" }] } }) });

test("its data is its questions: a field each, his answers by place, and only what he typed goes", () => {
  assert.deepEqual(asksOf(P).map((q) => q.choices.length), [0, 2, 2]);
  assert.deepEqual(asksOf({ action: "run_tool", questions: P.questions }), [], "only a questions card has any");
  const got = [], fs = askFields(P, ["Locals"], (i, v) => got.push([i, v]));
  assert.deepEqual(fs.map((f) => [f.type, f.label, f.value, f.editable]), [["ask", "Who is the site for?", "Locals", true], ["ask", "Which pages?", "", true], ["ask", "What tone?", "", true]]);
  fs[1].onChange("One page"); assert.deepEqual(got, [[1, "One page"]]);
  assert.equal(askFields(P, ["Locals"])[0].editable, false, "pressed: read-only");
  assert.deepEqual(answersFor(P, [" Locals ", undefined]), ["Locals", "", ""]);
  assert.equal(answeredAny(["", "  "]), false); assert.equal(answeredAny(["", "Warm"]), true);
  assert.deepEqual(answersOf(JSON.parse(pressed.FinalText)), ["Locals", "One page", ""]);
});

test("it reads as a card of questions - its heading, one press named for what it does - never its JSON in a box", () => {
  const p = proposalPresentation(rv());
  assert.equal(p.lead, "Before I build the site"); assert.equal(p.approveLabel, "Send answers"); assert.equal(p.asks.length, 3);
  assert.match(p.leadWhy, /^3 questions/); assert.equal(p.bare, true); assert.equal(reviewText(rv()), "");
  assert.equal(proposalPresentation(rv({ DraftText: JSON.stringify({ ...P, title: "" }) })).lead, "The agent has a few questions");
  assert.deepEqual([outcomeOf(pressed).mark, outcomeOf(pressed).label], ["approved", "✓ Answered"]);
});

const AXIOS = { name: "axios", setup(b) { b.onResolve({ filter: /^axios$/ }, () => ({ path: "axios", namespace: "stub" }));
  b.onLoad({ filter: /.*/, namespace: "stub" }, () => ({ loader: "js", contents: "const a = { get: async () => ({ data: {} }), post: async () => ({ data: {} }), put: async () => ({ data: {} }), interceptors: { request: { use() {} }, response: { use() {} } }, defaults: { headers: { common: {} } } }; export default { ...a, create: () => a };" })); } };
const page = async () => {
  const hold = setInterval(() => {}, 1000);
  try {
    const { build } = await import("esbuild");
    const out = await build({ stdin: { resolveDir: new URL("..", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"), loader: "jsx", contents: `
      import React from "react"; import { renderToStaticMarkup } from "react-dom/server.browser";
      import ReviewDecision from "./src/ReviewDecision.jsx"; import PassedCard from "./src/PassedCard.jsx";
      export const waiting = (r) => renderToStaticMarkup(<ReviewDecision review={r} onChanged={() => {}} />);
      export const settled = (r) => renderToStaticMarkup(<PassedCard reviews={[r]} />);` },
      bundle: true, write: false, format: "esm", jsx: "automatic", platform: "node", logLevel: "silent", plugins: [AXIOS], define: { "process.env.NODE_ENV": '"production"' },
      loader: { ".css": "empty", ".png": "empty", ".svg": "empty", ".jpg": "empty", ".woff2": "empty", ".json": "json" } });
    const { writeFileSync } = await import("node:fs"), { join } = await import("node:path"), { pathToFileURL } = await import("node:url");
    const f = join((await import("../browser/tempdirs.mjs")).ownTemp("tq-asks-"), "page.mjs"); writeFileSync(f, out.outputFiles[0].text);
    return import(pathToFileURL(f).href);
  } finally { clearInterval(hold); }
};

test("drawn by the one review card: every question on it, a pick per choice, one press that waits for an answer - and pressed, his answers stay", async () => {
  const { waiting, settled } = await page(), html = waiting(rv());
  assert.equal((html.match(/data-tq-review-card=/g) || []).length, 1, "one card");
  assert.match(html, /data-tq-review-kind="questions"/);
  assert.deepEqual([...html.matchAll(/data-tq-ask-question="">([^<]*)</g)].map((m) => m[1]), P.questions.map((q) => q.question));
  assert.deepEqual([...html.matchAll(/data-tq-ask-choice="([^"]*)"/g)].map((m) => m[1]), ["Home, Menu, Contact", "One page", "Warm", "Plain"]);
  assert.equal((html.match(/data-tq-ask-line=/g) || []).length, 3, "each can be answered in his own words");
  assert.match(html, /<button[^>]*disabled=""[^>]*data-tq-press="approve"[^>]*>Send answers</, "nothing to send until he answers one");
  assert.match(html, /data-tq-press="reject"[^>]*>Dismiss</);
  assert.doesNotMatch(html, /&quot;action&quot;|data-tq-draft-box=""(?![^>]*display:none)/, "its JSON is never a box of words");
  const after = settled(pressed);
  assert.match(after, /data-tq-pressed="approved"[^>]*>✓ Answered</);
  assert.deepEqual([...after.matchAll(/data-tq-ask-answer=""[^>]*>([^<]*)</g)].map((m) => m[1]), ["Locals", "One page", "No answer"]);
  assert.doesNotMatch(after, /data-tq-ask-choice=|<textarea/, "nothing left to press or type");
});
