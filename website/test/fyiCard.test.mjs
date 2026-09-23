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
  // the gist rides through gistFor now: it is dropped when it only restates the line above it,
  // which is every assistant idea (fyiRow.js, and test/fyiRow.test.mjs)
  assert.match(fyis, /\{open !== i\.key && !folded && gistFor\(i\) && <div className="tq-fyi-gist">\{gistFor\(i\)\}<\/div>\}/);
  // ...and past a handful every line folds to one, so ten fyi is a list you skim rather than a card
  // you scroll past with twenty doors on it (the owner, 2026-09-16: "4 fyi or 10 fyis at one time")
  assert.match(fyis, /const folded = items\.length > FOLD_AT/);
  assert.doesNotMatch(fyis, /tq-fyi-doors/);                                         // no door on every line (2026-09-23)
  assert.match(fyis, /<button type="button" className="tq-fyi-line" onClick=\{\(\) => setOpen/);   // the line IS the control
  for (const label of ["Reply", "Make task", "Coding agent", "Regular agent", "Talk about it"]) assert.match(fyis, new RegExp(`>${label}</Button>`));
  assert.match(fyis, /propose\("mine", i\)/); assert.match(fyis, /propose\("coder", i\)/); assert.match(fyis, /propose\("regular_agent", i\)/);
  assert.match(fyis, /onPropose\?\.\(verb, i\.key\)/);                               // the entry's own key, never the handful's
  assert.match(fyis, /api\.post\(`\/api\/messages\/\$\{i\.mid\}\/reply`, \{ draft: true \}\)/);   // a reply drafts at once
  assert.doesNotMatch(fyis.slice(0, fyis.indexOf('variant="contained"')), /onDone\?\./);  // no entry action settles the handful
  assert.match(fyis, /\{open === i\.key && \(\s*<div className="tq-card-actions tq-fyi-acts"/);   // ...and they belong to the one you opened
  const view = read("AssistantView.jsx");
  assert.match(view, /api\.post\("\/api\/concierge\/propose", \{ verb, key, table \}\)/);
  assert.match(view, /onPropose=\{actions\.propose\}/);
  assert.match(view, /card: \{ kind: "proposal", key: data\.key, title: data\.label, op: data\.id/);   // the same card the words make
});

test("the grouped context, the task summary and the checklist stay renderable - on the Tasks tab, not the walk", () => {
  const cards = read("assistantCards.jsx");
  const combined = cards.slice(cards.indexOf("function CombinedTaskText"), cards.indexOf("export function CardShell"));
  assert.match(combined, /doc\.task\?\.Summary/); assert.match(combined, /className="tq-task-focus"/);
  assert.match(combined, /items\.map/); assert.match(combined, /tq-task-focus-item/);
  assert.match(combined, /Email context · \{messages\.length\} messages combined by triage/);
  // the walk's cards lead with who wants what and link to the task; the checklist lives on the task
  // (the owner, 2026-09-23: "let's keep the detail task list on the actual task tab")
  assert.match(combined, /const task = list && /);
  const task = cards.slice(cards.indexOf("export function TaskCard"), cards.indexOf("export function FyisCard"));
  assert.match(task, /lead=\{<TaskLead card=\{card\} \/>\}/);
  assert.doesNotMatch(cards, /<CombinedTaskText card=\{card\} \/>/, "every card in the walk passes list={false}");
});

test("a box means an item you can tick, and the job is not said twice", () => {
  // The header wore a checkbox that ticked nothing, above a bold summary that repeated the one
  // item under it (the owner, 2026-09-11: "seems duplicated ... boxes should be for specific
  // items in the task list").
  const cards = read("assistantCards.jsx");
  const combined = cards.slice(cards.indexOf("function CombinedTaskText"), cards.indexOf("export function CardShell"));
  const label = /<div className="tq-task-focus-label">([\s\S]*?)<\/div>/.exec(combined)[1];
  assert.doesNotMatch(label, /tq-task-box/, "the header keeps the word and loses the box");
  assert.match(label, /\{items\.length \? "Task list" : "Task"\}/);
  // the summary stands in only when there is no list to read instead
  assert.match(combined, /\{!items\.length && taskText && <div className="tq-task-focus-text">/);
  // ...and every remaining box belongs to one item
  assert.equal((combined.match(/tq-task-box/g) || []).length, 1);
  assert.match(combined, /const ownTask = messages\.length === 1/);
  assert.match(combined, /const repeatReceipt = messages\.length === 1 && sameWords\(onlyBody, taskWords\)/);   // any channel (2026-09-23)
  assert.match(combined, /!repeatReceipt && <FullText/);
  // the 25px indent existed to clear that header box; without it the list starts at the edge
  const css = read("assistantView.css");
  assert.match(css, /\.tq-task-focus-list \{ margin: 11px 0 0 0;/);
  assert.match(css, /\.tq-task-focus-text \{ margin: 8px 0 0 0;/);
});

test("a paused assistant task exposes resume instead of pretending nobody has worked it", () => {
  const cards = read("assistantCards.jsx");
  const agent = cards.slice(cards.indexOf("export function AgentCard"), cards.indexOf("export function MeetingCard"));
  assert.match(agent, /card\.paused \? "conversation paused"/);
  assert.match(agent, /\/api\/tasks\/\$\{card\.tid\}\/resume/);
  assert.match(agent, /"Continue this session"/);
  assert.match(agent, /card\.paused && card\.tid && <CombinedTaskText/);
  const tasks = read("TasksView.jsx");
  assert.match(tasks, /const resumeGeneralAgent = async/);
  // one set of words for the one act, whichever agent held the conversation (2026-09-15)
  assert.match(tasks, /"Continue this session"/);
  assert.match(tasks, /const continueSession = async/);
  assert.match(tasks, /\/api\/tasks\/\$\{id\}\/continue-session/);
});
