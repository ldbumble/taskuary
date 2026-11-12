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
  assert.ok(calls.includes("/api/terminals"), "the sessions come with it");
  // ...and never its waiting room: the view no longer draws it, and its own 3 s poll read it in series behind every task read (2026-10-26)
  assert.ok(!calls.some((u) => u.endsWith("/waitroom")), "no waiting room read for a view that draws none");
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

// NEVER A BLANK BEAT (seen 2026-11-11: a task opened for the first time drew its header and box over an empty chat for a quarter of a
// second): the chat's list is asked for with the task, held with it through the view's own read, and is the chat's first frame
test("a task read ahead brings its chat's list, and the chat draws it on its first frame", async () => {
  forgetTasks();
  const { heldConversation } = await import("../src/taskDetail.js");
  const calls = [], list = { rev: "r1", items: [{ id: "m:1", kind: "arrival" }], pending: [] };
  const api = { get: async (url) => { calls.push(url); return url.endsWith("/conversation") ? { data: list } : { data: { task: { TaskId: 4 } } }; } };
  assert.equal(heldConversation(4), null);
  await prefetchTask(api, 4); await new Promise((r) => setTimeout(r, 0));
  assert.ok(calls.includes("/api/tasks/4/conversation"));
  assert.equal(heldConversation(4).rev, "r1");
  keepTask(4, { task: { TaskId: 4, Title: "newer" } });
  assert.equal(heldConversation(4).rev, "r1", "the view's own read of the task keeps it");
  forgetTasks(4); assert.equal(heldConversation(4), null, "a write to the task lets it go");
  const view = src("GeneralWorkspace.jsx");
  assert.match(view, /const listOf = \(tid\) => \{ if \(!LISTS\.has\(tid\)\) \{ const h = heldConversation\(tid\); if \(h\) LISTS\.set\(tid, h\); \} return LISTS\.get\(tid\) \|\| null; \};/);
  assert.match(view, /const \[list, setList\] = useState\(\(\) => listOf\(tid\)\)/);
});

// ...AND THE CHAT DREW NOTHING UNTIL ITS OWN READ OF THE AGENT'S STATE LANDED (recorded 2026-11-12: on a rail click, Next and Back the task's
// header stood over a spinner for up to a second, its list already in hand): that read is asked ahead and held with the task too, and
// the chat's first frame is drawn from it
test("a task read ahead brings what its chat stands on, and the chat is drawn from it on its first frame", async () => {
  forgetTasks();
  const { heldChat } = await import("../src/taskDetail.js");
  const calls = [], chat = { messages: [], providers: [{ id: 3 }] };
  const api = { get: async (url) => { calls.push(url); return url.endsWith("/assistant") ? { data: chat } : url.endsWith("/conversation") ? { data: { items: [] } } : { data: { task: { TaskId: 6 } } }; } };
  assert.equal(heldChat(6), null);
  await prefetchTask(api, 6); await new Promise((r) => setTimeout(r, 0));
  assert.ok(calls.includes("/api/tasks/6/assistant"));
  assert.equal(heldChat(6), chat);
  keepTask(6, { task: { TaskId: 6, Title: "newer" } });
  assert.equal(heldChat(6), chat, "the view's own read of the task keeps it");
  forgetTasks(6); assert.equal(heldChat(6), null, "a write to the task lets it go");
  const view = src("GeneralWorkspace.jsx");
  assert.match(view, /const chatOf = \(tid\) => \{ if \(!CHATS\.has\(tid\)\) \{ const h = heldChat\(tid\); if \(h\) CHATS\.set\(tid, h\); \} return CHATS\.get\(tid\) \|\| null; \};/);
  assert.match(view, /const \[data, setData\] = useState\(first\);/);
  assert.doesNotMatch(view, /setData\(null\)/, "a chat drawn again never empties itself to read");
});

// ...AND A VIEW MOUNTED BEFORE IT LANDED DRAWS IT AS IT LANDS (recorded 2026-11-12 on the built app: a rail row clicked straight away drew
// its head and then 830 ms of spinner where the chat goes - the read asked at the press landed half-way through and was never drawn)
test("a chat read still on its way when the view mounts is handed over as it lands, unless the view's own read came first", async () => {
  forgetTasks();
  const { aheadChat, heldChat } = await import("../src/taskDetail.js");
  let land; const chat = { messages: [], providers: [] };
  const api = { get: (url) => (url.endsWith("/assistant") ? new Promise((r) => { land = () => r({ data: chat }); }) : Promise.resolve({ data: url.endsWith("/conversation") ? { items: [] } : { task: { TaskId: 7 } } })) };
  prefetchTask(api, 7); await new Promise((r) => setTimeout(r, 0));
  const p = aheadChat(7);
  assert.ok(p, "a read on its way is offered to the view");
  land(); assert.equal(await p, chat);
  assert.equal(heldChat(7), chat); assert.equal(aheadChat(7), null, "once landed it is held, not ahead");
  const view = src("GeneralWorkspace.jsx");
  assert.match(view, /if \(!first\(\)\) aheadChat\(task\.TaskId\)\?\.then\(\(d\) => \{ if \(live && !own && d\) accept\(d\); \}\);/);
  assert.match(view, /\.then\(\(r\) => \{ own = true; if \(live\) accept\(r\.data\); \}\)/, "the view's own read is newer: what lands ahead after it is not drawn");
  // ...and the task view's first frame waits for it - capped - so head and chat are one move; never drawn from the list alone, whose files and
  // cards then landed a beat later and grew the turn by 900 px (recorded 2026-11-12)
  const page = src("TaskPage.jsx");
  assert.match(page, /const \[detail, setDetail\] = useState\(\(\) => \(aheadChat\(selected\) \? null : heldTask\(selected\)\)\);/);
  assert.match(page, /const chat = first \? aheadChat\(id\) : null, both = \(p\) => \(chat \? Promise\.all\(\[p, Promise\.race\(\[chat, new Promise\(\(r\) => setTimeout\(r, CHAT_WAIT\)\)\]\)\]\)/);
  assert.match(page, /if \(coming\) \{ const data = await both\(coming\);/);
  assert.match(view, /if \(!data && !error\) return opening/);
});

test("a failed read ahead holds nothing, so the view reads it itself", async () => {
  forgetTasks();
  await prefetchTask({ get: async () => { throw new Error("down"); } }, 5);
  assert.equal(heldTask(5), null);
});

test("the view draws from the held read, and the reads ahead are where the next view is already known", () => {
  const page = src("TaskPage.jsx"), view = src("AssistantView.jsx"), search = src("SearchEverything.jsx");
  assert.match(page, /const \[detail, setDetail\] = useState\(\(\) => \(aheadChat\(selected\) \? null : heldTask\(selected\)\)\);/);
  assert.match(page, /setDetail\(data\); keepTask\(id, data, undefined, asked\);/);
  assert.match(view, /useEffect\(\(\) => \{ if \(nextTid\) prefetchTask\(api, nextTid\); \}, \[nextTid, displayRevision\(pile\)\]\);/);   // the row Next brings
  assert.match(view, /onPointerEnter=\{\(\) => \{ if \(!isCur && i\.tid\) prefetchTask\(api, i\.tid\); \}\}/);        // a rail row under the pointer
  assert.match(search, /if \(aheadTid\) prefetchTask\(api, aheadTid\);/);                                             // a search hit highlighted
  // an act makes the held reads old - but Next is no act, it is what they are for
  assert.match(view, /onPressed\(\(id\) => \{ if \(!walkMove\(id\)\) forgetTasks\(actedTid\.current \?\? null\); \}\)/);
  assert.match(view, /useEffect\(\(\) => \{ if \(currentItem\?\.tid\) actedTid\.current = currentItem\.tid; \}, \[currentItem\]\);/,
    "an act lets go of its own task's read only - not the next item's");
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

// A ROW CLICKED COLD IS DRAWN AT THE CLICK (owner-approved, 2026-10-20): the old view and its ring stayed up for the whole read
test("a rail row clicked before its task is read puts its frame up at the click, titled, over the view's loading state", () => {
  const view = src("AssistantView.jsx"), page = src("TaskPage.jsx"), item = src("CanvasItem.jsx");
  assert.match(item, /<TaskPage taskId=\{card\.tid\} title=\{card\.title \|\| ""\}/, "the frame knows which item it is");
  assert.match(page, /data-tq-task-loading=[\s\S]{0,800}canvas && !!title && <Typography data-tq-task-loading-title=""/, "...and says it while it reads");
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
  assert.deepEqual(pageRead(7), { at: 1100, state: "approve", live: false, rec: null });
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
  assert.match(page, /page: rail\?\.tid \? pageRead\(rail\.tid\) : null,\n/, "the header pill takes the same read");
});

// THE RECORDED RESTART (2026-11-11): one poll failed while the app restarted and the red line stood over a task that loaded fine ever after
test("a task read that works takes back the line a failed one left", () => {
  const page = src("TaskPage.jsx").replace(/\r\n/g, "\n"), read = page.slice(page.indexOf("detailReads.current ||= coalesce("), page.indexOf("const loadDetail = useCallback("));
  assert.match(read, /setDetail\(data\); keepTask\(id, data, undefined, asked\);[\s\S]*?if \(loadFailed\.current\) \{ loadFailed\.current = false; setErr\(""\); \}/, "cleared by the next read that works");
  assert.match(read, /loadFailed\.current = true; setErr\(e\?\.response\?\.data\?\.detail \|\| "Failed to load task"\);/, "...and only the line this read wrote: another error is not its to clear");
});
