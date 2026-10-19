// THE ONE LIST OF BUTTONS (taskuary/buttons.json, the owner, 2026-10-17: "if it's in one code place it's easy to update it later").
// The page reads every button's words through src/buttons.js; these tests hold that line - the Advisor's verb finds the task page's
// own button for it, no page file types a button's label itself, and no removed name is left anywhere a person can read it.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { ALL_LABELS, REMOVED, VERBS, hint, label, labelOfRow, liveVerb, rowsOf, verbOfRow } from "../src/buttons.js";
import { advisedAny, advisedIn, rowOf } from "../src/actionRow.js";

const json = JSON.parse(fs.readFileSync(path.join(process.cwd(), "..", "taskuary", "buttons.json"), "utf8"));
const SRC = path.join(process.cwd(), "src");
const files = fs.readdirSync(SRC).filter((f) => /\.(jsx?|mjs)$/.test(f) && f !== "buttons.js");
// what a person can read: string literals and JSX text, with comments gone (a comment reaches nobody)
// ...a block comment only where one can start (a line's head, a JSX `{`): "src/**/*.js" in a string is not one
const strip = (s) => s.replace(/(^[ \t]*|\{)\/\*[\s\S]*?\*\/\}?/gm, "").replace(/(^|\s)\/\/[^\n]*/g, "$1");
// ...each literal taken whole (a template's closing tick never opens the next one); a template with `${}` in it is not one word
const said = (code) => [...code.matchAll(/"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\]|\\.)*)`|>\s*([^<>{}\n]+?)\s*</g)]
  .map((m) => m[1] ?? m[2] ?? (m[3]?.includes("${") ? "" : m[3]) ?? m[4]);
const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: labelOfRow(id) || id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });

test("buttons.js reads buttons.json: one label, its state words, its hint, the row ids", () => {
  assert.equal(label("close"), json.verbs.close.label);
  assert.equal(label("approve", "action"), json.verbs.approve.states.action);
  assert.equal(label("redraft", "none"), json.verbs.redraft.states.none);
  assert.equal(label("redraft", "nope"), json.verbs.redraft.label, "an unknown state is the label");
  assert.equal(hint("defer"), json.verbs.defer.hint);
  assert.equal(hint("approve", "action"), json.verbs.approve.state_hints.action);
  for (const [verb, b] of Object.entries(json.verbs)) for (const r of b.row) { assert.equal(verbOfRow(r), verb); assert.equal(labelOfRow(r), b.label); }
  assert.equal(verbOfRow("12:approve"), "approve", "a draft's own `<rid>:verb` id");
  assert.equal(verbOfRow("kind"), "change_kind", "the task page's pickers are on the list too (the dead-end walk's NAMES, 2026-10-18)");
  assert.equal(verbOfRow("no-such-row"), null);
  assert.deepEqual(rowsOf("regular_agent"), ["start-agent", "send-general"]);
  for (const b of Object.values(json.verbs)) { assert.ok(ALL_LABELS.includes(b.label)); for (const s of Object.values(b.states || {})) assert.ok(ALL_LABELS.includes(s)); }
  assert.equal(ALL_LABELS.length, new Set(ALL_LABELS).size);
});

test("a removed verb is never drawn: an old word lands on the verb it became, Prep me on nothing", () => {
  assert.deepEqual(REMOVED, { prep: null, later: "defer", skip: "defer", archive: "not_ours", done: "close" });
  assert.equal(liveVerb("later"), "defer"); assert.equal(liveVerb("done"), "close"); assert.equal(liveVerb("prep"), null);
  assert.equal(label("skip"), label("defer")); assert.equal(label("prep"), "");
  for (const r of Object.keys(REMOVED)) assert.ok(!(r in VERBS), r);
});

// THE ADVISOR FILLS THE REAL BUTTON: its verb (advisor.py) is not the task page's id - close/done, defer/remind, stop_agent/save-end -
// and matching only ids drew a second button beside the real one. buttons.json's `row` lists are the map.
test("the Advisor's verb finds the task page's own button for the same act, by buttons.json's row ids", () => {
  const list = [v("reply", "decide", { tone: "p" }), v("redraft", "decide"), v("continue", "agent"), v("save-end", "agent"), v("start-agent", "agent"),
    v("done", "more"), v("remind", "more"), v("close-note", "more"), v("nat", "more"), v("hand", "more"), v("reshape", "more"), v("next", "next")];
  for (const [verb, id] of [["close", "done"], ["defer", "remind"], ["stop_agent", "save-end"], ["regular_agent", "start-agent"], ["redraft", "redraft"],
    ["reply", "reply"], ["continue", "continue"], ["close_note", "close-note"], ["remove", "nat"], ["forward", "hand"], ["split", "reshape"]]) {
    const pick = { verb, label: label(verb) };
    assert.equal(advisedIn(list, pick)?.id, id, `${verb} -> ${id}`);
    assert.equal(advisedAny(list, pick)?.id, id, `${verb}: found, so the Advisor adds no button of its own`);
    const r = rowOf({ ref: "", list }, pick), all = [...r.decide, ...r.agent];
    assert.equal(all.filter((x) => x.tone === "p").map((x) => x.id).join(), id, `${verb}: the real button is the filled one`);
    assert.ok(!all.some((x) => String(x.id).startsWith("advice:")));
  }
  assert.equal(advisedIn([v("send-general", "agent")], { verb: "regular_agent" })?.id, "send-general");
  // an old saved pick of a removed verb still lands on the live button; Prep me on none
  assert.equal(advisedIn(list, { verb: "done" })?.id, "done");
  assert.equal(advisedIn(list, { verb: "later" })?.id, "remind");
  assert.equal(advisedIn(list, { verb: "prep", label: "Prep me" }), null);
  // a draft's own `<rid>:` buttons: Mark done is the advisor's close, and an advised Send is never a Redraft that keeps the approve id
  const draft = [v("12:approve", "decide", { label: label("redraft"), card: true }), v("12:done", "decide", { closes: true })];
  assert.equal(advisedIn(draft, { verb: "close", label: label("close") })?.id, "12:done");
  assert.equal(advisedIn(draft, { verb: "approve", label: label("approve") }), null, "Redraft is not Send");
  assert.equal(advisedIn([v("12:approve", "decide", { label: label("approve", "action") })], { verb: "approve" })?.id, "12:approve", "Approve sends a proposal");
});

// a label typed in a page file is the second place the owner's word lives - the next rename misses it
const NOT_BUTTONS = {
  "actionRow.js": ["Reply"],                                   // the REPLY section's heading over its buttons (TYPES)
  "FeedView.jsx": ["Reply"],                                   // the story's Reply step and an untitled message's subject
  "TaskPage.jsx": ["Reply"],                                   // an untitled message's subject
  "assistantCards.jsx": ["New task"],                          // the channel name of a task you started
  "demoApi.js": ["New task"],                                  // a new demo task's default title
  "TasksView.jsx": ["New task"],                               // the new-task dialog's title
  // a setup wizard's own step forward - not the walk's Next, which puts an item down
  "FirstRun.jsx": ["Next"], "FirstRunAbout.jsx": ["Next"], "SkillImport.jsx": ["Next"],
  // other sends that are not a draft's Send (2026-10-18, when approve's label became "Send"): the bug report's own, the chat
  // composer's arrow, and the answer box's Send/Queue to a waiting agent
  "BugReportDialog.jsx": ["Send"], "GeneralWorkspace.jsx": ["Send"], "ui.jsx": ["Send"],
  // a report's setup wizard steps forward with its own Continue - not the agent's (2026-10-18, when continue's label became "Continue")
  "ReportsView.jsx": ["Continue"],
};
test("no page file types a button's label: every one is read from buttons.js", () => {
  const hits = [];
  for (const f of files) {
    const ok = NOT_BUTTONS[f] || [];
    for (const s of said(strip(fs.readFileSync(path.join(SRC, f), "utf8")))) if (ALL_LABELS.includes(s.trim()) && !ok.includes(s.trim())) hits.push(`${f}: "${s.trim()}"`);
  }
  assert.deepEqual(hits, []);
});

test("no removed or second name for a button is left where a person can read it", () => {
  const gone = ["Prep me", "Snooze", "Make a task", "Make task", "Take it myself", "Redraft it", "Run it", "Merge & close", "Continue session", "Close out",
    "Archive it", "Handled", "Draft a follow-up", "Hand to agent", "Hand to coding agent", "Regular agent", "A non-coding agent", "Silence this sender",
    "Block them in Settings", "Send back to the agent", "Continue the agent", "Refresh the draft", "Refresh draft", "Mark it handled", "Test the connection",
    "Run the report again", "Send the answer to the agent", "Write reply", "Start an agent", "Start another agent", "Send to non-coding agent",
    "Use non-coding agent", "Start coding session", "Approve & send", "Run action", "Save playbook", "Draft a reply", "Check again"];
  const hits = [], heading = { "TaskPage.jsx": ["Close out"] };   // the task page's third section is named Close out - a heading, no button
  for (const f of files) for (const s of said(strip(fs.readFileSync(path.join(SRC, f), "utf8"))))
    if (gone.includes(s.trim()) && !(heading[f] || []).includes(s.trim())) hits.push(`${f}: "${s.trim()}"`);
  assert.deepEqual(hits, []);
  const code = files.map((f) => strip(fs.readFileSync(path.join(SRC, f), "utf8"))).join("\n");
  assert.doesNotMatch(code, /verb === "prep"|\/api\/calendar\/prep/, "Prep me is gone, its road too");
  assert.doesNotMatch(code, /\bshortLabel\b/, "no second, shorter name for the bar");
});
