import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";
import { forgetTasks, heldSteps, heldTask, keepTask, prefetchTask } from "../src/taskDetail.js";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
const fake = (calls) => ({ get: async (url) => { calls.push(url); const id = Number(url.split("/")[3]);
  return url.endsWith("/steps") ? { data: { steps: [{ id: 1, text: "Book the room" }] } } : { data: { task: { TaskId: id, DoneWhen: id === 9 ? "booked" : "" } } }; } });

// SWAP, NEVER CLEAR (G8): the view on the table draws its task on the first frame when the read was asked for ahead of it
test("a task read ahead is held for its view, once per task, and a goal brings its steps", async () => {
  forgetTasks();
  const calls = [], api = fake(calls);
  assert.equal(heldTask(4), null);
  await prefetchTask(api, 4); await prefetchTask(api, 4); await new Promise((r) => setTimeout(r, 0));
  assert.deepEqual(calls.filter((u) => u === "/api/tasks/4"), ["/api/tasks/4"], "one read per task while it is fresh");
  assert.ok(calls.includes("/api/tasks/4/waitroom") && calls.includes("/api/terminals"), "its waiting room and the sessions come with it");
  assert.equal(heldTask(4).task.TaskId, 4);
  await prefetchTask(api, 9); await new Promise((r) => setTimeout(r, 0));
  assert.equal(heldSteps(9)[0].text, "Book the room");
  keepTask(9, { task: { TaskId: 9, DoneWhen: "booked", Title: "newer" } });
  assert.equal(heldTask(9).task.Title, "newer");
  assert.ok(heldSteps(9), "a view's own read keeps the goal's steps");
  keepTask(9, { task: { TaskId: 8 } });                    // another task's answer is never held under this one
  assert.equal(heldTask(9).task.Title, "newer");
  forgetTasks();
  assert.equal(heldTask(4), null);
});

test("a failed read ahead holds nothing, so the view reads it itself", async () => {
  forgetTasks();
  await prefetchTask({ get: async () => { throw new Error("down"); } }, 5);
  assert.equal(heldTask(5), null);
});

test("the view draws from the held read, and the reads ahead are where the next view is already known", () => {
  const page = src("TaskPage.jsx"), view = src("AssistantView.jsx"), search = src("SearchEverything.jsx");
  assert.match(page, /const \[detail, setDetail\] = useState\(\(\) => heldTask\(selected\)\);/);
  assert.match(page, /setDetail\(data\); keepTask\(id, data, undefined, asked\);/);
  assert.match(view, /useEffect\(\(\) => \{ if \(nextTid\) prefetchTask\(api, nextTid\); \}, \[nextTid, displayRevision\(pile\)\]\);/);   // the row Next brings
  assert.match(view, /onPointerEnter=\{\(\) => \{ if \(!isCur && i\.tid\) prefetchTask\(api, i\.tid\); \}\}/);        // a rail row under the pointer
  assert.match(search, /if \(aheadTid\) prefetchTask\(api, aheadTid\);/);                                             // a search hit highlighted
  // an act makes the held reads old - but Next is no act, it is what they are for
  assert.match(view, /onPressed\(\(id\) => \{ if \(!\/\(\^\|:\)next\$\/\.test\(String\(id \|\| ""\)\)\) forgetTasks\(actedTid\.current \?\? null\); \}\)/);
  assert.match(view, /useEffect\(\(\) => \{ if \(currentItem\?\.tid && earlyRef\.current\?\.key !== currentItem\.key\) actedTid\.current = currentItem\.tid; \}, \[currentItem\]\);/,
    "an act lets go of its own task's read only - not the next item's, just before the walk goes on to it");
});

test("a task's session is held with it: unknown until read, null for a task no agent holds", async () => {
  const { heldTerm, keepTerms } = await import("../src/taskDetail.js");
  forgetTasks();
  assert.equal(heldTerm(3), undefined, "not read yet - the view looks for itself");
  keepTerms([{ taskId: 3, sid: "s1", alive: false }, { taskId: 3, sid: "s2", alive: true }]);
  assert.equal(heldTerm(3).sid, "s2", "the live one first, as findTerm picks");
  assert.equal(heldTerm(7), null);
  forgetTasks(7);
  assert.equal(heldTerm(3).sid, "s2", "another task's write leaves this one's session as it was");
  assert.equal(heldTerm(7), undefined, "...and its own is unknown again");
  forgetTasks();
  assert.equal(heldTerm(3), undefined, "a write that names no task lets the whole list go");
});

// NEXT PUTS THE NEXT ONE UP AT THE PRESS (G8): the fold left the canvas with no view and the rail ringing the item put down until the
// server answered - the item the capture names is drawn at once from its held read, and the answer fills that same line
test("Next draws what its capture names in the same frame as the fold, and the answer fills that line in place", () => {
  const view = src("AssistantView.jsx"), turns = src("assistantTurns.js");
  assert.match(view, /const drawsNow = \(c\) => !!c && showsTask\(c, cardFor\(c\)\) && !!heldTask\(c\.tid\) && heldTerm\(c\.tid\) !== undefined;[^]*aheadItem && \(drawsNow\(aheadItem\) \|\|/, "a Next only from a read already held - never an empty view");
  assert.match(view, /drawAhead\(\{ \.\.\.line, text: "", card: aheadItem \}\)/);
  assert.match(view, /setMsgs\(\(m\) => \[\.\.\.m, \{ \.\.\.line, ahead: true \}\]\);\s+putOnTable\(line\.card\);/);
  assert.match(view, /const id = keep \? ahead\.id : `a\$\{Date\.now\(\)\}`;/, "the same id: the view stays mounted");
  assert.match(view, /setMsgs\(\(m\) => m\.filter\(\(x\) => x\.id !== rec\.id\)\);\s+const t = rec\.table;/, "a failure puts the table back");
  assert.match(turns, /!m\.ahead && !NOT_ITEM\.has/, "a line drawn ahead is no copy of the item for oneCopy to fold others into");
  // ...an item an agent is working included: the walk takes it like any task, and its card is the agent's pane (2026-10-21)
  assert.match(view, /i\.key === aheadKey && !i\.settling\)/, "an item an agent has is drawn ahead like the rest");
});

// A ROW CLICKED COLD IS DRAWN AT THE CLICK (owner-approved, 2026-10-20): the old view and its ring stayed up for the whole read
test("a rail row clicked before its task is read puts its frame up at the click, titled, over the view's loading state", () => {
  const view = src("AssistantView.jsx"), page = src("TaskPage.jsx"), item = src("CanvasItem.jsx");
  assert.match(view, /else if \(aheadItem && \(drawsNow\(aheadItem\) \|\| \(key && showsTask\(aheadItem, cardFor\(aheadItem\)\)\)\)\)/,
    "a pick by name needs no held read; a Next still does");
  assert.match(item, /<TaskPage taskId=\{card\.tid\} title=\{card\.title \|\| ""\}/, "the frame knows which item it is");
  assert.match(page, /data-tq-task-loading=[\s\S]{0,800}canvas && !!title && <Typography data-tq-task-loading-title=""/, "...and says it while it reads");
});

// A CLOSE PUTS THE NEXT ONE UP AT ITS PRESS (owner-approved, 2026-10-20): the next was drawn only after the server recorded the close
test("Mark done, Remove and Remind me draw the next item at the press; a failed close takes it down and puts the closed one back", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /putDown: \(key, tid = null\) => \{[^\n]*drawNextEarlyRef\.current\?\.\(key\); \}/, "the press that folds the item draws the next");
  assert.match(view, /pickUp: \(key, why\) => \{ takeEarlyBackRef\.current\?\.\(\);/, "a close that fails takes the drawn one down first");
  assert.match(view, /const takeEarlyBack = \(\) => \{ const e = earlyRef\.current; earlyRef\.current = null; if \(e\) unshow\(e\); \};/, "...and the closed item is back on the table");
  assert.match(view, /earlyRef\.current = drawAhead\(\{ id: `a\$\{Date\.now\(\)\}`, role: "assistant", text: "", options: \[\], chips: \[\], card: it \}\);/, "on the one road ahead");
  assert.match(view, /!heldTask\(it\.tid\) \|\| heldTerm\(it\.tid\) === undefined\) return;/, "only from a held read, as a Next draws");
  assert.match(view, /if \(early\) \{ selectionRef\.current = null; currentRef\.current = null; carryRef\.current = early; \}\s+else clearTable\(\);/,
    "advance keeps the drawn item up and hands it to the walk's surface");
  assert.match(view, /if \(keeps\) aheadRef\.current = \{ \.\.\.carried, hash: null, table: tableNow\(\) \};\s+else dropCarried\(\);/,
    "the answer fills the drawn line in place when it names the same item, and takes it down when not");
});

// WHICH READ IS NEWER (the owner, 2026-10-23: "this shows agent working but it's not working"): the rail was built under the server's lock
// for minutes, and its "agent working" stood over a task whose own read said the agent had finished - a task read asked after the rail's
// is the newer word on that task, for its rail row and its header pill alike
test("a task read speaks over the rail only when it was asked after the rail's, and the rail draws again when one says something new", async () => {
  const { notePile, noteRead, pageRead, watchReads } = await import("../src/taskDetail.js");
  forgetTasks();
  const seen = [], stop = watchReads((tid) => seen.push(tid));
  notePile(1000);
  noteRead(7, { task: { TaskId: 7 }, state: "approve", session: null }, 900);
  assert.equal(pageRead(7), null, "a read asked before the rail's is older than it");
  noteRead(7, { task: { TaskId: 7 }, state: "approve", session: { alive: false } }, 1100);
  assert.deepEqual(pageRead(7), { at: 1100, state: "approve", live: false });
  noteRead(7, { task: { TaskId: 7 }, state: "working", session: { alive: true } }, 1050);
  assert.equal(pageRead(7).state, "approve", "a read asked earlier never overwrites a later one, whenever it lands");
  noteRead(7, { task: { TaskId: 8 } }, 1200);
  assert.equal(pageRead(7).at, 1100, "another task's answer is never kept under this one");
  notePile(1300);
  assert.equal(pageRead(7), null, "a newer rail stands again");
  keepTask(7, { task: { TaskId: 7 }, state: "agentdone" }, undefined, 1400);
  assert.equal(pageRead(7).state, "agentdone", "the page's own read is kept with the moment it was asked");
  assert.deepEqual(seen, [7, 7], "a read that says the same thing again draws nothing");
  stop(); forgetTasks();
  assert.equal(pageRead(7), null);
});

test("the rail stamps its reads and its rows and the header pill take the task's newer read", () => {
  const view = src("AssistantView.jsx"), page = src("TaskPage.jsx");
  assert.match(view, /pileRef\.current = refreshPilePresentation\(pileRef\.current, data\); notePile\(askedAt\);/, "a rail read, stamped when asked");
  assert.match(view, /notePile\(forcedLoadStartedAt\.current\);/, "...and one that came with an answer");
  assert.match(view, /const page = i\.tid \? pageRead\(i\.tid\) : null, why = rowWhy\(i, page\);/);
  assert.match(view, /railStatus\(i, !canSend\(sendCaps, i\.channel\), page\)/, "the row's icon");
  assert.match(view, /useEffect\(\(\) => watchReads\(\(\) => reread\(\(n\) => n \+ 1\)\), \[\]\);/, "the rail draws again on a new read");
  assert.match(page, /page: rail\?\.tid \? pageRead\(rail\.tid\) : null \}\);/, "the header pill takes the same read");
});
