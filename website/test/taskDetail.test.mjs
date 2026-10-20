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
  assert.match(page, /setDetail\(data\); keepTask\(id, data\);/);
  assert.match(view, /useEffect\(\(\) => \{ if \(nextTid\) prefetchTask\(api, nextTid\); \}, \[nextTid, displayRevision\(pile\)\]\);/);   // the row Next brings
  assert.match(view, /onPointerEnter=\{\(\) => \{ if \(!isCur && i\.tid\) prefetchTask\(api, i\.tid\); \}\}/);        // a rail row under the pointer
  assert.match(search, /if \(aheadTid\) prefetchTask\(api, aheadTid\);/);                                             // a search hit highlighted
  // an act makes the held reads old - but Next is no act, it is what they are for
  assert.match(view, /onPressed\(\(id\) => \{ if \(!\/\(\^\|:\)next\$\/\.test\(String\(id \|\| ""\)\)\) forgetTasks\(\); \}\)/);
});

test("a task's session is held with it: unknown until read, null for a task no agent holds", async () => {
  const { heldTerm, keepTerms } = await import("../src/taskDetail.js");
  forgetTasks();
  assert.equal(heldTerm(3), undefined, "not read yet - the view looks for itself");
  keepTerms([{ taskId: 3, sid: "s1", alive: false }, { taskId: 3, sid: "s2", alive: true }]);
  assert.equal(heldTerm(3).sid, "s2", "the live one first, as findTerm picks");
  assert.equal(heldTerm(7), null);
  forgetTasks(7);
  assert.equal(heldTerm(3), undefined, "a write lets the session list go with the task");
});
