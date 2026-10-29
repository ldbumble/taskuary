// ONE READ IN FLIGHT PER KEY (2026-10-23): behind a stalled server one task page held twenty GET /api/tasks/<id> open at once.
// A call while a read runs shares the one re-read after it; leaving a task aborts its read. And the Send press lets go when the
// decide answers, with a timeout after which the card reads its own delivery state.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { coalesce } from "../src/coalesce.js";
import { DECIDE_TIMEOUT, timedOut } from "../src/sendState.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const gate = () => { let open; const p = new Promise((r) => { open = r; }); return { p, open }; };

test("one read in flight per key: calls meanwhile share ONE re-read, with the newest arguments", async () => {
  const calls = [], gates = [];
  const c = coalesce(async (id, n, signal) => { calls.push([id, n]); const g = gate(); gates.push(g); await g.p; return `${id}:${n}`; });
  const a = c.run(7, 7, 1);
  await Promise.resolve();
  const b = c.run(7, 7, 2), d = c.run(7, 7, 3);
  assert.equal(b, d, "the calls behind a running read share one promise");
  await new Promise((r) => setTimeout(r));
  assert.deepEqual(calls, [[7, 1]], "nothing more goes out while the first read runs");
  gates[0].open();
  assert.equal(await a, "7:1");
  await new Promise((r) => setTimeout(r));
  assert.deepEqual(calls, [[7, 1], [7, 3]], "one re-read after it lands, carrying the newest call");
  gates[1].open();
  assert.equal(await b, "7:3");
  assert.equal(c.busy(7), false);
  c.run(7, 7, 4); await new Promise((r) => setTimeout(r));
  assert.equal(calls.length, 3, "a call after everything landed reads at once");
  gates[2].open();
});

test("other keys read side by side, and a failed read still lets the dirty re-read go", async () => {
  let n = 0;
  const c = coalesce(async (id) => { n += 1; if (id === "x" && n === 1) throw new Error("stalled"); return id; });
  const x = c.run("x", "x"), y = c.run("y", "y"), again = c.run("x", "x");
  await assert.rejects(x, /stalled/);
  assert.equal(await y, "y");
  assert.equal(await again, "x");
  assert.equal(n, 3);
});

test("moving to another task aborts the read of the last one, and its queued re-read never goes", async () => {
  const signals = [], ids = [];
  const c = coalesce((id, signal) => { ids.push(id); signals.push(signal);
    const no = () => Object.assign(new Error("canceled"), { code: "ERR_CANCELED" });
    return new Promise((res, rej) => signal.aborted ? rej(no()) : signal.addEventListener("abort", () => rej(no()))); });
  const old = c.run(1, 1); const queued = c.run(1, 1);
  c.run(2, 2);
  await Promise.resolve();
  c.drop(2);
  assert.equal(signals[0].aborted, true);
  await assert.rejects(old, /canceled/);
  assert.equal(await queued, undefined);
  assert.equal(signals.length, 2, "the dropped task's dirty re-read was not sent");
  assert.equal(signals[1].aborted, false, "the task now open keeps its read");
  assert.equal(c.busy(1), false);
});

test("the task page, the conversation read and the pile each hold one read in flight", () => {
  const page = read("TaskPage.jsx"), view = read("AssistantView.jsx");
  assert.match(page, /detailReads\.current \|\|= coalesce\(async \(id, signal\) =>/);
  assert.match(page, /api\.get\(`\/api\/tasks\/\$\{id\}`, \{ signal \}\)/);
  assert.match(page, /return detailReads\.current\.run\(id, id\);/);
  assert.match(page, /useEffect\(\(\) => \{ detailReads\.current\.drop\(selected \|\| null\); \}, \[selected\]\);/);
  assert.equal((page.match(/api\.get\(`\/api\/tasks\/\$\{id\}`/g) || []).length, 1, "every task read goes through the one coalesced reader");
  assert.match(view, /chatReads\.current \|\|= coalesce\(\(epoch\) => readChatRef\.current\(epoch\)\);/);
  assert.match(view, /const readChat = useCallback\(\(epoch = chatEpoch\.current\) => chatReads\.current\.run\(epoch, epoch\), \[\]\);/);
  assert.match(view, /if \(pileFlight\.current\) \{\n\s+if \(force\) pileForcePending\.current = true;\n\s+return pileFlight\.current;/, "the pile was coalesced already (pileFlight)");
});

test("a Send lets go when the decide answers, and after a minute with no answer reads the delivery state instead", () => {
  assert.equal(DECIDE_TIMEOUT, 60000);
  assert.equal(timedOut({ code: "ECONNABORTED" }), true);
  assert.equal(timedOut({ code: "ERR_CANCELED" }), false);
  assert.equal(timedOut({ response: { status: 500 } }), false);
  const card = read("ReviewDecision.jsx");
  assert.equal((card.match(/\/decide`,[\s\S]{0,400}?\{ timeout: DECIDE_TIMEOUT \}\);/g) || []).length, 2, "both decide calls carry the timeout");
  assert.doesNotMatch(card, /await onSent\(\); setBusy\(false\)/, "busy never waits on the re-read after the send");
  assert.equal((card.match(/setBusy\(false\); await onSent\(\{ closes: [^\n]+\}\); return;/g) || []).length, 2);
  assert.equal((card.match(/if \(timedOut\(e\)\) onChanged\?\.\(\);/g) || []).length, 2, "a timeout reads the review again, no line of its own");
});
