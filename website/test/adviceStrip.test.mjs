// THE ADVISOR'S STRIP AFTER AN ACT (2026-10-19): after Send the line still said the sender was waiting, with Reply lit; the row
// reshuffled when the advice landed; "Thinking about this one…" went to nothing. These pin the contract: every press re-reads the
// advice, the advice only tints the row, and every reason for no line is a sentence that lights one move.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { acted, advisedAny, advisedIn, clustersOf, onPressed, press, put, rowOf } from "../src/actionRow.js";
import { ADVICE_NONE, adviceNone } from "../src/words.js";

const v = (id, group, extra = {}) => ({ id, group, tone: "s", label: id, title: "", disabled: false, why: "", promote: true, lead: false, ...extra });
const read = (n) => fs.readFileSync(path.join(process.cwd(), "src", n), "utf8");
const layout = (r) => clustersOf(r).map((g) => [g.type, g.shown.map((x) => x.id), g.rest.map((x) => x.id)]);

test("a press is heard once it settles, so the advice is read again for the item as the act left it", async () => {
  const heard = [];
  const off = onPressed((id) => heard.push(id));
  let done;
  put("t", [{ ...v("send", "decide"), run: () => new Promise((r) => { done = r; }) }]);
  press("send");
  await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(heard, [], "not before the act has finished");
  done(); await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(heard, ["send"]);
  acted("12:approve"); assert.deepEqual(heard, ["send", "12:approve"], "a card's own button says so the same way");
  off(); put("t", null);
  // ...and the page and a phone's row both listen, as does the draft's own Send under the card
  assert.match(read("AssistantView.jsx"), /onPressed\(\(\) => \{ if \(onTableRef\.current\) readAdvice\(onTableRef\.current, true\); \}\)/);
  assert.match(read("CanvasItem.jsx"), /onPressed\(\(\) => read\(\)\)/);
  assert.equal((read("ReviewDecision.jsx").match(/finally \{ acted\(no\(/g) || []).length, 4, "decide, decideBoth, redraft and copy");
});

test("the advice only tints: the same buttons in the same places with and without it, whatever it picks", () => {
  const list = [v("reply", "decide", { label: "Reply" }), v("share", "decide", { label: "Send out results" }), v("attach", "more", { label: "Attach a file" }),
    v("12:approve", "decide", { label: "Send", card: true, tone: "p" }), v("start-agent", "agent"), v("done", "more", { label: "Mark done" }),
    v("close-note", "more"), v("nat", "more"), v("remind", "more", { label: "Remind me" }), v("next", "next")];
  const plain = layout(rowOf({ ref: "", list }));
  for (const pick of [{ verb: "approve", label: "Send" }, { verb: "reply", label: "Reply" }, { verb: "close", label: "Mark done" }, { verb: "next" }])
    assert.deepEqual(layout(rowOf({ ref: "", list }, pick)), plain, pick.verb);
  assert.ok(!JSON.stringify(layout(rowOf({ ref: "", list }))).includes("slot:"), "the card's own Send leaves no empty slot on the bar - its button is under the draft (2026-10-22, 2026-10-25)");
});

// THE OBVIOUS MOVE IS SILENT (the owner, 2026-10-23: "No suggestion...", "Nothing to decide...", "Thinking..." and every sentence
// explaining a silence go): only no AI is said, with its way out; any other reason lights Next and says nothing
test("no line is still an answer: only no AI is a sentence, and every other silence lights Next - never nothing", () => {
  assert.deepEqual(Object.keys(ADVICE_NONE), ["no_ai"]);
  assert.equal(ADVICE_NONE.no_ai.move, "ai");
  for (const why of ["nothing", "quiet", "working", "off", "cap", "some-new-reason"]) assert.deepEqual(adviceNone(why), { line: "", move: "next" }, why);
  const r = rowOf({ ref: "", list: [v("done", "more"), v("next", "next")] }, { verb: adviceNone("nothing").move });
  assert.equal(r.next.tone, "p");
  assert.equal(rowOf({ ref: "", list: [v("next", "next", { disabled: true })] }, { verb: "next" }).next.tone, "s", "a greyed Next is never lit");
  const view = read("AssistantView.jsx");
  assert.doesNotMatch(view, /AdviceNone|Thinking about this one/);
  assert.doesNotMatch(read("ActionRow.jsx"), /export function AdviceNone/);
  // ...and NO STRIP AT ALL (the owner, 2026-10-26: "maybe keep the box but remove the advisor?"): not on the desk's dock, not over a
  // phone's row - the lit button is the decision, no AI the row's own Connect an AI (browser/dock-strip.test.mjs measures the dock)
  for (const f of ["AssistantView.jsx", "CanvasItem.jsx", "ActionRow.jsx"]) assert.doesNotMatch(read(f), /className="tq-strip"|data-tq-advice="no_ai"/, f);
  assert.doesNotMatch(read("assistantView.css"), /\.tq-strip/);
  assert.match(view, /useVerbs\("noai", \[\{ id: "noai:connect", group: "decide", label: CONNECT_AI,[\s\S]{0,200}\], !firstRun && noAi && !rowConnect\);/);
  assert.match(read("CanvasItem.jsx"), /useVerbs\("noai", \[\{ id: "noai:connect"[\s\S]{0,200}phone && noAi && !rowHas\);/);
  // ...and the dead-end walk holds the page to all of it (STILL, STRIP, REREAD, LIT)
  const walk = fs.readFileSync(path.join(process.cwd(), "deadend_check.mjs"), "utf8");
  for (const rule of ["STILL", "STRIP", "REREAD", "LIT"]) assert.ok(walk.includes(`note("${rule}"`), rule);
  // ...and setup's own line, the one .tq-next the dock still draws, is one line tall (30px since the owner's 2026-10-26 laptop)
  assert.match(read("assistantView.css"), /\.tq-dock \.tq-next \{ margin: 0; min-height: 30px;/);
});

// THE ADVISOR MATRIX (2026-10-19): every moment the Advisor speaks must match the screen. Two it caught: the draft's text cleared, Send
// greyed, and the strip went blank with nothing lit; after a refused send the lit Redraft stood a scroll below the card's edge.
test("an advised move the row has greyed says why it is off, and a move lit on the card is brought into view", () => {
  const list = [v("12:approve", "decide", { label: "Send", card: true, tone: "p", disabled: true, why: "write the reply first" }), v("next", "next")];
  const pick = { verb: "approve", label: "Send" };
  assert.equal(advisedIn(list, pick), null, "a greyed button is never lit");
  assert.equal(advisedAny(list, pick)?.why, "write the reply first", "...but the row still has it, and says why it is off");
  // ...on the greyed button itself, its hover title - the strip's "<X> is off - <why>." went with the strip (2026-10-26)
  const src = read("ActionRow.jsx");
  assert.doesNotMatch(src, /is off - /);
  assert.match(src, /title=\{\(v\.disabled && v\.why\) \|\| v\.title \|\| undefined\}/);
  // ...and held clear of what stands over it (inView.js), marked so the conversation's pin keeps it clear too (the phone pass, 2026-10-20)
  const rd = read("ReviewDecision.jsx");
  assert.match(rd, /if \(!lit\.startsWith\(`\$\{r\.ReviewId\}:`\)\) return undefined;\s*const el = movesRef\.current\?\.querySelector\("\.MuiButton-contained"\);/);
  assert.match(rd, /el\?\.setAttribute\("data-tq-lit", ""\);\s*const stop = holdInView\(el\);/);
  assert.match(read("AssistantView.jsx"), /el\.querySelector\("\[data-tq-lit\]"\)[\s\S]{0,200}floorOf\(body, el\)/);
});

// THE MATRIX'S VERIFY (2026-10-20): a chat's Mark done copies the draft - with the box emptied the line still said "copy it to where the
// question came from"; the move stays the advised one, and says what it does now (`blank`)
test("a move whose text is gone says what it does now, still lit", () => {
  const list = [v("12:approve", "decide", { label: "Mark done", card: true, tone: "p", blank: "The draft box is empty - Mark done closes it with nothing copied" }), v("next", "next")];
  assert.equal(advisedIn(list, { verb: "close", label: "Mark done" })?.id, "12:approve", "still the advised move");
  assert.match(read("actionRow.js"), /\.\.\.\(v\.blank \? \{ blank: v\.blank \} : \{\}\)/, "the row carries it to the strip");
  // ...said by no strip since 2026-10-26: the button is still the lit one
  assert.doesNotMatch(read("ActionRow.jsx"), /onRow\.blank/);
});

test("a move greyed only by the owner's own press in flight is not said to be off (the 2026-10-25 sweep)", async () => {
  const { pressInFlight } = await import("../src/actionRow.js");
  // the owner pressed Send: the draft's verbs grey while it goes, and the strip said "Redraft is off - it cannot be pressed right now."
  assert.ok(pressInFlight([v("12:redraft", "decide", { label: "Redraft", disabled: true }), v("12:approve", "decide", { label: "Sending…", disabled: true, card: true })]));
  assert.ok(pressInFlight([v("reply", "decide", { label: "Drafting…", disabled: true })]), "its own press, mid-way");
  // ...a move that is truly greyed still says why
  assert.ok(!pressInFlight([v("12:redraft", "decide", { label: "Redraft", disabled: true, why: "the reply was sent" })]));
  // ...and since 2026-10-26 nothing says "is off" over the row at all (the strip is gone)
  assert.doesNotMatch(read("ActionRow.jsx"), /is off - /);
});

// THE STRIP'S LINES, SORTED (the owner, 2026-10-26: "maybe keep the box but remove the advisor?"): the few that warn of something on the task
// are drawn in it beside what they are about; every other one the task or the lit button already says
test("a warning lands in the task beside its subject, and every other strip line is dropped", async () => {
  const { taskNote } = await import("../src/advice.js");
  const d = (state, line, extra = {}) => ({ key: "task:7", for: "task:7", verb: "reply", label: "Reply", state, line, by: "rule", ...extra });
  // the draft promising what nothing backs: under the draft, with its Why?
  assert.deepEqual((({ at, line, why }) => ({ at, line, why }))(taskNote(d("draft_ready", "The draft promises what nothing here shows.", { verb: "redraft", label: "Redraft", by: "model" }))),
    { at: "draft", line: "The draft promises what nothing here shows.", why: true });
  // the same ask as another task, and a model's reason the lit button is not the obvious one: at the task's head
  assert.equal(taskNote(d("duplicate", "Same ask as TQ-0012.", { verb: "remove" }))?.at, "task");
  assert.equal(taskNote(d("asked", "TQ-0012 may already cover this - an agent is on it.", { verb: "defer", by: "model" }))?.at, "task");
  // ...said by the task already, or narration of the lit button: nowhere
  for (const [state, line] of [["failed", "Failed: no AI is connected"], ["failed_cause", "Failed: the run stopped"], ["report_failed", "Report failed: timeout"],
    ["invite_clash", "Clashes with Quarter-end planning 9:00-12:00."], ["invite_free", "Free then."], ["stranger", "First mail from vendor.example."],
    ["stopped", "Stopped 2 hours ago."], ["unpushed", "Changes ready - not pushed."], ["waiting_late", "Erin Blake: 4 days, no answer."],
    ["goal_late", "Pick the vendor: 3 days late."], ["asked", "Erin Blake asked 2 hours ago."], ["asked_late", "You usually answer Erin within the hour; this is 3h."]])
    assert.equal(taskNote(d(state, line)), null, state);
  assert.equal(taskNote(d("draft_ready", "")), null, "a silent decision says nothing anywhere");
  assert.equal(taskNote({ none: "no_ai", for: "task:7" }), null, "no AI is the row's Connect an AI, lit");
  // ...drawn under the draft and at the head of the main view, on the canvas and the Tasks tab alike - no line over the Tasks tab's bar
  const page = read("TaskPage.jsx");
  assert.match(page, /const warn = notDone \? \(canvas \? note : taskNote\(taskAdvice\)\) : null;/);
  assert.match(page, /\{pendingReview && warnAt\("draft", \{ mt: 0\.75 \}\)\}/);
  assert.match(page, /\{!fromDrawer && warnAt\("task"\)\}/);
  assert.match(page, /\{fromDrawer && warnAt\("task", \{ mb: 1 \}\)\}/);
  assert.doesNotMatch(page, /data-tq-task-advice/);
  assert.match(read("CanvasItem.jsx"), /onLeave=\{onLeave\} onStay=\{onStay\} note=\{note\} \/>/);
});
