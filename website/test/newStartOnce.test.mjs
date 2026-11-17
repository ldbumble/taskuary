import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

// A REFUSED START FILES ONE TASK (the UI audit, 2026-10-21): New > Give an agent a job made the task, then asked for the start; a
// refused start said "nothing started" while a task stood filed, and every retry filed another copy
const src = readFileSync(new URL("../src/NewSheet.jsx", import.meta.url), "utf8");
const agent = src.slice(src.indexOf('} else if (kind === "agent") {'), src.indexOf('} else if (kind === "goal") {'));

test("the same words pressed again start the task already filed, never a second one", () => {
  assert.match(agent, /const again = filed\.current\?\.about === about && filed\.current\.how === how \? filed\.current : null;/);
  assert.match(agent, /const data = again \|\| \(await api\.post\("\/api\/tasks"/);
  assert.match(agent, /if \(!again\) \{\s+filed\.current = \{ \.\.\.data, about, how \};/);
  assert.ok(agent.indexOf("filed.current = null;") > agent.indexOf("/dispatch"), "forgotten only once a start went through");
});

test("a refused start names the task it filed", () => {
  assert.match(agent, /\$\{data\.ref\} is filed but did not start - /);
  assert.equal((agent.match(/\/dispatch`/g) || []).length, 1, "one start, for both kinds of agent");
});

// A TASK A PRESS MADE OPENS WHOLE, ONE ROAD FOR EVERY PRESS (the walk of a new task, 2026-11-17: Enter on a report's Send to agent snapped the
// report back, then a title alone, an empty head, the task before it, a mail-icon stub row): the view on screen stays as it is - his words where
// he typed them - until the new task's head and its chat are both read, then the task is drawn in one move. Here the chat's read is held back:
// no frame before it lands may show the new task, and every frame shows either his words or the task with its chat in hand
test("the view stays until the made task's head and chat are both read, then swaps once; a slow chat never draws an empty one", async () => {
  const { forgetTasks, heldConversation, heldTask, readWhole } = await import("../src/taskDetail.js");
  forgetTasks();
  let landChat;
  const chatIn = new Promise((r) => { landChat = r; });
  const list = { rev: "r1", items: [{ id: "l1", kind: "line", text: "What does this say about March?" }], pending: [], working: true };
  const api = { get: async (url) => (url.endsWith("/conversation") ? (await chatIn, { data: list }) : url.endsWith("/assistant") ? { data: { messages: [] } }
    : url === "/api/terminals" ? { data: [] } : { data: { task: { TaskId: 31, Title: "What does this say about March?" } } }) };
  let table = "report:7", whole = false;
  const frame = () => (table === "report:7" ? { id: table, his: "What does this say about March?" } : { id: table, chat: heldConversation(31)?.items || [] });
  const open = readWhole(api, 31).then(() => { whole = true; table = "task:31"; });
  const frames = [];
  for (let i = 0; i < 5; i += 1) { await new Promise((r) => setTimeout(r, 5)); frames.push(frame()); }
  assert.ok(heldTask(31), "the head is in by now");
  assert.equal(whole, false, "...but the chat is not, so the task is not drawn");
  landChat(); await open; frames.push(frame());
  assert.ok(frames.slice(0, -1).every((f) => f.id === "report:7" && f.his), "his words stand in every frame before the swap");
  assert.deepEqual(frames.at(-1), { id: "task:31", chat: list.items }, "the task is drawn with its chat, never an empty one");
  forgetTasks();
});

test("a read that never lands holds the view no longer than its wait: the press still opens the task", async () => {
  const { forgetTasks, readWhole } = await import("../src/taskDetail.js");
  forgetTasks();
  const api = { get: () => new Promise(() => {}) };
  const t = Date.now(); await readWhole(api, 32, 40);
  assert.ok(Date.now() - t < 1000);
  forgetTasks();
});

test("every press that opens a task goes the one road: held for the read, then pulled with its row; nothing clears the table first", () => {
  const view = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
  const item = readFileSync(new URL("../src/ItemSections.jsx", import.meta.url), "utf8");
  const open = view.slice(view.indexOf("const openTaskCard = "), view.indexOf("browseRef.current = browse; openTaskRef.current = openTaskCard;"));
  assert.match(open, /readWhole\(api, req\.tid\)\.then\(/, "the open waits for the task's head and chat");
  assert.ok(open.indexOf("readWhole(") < open.indexOf("pull("), "...before anything is pulled onto the table");
  assert.match(open, /madeRow\(/, "...and draws its row from what was read, as the rail would");
  // ...a hand-off's start (the report's Send to agent, an email's Hand off) leaves the item on the table until the task replaces it
  assert.doesNotMatch(view, /clearTable\(\); loadPile\(\); openTaskCard/);
  assert.match(view, /if \(step === "watch"\) \{ loadPile\(\); opened = openTaskCard\(\{ tid: out\.tid \}\); \}/);
  assert.match(view, /const r = await runProposal\(\{ \.\.\.data, key: data\.key \|\| item\.key \}\);\s+return r\?\.opened;/, "the box's Send waits for the swap");
  // ...and the box keeps his words and its spinner until then: cleared only after the start, which now returns once the task is up
  assert.match(item, /await hand\.start\(\{ verb: hand\.verb, text: q, files: pics\.paths, items: hand\.items \}\); setText\(""\); pics\.clear\(\); onHand\?\.\(null\); return;/);
  assert.doesNotMatch(view, /holdsNew/, "New's own hold is this road now");
});

test("the row a made task draws at the press carries its kind, its agent at work and its age, so the rail draws it right first time", async () => {
  const { madeRow } = await import("../src/funnelPile.js");
  const r = madeRow(12, "Compare three caterers", { working: true, at: "2026-11-17 09:30:00" });
  assert.equal(r.kind, "agent"); assert.equal(r.lane, "working"); assert.equal(r.since, "2026-11-17 09:30:00"); assert.equal(r.key, "task:12");
  const plain = madeRow(13, "Draft to a vendor");
  assert.equal(plain.kind, "task"); assert.equal(plain.lane, undefined); assert.ok(plain.since, "an age from the press");
});
