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
