// The fyi handful and the single item, as the cards draw them (PW-151/152): a summary for each entry and
// actions on ONE entry through the proposal road; the task card carries the whole grouped context, the
// task summary and the checklist.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("each fyi entry shows its own summary and acts alone through the proposal road", () => {
  const cards = read("assistantCards.jsx");
  const fyis = cards.slice(cards.indexOf("export function FyisCard"), cards.indexOf("export function WrapupCard"));
  assert.match(fyis, /\{i\.summary \|\| i\.preview\}/);                              // the summary, the gist as the fallback
  for (const label of ["Reply", "Make task", "Coding agent", "Regular agent"]) assert.match(fyis, new RegExp(`>${label}</Button>`));
  assert.match(fyis, /propose\("mine", i\)/); assert.match(fyis, /propose\("coder", i\)/); assert.match(fyis, /propose\("regular_agent", i\)/);
  assert.match(fyis, /onPropose\?\.\(verb, i\.key\)/);                               // the entry's own key, never the handful's
  assert.match(fyis, /api\.post\(`\/api\/messages\/\$\{i\.mid\}\/reply`, \{ draft: true \}\)/);   // a reply drafts at once
  assert.doesNotMatch(fyis.slice(0, fyis.indexOf('variant="contained"')), /onDone\?\./);  // no entry action settles the handful
  const view = read("AssistantView.jsx");
  assert.match(view, /api\.post\("\/api\/concierge\/propose", \{ verb, key \}\)/);
  assert.match(view, /onPropose=\{actions\.propose\}/);
  assert.match(view, /card: \{ kind: "proposal", key: data\.key, title: data\.label, op: data\.id/);   // the same card the words make
});

test("the task card carries the whole grouped context, the task summary and the checklist", () => {
  const cards = read("assistantCards.jsx");
  const combined = cards.slice(cards.indexOf("function CombinedTaskText"), cards.indexOf("export function CardShell"));
  assert.match(combined, /doc\.task\?\.Summary/); assert.match(combined, /<b>The task:<\/b> \{doc\.task\.Summary\}/);
  assert.match(combined, /checklistMarkdown\(doc\.checklist\)/);
  assert.match(combined, /messages combined by triage/);
  const task = cards.slice(cards.indexOf("export function TaskCard"), cards.indexOf("export function FyisCard"));
  assert.match(task, /\{card\.tid && <CombinedTaskText card=\{card\} \/>\}/);
});
