// THE AGENT RECOMMENDS, INSIDE A TASK (the owner, 2026-11-09: "the agents while running should recommend actions, no assistant" /
// "assistant/advisor should only be on rail" / "the agent does not wait for it"). The one filled button on a task's row is the field the
// server serves with the task and with the rail's item (`recommended`, rulebook.recommended - tests/test_recommended.py); the Advisor is
// asked only about its own row, an idea. And Continue pressed on a task opens the task's own box, with nothing handed to the Assistant.
import fs from "node:fs";
import test from "node:test";
import assert from "node:assert/strict";
import { isIdea, ownPick } from "../src/tableState.js";
import { forgetTasks, keepTask, noteRead, recRead, watchRecs } from "../src/taskDetail.js";

const src = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the served field is the row's light in the shape the row already reads, and only an idea row is the Advisor's", () => {
  assert.ok(isIdea("idea:4")); for (const k of ["task:4", "processing:pi_4", "", null]) assert.ok(!isIdea(k), String(k));
  // ...BY ITS ITEM: the rail hands an idea a processing key like any row's, and by the key alone its row read as a task's
  assert.ok(isIdea({ key: "processing:pi_4", kind: "idea" })); assert.ok(isIdea({ key: "idea:4" }));
  for (const it of [{ key: "processing:pi_4", kind: "todo" }, { key: "processing:pi_4", kind: "agent", tid: 4 }, {}]) assert.ok(!isIdea(it), JSON.stringify(it));
  assert.deepEqual(ownPick({ verb: "send_close", label: "Send and close", why: "Sends the file Q3 accruals.xlsx.", state: "draft_ready" }, "processing:pi_4"),
    { verb: "send_close", label: "Send and close", state: "draft_ready", why: "Sends the file Q3 accruals.xlsx.", line: "", by: "agent", for: "processing:pi_4", key: "processing:pi_4" });
  assert.equal(ownPick(null, "task:4"), null, "nothing recommended fills nothing");
  assert.equal(ownPick({ verb: "close" }, ""), null);
  assert.equal(ownPick({ verb: "close" }, "task:4").line, "", "it says no line over the row");
});

test("every read of a task keeps its recommended move, and the view on the table hears each one", () => {
  forgetTasks();
  const seen = [], stop = watchRecs((tid, r) => seen.push([tid, r.rec?.verb || null]));
  noteRead(7, { task: { TaskId: 7 }, state: "approve", recommended: { verb: "send_close", label: "Send and close" } }, 1000);
  assert.equal(recRead(7).rec.verb, "send_close"); assert.equal(recRead(7).at, 1000);
  noteRead(7, { task: { TaskId: 7 }, state: "approve" }, 1100);
  assert.equal(recRead(7).rec.verb, "send_close", "an answer that does not carry the field says nothing about it");
  noteRead(7, { task: { TaskId: 7 }, state: "approve", recommended: null }, 1200);
  assert.equal(recRead(7).rec, null, "present and empty: nothing is filled");
  noteRead(7, { task: { TaskId: 7 }, state: "working", recommended: { verb: "close" } }, 1150);
  assert.equal(recRead(7).rec, null, "a read asked earlier never overwrites a later one");
  keepTask(7, { task: { TaskId: 7 }, state: "agentdone", recommended: { verb: "close", label: "Mark done" } }, undefined, 1300);
  assert.equal(recRead(7).rec.verb, "close", "the page's own read brings it");
  assert.deepEqual(seen, [[7, "send_close"], [7, "send_close"], [7, null], [7, "close"]], "the same state said again still carries its move");
  stop(); forgetTasks();
  assert.equal(recRead(7), null);
});

test("a task's row asks the Advisor nothing: the page reads the field, and only an idea row reads /api/advice", () => {
  const view = src("AssistantView.jsx");
  assert.equal((view.match(/api\.get\("\/api\/advice"/g) || []).length, 2, "the idea row's read and its notes in the past-chats menu");
  const at = view.indexOf("if (!ideaOn(key)) {"), end = view.indexOf('adviceSent.current = { key, at: ++readClock.current };', at);
  assert.ok(at > 0 && end > at);
  const own = view.slice(at, end);
  assert.doesNotMatch(own, /api\/advice/);
  assert.match(own, /if \(it && "recommended" in it\) noteOwn\(key, it\.recommended, seenAt\(it\)\);/, "the rail's item on the table carries it");
  assert.match(own, /const h = tid && heldTask\(tid\) \? recRead\(tid\) : null;\s+if \(h\) noteOwn\(key, h\.rec, h\.at\);/, "and a read of its task");
  assert.match(own, /return;\s+\}\s+let got = null;\s*$/, "nothing below is reached");
  assert.match(view, /useEffect\(\(\) => watchRecs\(\(tid, r\) => \{/, "the task view's own read is the newest word");
  // ...nothing of the Advisor's is mounted over a task's row - only the mark of what is filled; its own row keeps AdvisorNext and its notes
  assert.match(view, /&& <div hidden data-tq-recommended=\{shownAdvice\?\.verb \|\| ""\} \/>\}/);
  assert.match(view, /const ideaOn = \(key\) => isIdea\(currentRef\.current\?\.key === key \? currentRef\.current : key\);/, "the item on the table says its kind");
  assert.match(view, /const ideaRow = isIdea\(currentItem\?\.key === table\.key \? currentItem : table\.key\);/);
  assert.match(view, /ideaRow && <>\s*<AdvisorNext advice=\{shownAdvice\} onPropose=\{pressAdvice\} onErr=\{setErr\} \/>/);
  assert.match(view, /\{current && ideaRow && <AdvisorNotes keyOnTable=\{current\} \/>\}/);
  // ...and neither task view reads it for itself
  for (const f of ["TaskPage.jsx", "CanvasItem.jsx"]) assert.doesNotMatch(src(f), /api\.get\("\/api\/advice"|useItemAdvice|readTaskAdvice/, f);
});

// CONTINUE'S ROAD: a narrow canvas handed the press to the Assistant's conversation (a `tq-continue` event it listened for) to draw the box
// there - with that conversation folded away a lit Continue did nothing. The task takes it itself, at any width - and where its agent
// section is one chat, into that chat's own box: a Continue card over a box already reading "Write to pick the session back up" was two boxes
test("Continue on a task is the task's own chat box and hands nothing to the Assistant", () => {
  const page = src("TaskPage.jsx"), view = src("AssistantView.jsx"), chat = src("GeneralWorkspace.jsx");
  assert.match(page, /if \(a && canvas && t && !sessionView\) \{ if \(chatPane\) intoChat\(""\); else setContinueCard\(\{ note: "" \}\); return; \}/, "at any width");
  assert.match(page, /const intoChat = \(note\) => \{\s*setChatSeed\(\{ id: Date\.now\(\), text: note \|\| "" \}\);/);
  assert.match(page, /querySelector\("\[data-tq-agent-room\] \.tq-aui-input"\)/, "the cursor goes to the task's box, never the Assistant's");
  assert.match(page, /seed=\{chatPane \? chatSeed : null\}/);
  assert.match(chat, /if \(seed\.text && !c\.getState\(\)\.text\) c\.setText\(seed\.text\);/, "its note, never over the owner's words");
  assert.doesNotMatch(page, /\{chatPane && <Box.*\{newStep\(\)\}<\/Box>\}/, "no second box over the chat");
  assert.doesNotMatch(page, /CustomEvent\("tq-continue"/, "no press is sent to the Assistant");
  assert.doesNotMatch(view, /addEventListener\("tq-continue",/, "and it listens for none");
  // ...the box is the task's own card, under its conversation - never over a session's screen, which has no pane for it
  assert.match(page, /\{continueCard && !runFormOpen && !sessionView && <Box data-tq-continue-pane=""/);
  // ...a Continue the owner asked the Assistant for is still claimed by the task view, with its notes - whatever the width
  assert.match(page, /claimRef\.current = canvas && active && t && !sessionView \? \(d\) => \{ if \(Number\(d\?\.tid\) !== Number\(selected\)\) return false; setRestartOpen\(false\); if \(chatPane\) intoChat\(d\.note\); else setContinueCard\(\{ note: d\.note \|\| "" \}\); return true; \} : null;/);
  assert.match(view, /new CustomEvent\("tq-continue-here", \{ detail: \{ tid, note: noteFor\(tid\), claim: \(\) => \{ claimed = true; \} \} \}\)/);
  // ...and what goes wrong is said in the box itself (ContinueBox), on the task
  assert.match(page, /<ContinueBox /);
});

// THE PILL OVER A TASK (2026-11-09): grown under the mouse it rose across the foot of the task's own composer at 1440x900, its Send under it
test("the Assistant's pill never grows over a task's view", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /const popOn = !phone && !old && !walk && !firstRun && lastCardIdx >= 0 && barHolds;/);
  assert.match(view, /const grow = chatApart && !boxWide && !popOn && \(hover \|\| !!text\.trim\(\)\);/);
});

// A LATE ANSWER NO AGENT WAS WOKEN FOR (the owner, 2026-11-10: "job of agent is to be helpful and do as much as possible"): the server lights
// Chase (rulebook.LATE), and the task's row draws Chase only then - its own verb, so the row fills it like any recommended move
test("a lit Chase is drawn on the task's row, only while it is the recommended move, and drafts on the chase road", () => {
  const page = src("TaskPage.jsx");
  assert.match(page, /\.\.\.\(rec\?\.verb === "chase" && !liveSession \? \[\{ id: "chase", group: "decide"/);
  assert.match(page, /runOperation\(api, "task\.chase", t\.TaskId, \{ key: `task:\$\{t\.TaskId\}` \}\)/, "the slipped card's own road, keyed by the task");
});

// A ROW WITH NOTHING LIT SAYS WHY ON THE ITEM'S OWN ROW - a phone's, the narrow window's: the server's sentence for it, and nothing filled.
// NEVER ON THE BAR UNDER THE PAGE (the owner, 2026-11-11: "never asked to have any text under the back next button"): the desk's bar is
// nav only, and for a day it carried that sentence under Back and Next - a sender's "asked 2 hours ago" read as the buttons' own caption
test("a row with nothing lit says why on the item's own row, and the bar under the page draws only its buttons", async () => {
  const { rowWhy, unlitWhy } = await import("../src/railStatus.js");
  const { adviceShown } = await import("../src/advice.js");
  const rec = { verb: null, label: "", why: "Stopped mid-work: the test database was not reachable.", state: "stopped" };
  const pick = ownPick(rec, "task:4");
  assert.equal(pick.why, rec.why); assert.equal(pick.verb, "");
  assert.equal(adviceShown(pick, { key: "task:4", lane: "stopped" }, false), null, "nothing is lit by it");
  assert.equal(rowWhy({ recommended: pick }), rec.why); assert.equal(unlitWhy({ verb: "close", why: "Finished." }), "", "a lit move says its own");
  assert.equal(rowWhy({ why: "An agent is working on this" }), "An agent is working on this", "the rail's own line where nothing is said");
  assert.match(src("ActionRow.jsx"), /why = inline \? row\.why \|\| says : ""/, "no line on a row that is not the item's own");
  const bar = src("AssistantView.jsx").match(/<div className="tq-dock-line">[\s\S]*?<\/div>/)[0];
  assert.match(bar, /<ActionRow advised=\{stripPick \|\| setupLit\} hold=\{rowHold\} early=\{rowEarly\} \/>/, "the bar is handed no sentence");
  assert.doesNotMatch(bar, /says=|rowWhy/);
  assert.match(src("CanvasItem.jsx"), /says=\{lit \? "" : rowWhy\(\{ recommended: read \}\)\}/);
});
