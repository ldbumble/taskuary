import { test } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { LANES, LANE_META, attentionBand, levelOf, arrivals, chipsOf, lastSaidIndex, lastActIndex, cardFor, currentItemFromPile, currentPresentationChanged, departures, displayRevision, drawOrder, followsItem, keysOf, laneMeta, refreshCurrentPresentation, refreshPilePresentation, rowMeta, statusLine } from "../src/funnelPile.js";
import * as tw from "../src/timeWords.js";
import * as pile from "../src/funnelPile.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
const cardsSrc = () => read("assistantCards.jsx");

test('Current follows only an explicit canonical migration or lineage alias', () => {
  const prior = { key: 'review:8', tid: 3 };
  const fresh = { key: 'processing:root', processing_id: 'root', aliases: ['review:8'], tid: 3, lane: 'approve' };
  assert.equal(followsItem(prior, fresh), true);
  assert.equal(currentItemFromPile(prior, { items: [], current: fresh }), fresh);
  assert.equal(followsItem({ ...prior, key: 'review:9' }, fresh), false);
});

test("every lane the server knows has a word, a mark and a role the theme can colour", () => {
  // `stopped` is inserted, never a reorder: lane_index IS the rail's sort order (funnel._order).
  // `theirs` follows `yours`: your task, waiting on somebody else (2026-09-25)
  assert.deepStrictEqual(LANES, ["blocked", "time", "approve", "asked", "yours", "theirs", "queued", "stopped", "saved", "broken", "unjudged", "forgotten", "report", "fyi", "working"]);
  // the owner's OWN work is a lane, not a kind override: a kind beats its lane (rowMeta), which is
  // right when the kind says more and wrong here - "on you" would have beaten "waiting to start" on
  // every queued row, because both carry kind 'todo' (the owner, 2026-09-16: "shouldn't this show
  // an emoji as well? queued or something").
  assert.strictEqual(LANE_META.yours.word, "on you");
  // an agent that ran and LEFT is neither waiting to start nor waving - it has its own word, taken
  // from taskLifecycle.agentPhase, which has named this correctly for the Tasks tab all along
  assert.strictEqual(LANE_META.stopped.word, "agent stopped");
  // ...and a row NOTHING judged is not an fyi: `fyi` claims a verdict was reached, and the whole
  // point of the error state is that none was (the owner, 2026-09-15: "that's a bad bug")
  assert.strictEqual(LANE_META.unjudged.word, "couldn't sort this");
  assert.strictEqual(LANE_META.unjudged.role, "bad");
  // a failed check is second only to an agent that is stuck, wears the oxblood `bad` role, and
  // is NOT in the server's MUTED_LANES - a rule that quiets a chatty report cannot quiet it failing
  assert.strictEqual(LANE_META.broken.role, "bad");
  for (const l of LANES) { assert.ok(LANE_META[l].word); assert.ok(LANE_META[l].mark); assert.ok("role" in LANE_META[l]); }
  // oxblood is spent on nothing but "this is on you": an agent waiting, a draft waiting for a yes
  assert.deepStrictEqual(LANES.filter((l) => LANE_META[l].role === "you"), ["blocked", "approve"]);
  assert.strictEqual(laneMeta("nonsense"), LANE_META.fyi);
});

test("the rail draws the server's next-first list as it comes: what comes out next is on top", () => {
  const items = [{ key: "a" }, { key: "b" }, { key: "c" }];
  assert.deepStrictEqual(drawOrder(items).map((i) => i.key), ["a", "b", "c"]);
  assert.notStrictEqual(drawOrder(items), items);   // a copy: the caller splices the current one out
  assert.deepStrictEqual(drawOrder(null), []);
});

test("an arrival is a key we have not drawn before - and the first paint is never an arrival", () => {
  const first = [{ key: "a" }, { key: "b" }];
  assert.deepStrictEqual([...arrivals(null, first)], []);
  const prev = keysOf(first);
  assert.deepStrictEqual([...arrivals(prev, [{ key: "b" }, { key: "z" }])], ["z"]);
  assert.deepStrictEqual([...arrivals(prev, first)], []);
  // ...and a departure is a key that was drawn and is gone - it falls out of the mouth
  assert.deepStrictEqual(departures(first, [{ key: "b" }]).map((i) => i.key), ["a"]);
  assert.deepStrictEqual(departures(null, first), []);
});

test("the card under a line is decided by kind, one card per kind", () => {
  assert.strictEqual(cardFor({ kind: "review" }), "reply");
  assert.strictEqual(cardFor({ kind: "action" }), "reply");
  assert.strictEqual(cardFor({ kind: "agent" }), "agent");
  assert.strictEqual(cardFor({ kind: "meeting" }), "meeting");
  assert.strictEqual(cardFor({ kind: "report" }), "report");
  assert.strictEqual(cardFor({ kind: "agentdone" }), "agentdone");
  assert.strictEqual(cardFor({ kind: "idea" }), "idea");
  assert.strictEqual(cardFor({ kind: "asked" }), "message");
  assert.strictEqual(cardFor({ kind: "fyi" }), "message");
  assert.strictEqual(cardFor({ kind: "triaging" }), null);
  assert.strictEqual(cardFor({ kind: "brief" }), "brief");
  assert.strictEqual(cardFor({ kind: "task" }), "task");
  assert.strictEqual(cardFor({ kind: "fyis" }), "fyis");
  assert.strictEqual(cardFor({ kind: "wrapup" }), "wrapup");
  assert.strictEqual(cardFor({ kind: "todo", lane: "working", tid: 358 }), "agent");
  assert.strictEqual(cardFor(null), null);
});

test("a dispatched message follows its task into the live agent row", () => {
  const card = { key: "msg:44", tid: 358, kind: "todo", lane: "asked" };
  const working = { key: "agent:358", tid: 358, kind: "todo", lane: "working", agent: "coding", sid: "abc" };
  assert.equal(currentItemFromPile(card, { current: null, items: [working] }), working);
  assert.equal(followsItem(card, working), true);
  assert.equal(cardFor(working), "agent");
  assert.equal(followsItem(card, { key: "agent:999", tid: 999, lane: "working" }), false);
});

test("full display revisions replace completed pile responses and retain identical ones", () => {
  const old = { rev: "legacy-same", display_revision: "display-1", items: [{ key: "a", preview: "old" }] };
  const edited = { rev: "legacy-same", display_revision: "display-2", items: [{ key: "a", preview: "new" }] };
  assert.equal(displayRevision(old), "display-1");
  assert.equal(displayRevision({ rev: "legacy-only" }), "legacy-only");
  assert.equal(refreshPilePresentation(old, { ...old }), old);
  assert.equal(refreshPilePresentation(old, edited), edited);
  assert.deepEqual(refreshPilePresentation(null, { items: [] }), { items: [] });
});

test("a changed Current presentation is a complete replacement so removed fields stay removed", () => {
  const old = { key: "msg:44", lane: "approve", presentation_revision: "p1",
    preview: "old excerpt", draft: true, tail: ["old question"], more: 3 };
  const fresh = { key: "msg:44", lane: "asked", presentation_revision: "p2", title: "Fresh title" };
  const fromPile = currentItemFromPile(old, { current: fresh, items: [] });
  const replaced = refreshCurrentPresentation(old, fromPile);
  assert.equal(currentPresentationChanged(old, fresh), true);
  assert.equal(replaced, fresh);
  assert.deepEqual(replaced, fresh);
  assert.equal("preview" in replaced, false);
  assert.equal("draft" in replaced, false);
  assert.equal("tail" in replaced, false);
  assert.equal("more" in replaced, false);
  assert.equal(refreshCurrentPresentation(fresh, { ...fresh }), fresh);
});

test("an explicitly missing scoped Current cannot resurrect from a stale queue row", () => {
  const current = { key: "msg:44", tid: 7, presentation_revision: "p1" };
  assert.equal(currentItemFromPile(current, { current: null, items: [{ ...current, presentation_revision: "p2" }] }), null);
  assert.equal(currentItemFromPile(current, { items: [{ ...current, presentation_revision: "p2" }] }).presentation_revision, "p2");
  const working = { key: "agent:7", tid: 7, lane: "working", presentation_revision: "worker-p1" };
  assert.equal(currentItemFromPile(current, { current: null, items: [working] }), working);
  assert.equal(currentItemFromPile(current, { current: null, items: [{ ...working, tid: 8 }] }), null);
  assert.equal(currentItemFromPile(current, { current: null, items: [{ ...working, lane: "blocked" }] }), null);
});

test("ages read as a person says them", () => {
  const now = new Date("2026-09-03T12:00:00").getTime();
  assert.strictEqual(tw.age("2026-09-03 12:12:00", now), "in 12m");
  assert.strictEqual(tw.age("2026-09-03 14:30:00", now), "in 2h");
  assert.strictEqual(tw.age("2026-09-03 11:59:30", now), "now");
  assert.strictEqual(tw.age("2026-09-03 11:20:00", now), "40m");
  assert.strictEqual(tw.age("2026-09-03 08:00:00", now), "4h");
  assert.strictEqual(tw.age("2026-08-30 08:00:00", now), "4d");
  assert.strictEqual(tw.age("", now), "");
  assert.strictEqual(tw.age("garbage", now), "");
});

test("the header line counts the pipe and what is on you", () => {
  assert.strictEqual(statusLine([], false), "All caught up");
  assert.strictEqual(statusLine([{ lane: "fyi" }, { lane: "approve" }, { lane: "blocked" }], false), "3 in the pipe · 2 on you");
  assert.strictEqual(statusLine([{ lane: "fyi" }], false), "1 in the pipe");
  assert.strictEqual(statusLine([{ lane: "fyi" }], true), "thinking…");
});


test("a few kinds say more than their lane does", async () => {
  const { rowMeta, laneMeta } = await import("../src/funnelPile.js");
  // an agent's finished task sits in a task lane under Tasks until read (2026-11-02); it reads "agent finished", not "on you"
  assert.equal(rowMeta({ kind: "agentdone", lane: "yours" }).word, "agent finished");
  assert.equal(rowMeta({ kind: "agentdone", lane: "yours" }).role, "done");
  // ...and a kind never beats a lane that is MORE specific: both of these carry kind 'todo'
  assert.equal(rowMeta({ kind: "todo", lane: "yours" }).word, "on you");
  assert.equal(rowMeta({ kind: "todo", lane: "queued" }).word, "waiting to start");
  assert.equal(rowMeta({ kind: "wrapup", lane: "report" }).word, "close it?");
  assert.equal(rowMeta({ kind: "report", lane: "report" }).word, laneMeta("report").word);
  assert.equal(rowMeta({ kind: "fyi", lane: "fyi" }).word, "fyi");
  assert.equal(rowMeta(null).word, "fyi");
});

test("the action words hang on the last thing Taskuary SAID about the item, not on a passive notice", () => {
  const item = { id: "a1", role: "assistant", card: { key: "msg:1", kind: "review", chips: [{ verb: "approve", label: "Send the reply" }] } };
  const notice = { id: "a2", role: "assistant", card: { key: "agent:9", kind: "agent", background_event: true } };
  assert.equal(lastSaidIndex([{ id: "u1", role: "user" }, item]), 1);
  assert.equal(lastSaidIndex([item, notice]), 0, "a background update must not take the words off the item");
  assert.equal(lastSaidIndex([item, { id: "r1", role: "receipt" }]), 0, "a receipt is not somewhere to act");
  assert.equal(lastSaidIndex([]), -1);
  // ...but a receipt carrying its way on (Not done -> Try again, a cancel, a sweep's Next) takes the words: drawn under the
  // line above it, a failed act ended on an empty row
  const failed = { id: "r2", role: "receipt", status: "error", chips: [{ verb: "next", label: "Next" }] };
  assert.equal(lastActIndex([item, failed]), 0, "a live item card keeps its own words");
  const proposal = { id: "p1", role: "assistant", proposal: { id: 7 }, card: { kind: "proposal", key: "msg:1" } };
  assert.equal(lastActIndex([proposal, failed]), 1, "a failed proposal's receipt carries the way on");
  assert.equal(lastActIndex([{ ...item, done: true }, failed]), 1, "a folded card has nothing left to press");
  assert.equal(lastActIndex([item, { id: "r1", role: "receipt" }]), 0, "a bare receipt still is not");
  assert.equal(lastActIndex([failed, item]), 1, "a newer line takes them back");
  // ...and a Not ours taken further never rides onto the next item's row (the owner, 2026-11-10: an idea's "No more ideas like this"
  // stood on an FYI batch's bar): its way is the item's own button, so nothing in funnelPile lends a receipt's chips past it
  assert.equal(Object.keys(pile).includes("furtherIndex"), false);
  // an answer to a typed question carries them on the turn itself; a surfaced item on its card
  assert.deepEqual(chipsOf(item).map((c) => c.verb), ["approve"]);
  assert.deepEqual(chipsOf({ role: "assistant", chips: [{ verb: "next", label: "Next" }] }).map((c) => c.verb), ["next"]);
  // ...and a clarifying choice replaces them: it goes back as words, so mixing the two invites two answers
  assert.deepEqual(chipsOf({ ...item, options: ["Tuesday", "Thursday"] }), [{ ask: "Tuesday", label: "Tuesday" }, { ask: "Thursday", label: "Thursday" }]);
  assert.deepEqual(chipsOf({ role: "assistant" }), []);
});

// Four cards read `${ageText(x)} ago` and so said "now ago" on anything fresher than two minutes -
// and "in 3 min ago" when the server's stamp was a moment ahead of the browser's clock.
test("an age said as a sentence never reads 'now ago' or 'in 3 min ago'", () => {
  const now = Date.parse("2026-09-10T12:00:00Z");
  const at = (min) => new Date(now - min * 60000).toISOString();
  assert.equal(tw.ago(at(0), now), "just now");
  assert.equal(tw.ago(at(1), now), "1m ago");
  assert.equal(tw.ago(at(7), now), "7m ago");
  assert.equal(tw.ago(at(150), now), "2h ago");
  assert.equal(tw.ago(at(-3), now), "in 3m");     // a stamp in the future is not an age at all
  assert.equal(tw.ago(null, now), "");
  assert.equal(tw.ago("not a date", now), "");
});

test("the waving agent is the one lane sized to be seen", () => {
  // "can't see the hand waving. used to say agent waving?" (the owner, 2026-09-11). The mark and
  // the word were both in the table; nothing wore them, because row_lane never said `blocked`.
  const meta = LANE_META.blocked;
  assert.equal(meta.word, "agent waiting on you");          // ...the same word timelineState.waving uses
  assert.equal(meta.mark, "👋");
  assert.equal(meta.loud, true);
  // LOUD IS EXACTLY "this is on you". The two tables disagreed while they were two - the Timeline
  // shouted a ready reply and the rail did not - and unifying them had to pick one (2026-09-16).
  // Tying it to the role rather than listing keys is what stops it drifting again.
  assert.deepEqual(Object.entries(LANE_META).filter(([, m]) => m.loud).map(([k]) => k).sort(),
                   Object.entries(LANE_META).filter(([, m]) => m.role === "you").map(([k]) => k).sort());
  // still the owner's own level, not a new one
  assert.equal(attentionBand({ lane: "blocked" }), attentionBand({ lane: "approve" }));
});

// THE TASKS RAIL AND THE WORK RAIL SAY THE SAME THING. The rail used to paint everything that was
// not done, dropped or busy with one red "needs you" chip, so an agent parked on a question and a
// reply waiting for your yes were indistinguishable (the owner, 2026-09-22). These two words must
// never collapse into one again, and they are the vocabulary's, not this rail's.
test("a waving agent and a waiting reply are two different words", () => {
  assert.equal(rowMeta({ lane: "blocked" }).word, "agent waiting on you");
  assert.equal(rowMeta({ lane: "approve" }).word, "ready to send");
  assert.notEqual(rowMeta({ lane: "blocked" }).word, rowMeta({ lane: "approve" }).word);
});

test("every lane the Tasks rail can land on has a word and a role", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile(new URL("../src/ui.jsx", import.meta.url), "utf8");
  const body = source.slice(source.indexOf("const taskLane ="), source.indexOf("const laneState ="));
  const lanes = [...new Set([...body.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]))].filter((l) => LANES.includes(l));
  assert.ok(lanes.length >= 5, "taskLane must still be reading lanes by name");
  for (const lane of lanes) {
    assert.ok(rowMeta({ lane }).word, `lane ${lane} has no word in lanes.json`);
    assert.ok("role" in rowMeta({ lane }), `lane ${lane} has no role, so the chip has no colour`);
  }
});

test('timeWords.band: empty or unreadable is blank, the past buckets into < 5m / < 15m / < 30m / < 1h / Nh / Nd', () => {
  const now = new Date('2026-09-28T12:00:00').getTime();
  const ago = (min) => new Date(now - min * 60000).toISOString();
  assert.strictEqual(tw.band('', now), '');
  assert.strictEqual(tw.band(null, now), '');
  assert.strictEqual(tw.band('not a date', now), '');
  assert.strictEqual(tw.band(ago(0), now), '< 5m');
  assert.strictEqual(tw.band(ago(29), now), '< 30m');
  assert.strictEqual(tw.band(ago(30), now), '< 1h');
  assert.strictEqual(tw.band(ago(59), now), '< 1h');
  assert.strictEqual(tw.band(ago(60), now), '1h');
  assert.strictEqual(tw.band(ago(1439), now), '23h');
  assert.strictEqual(tw.band(ago(1440), now), '1d');
  assert.strictEqual(tw.band(ago(3 * 1440 + 600), now), '3d');
});

test('timeWords.band: the future reads "in ..." and a server stamp with a space parses as local time', () => {
  const now = new Date('2026-09-28T12:00:00').getTime();
  const ahead = (min) => new Date(now + min * 60000).toISOString();
  assert.strictEqual(tw.band(ahead(5), now), 'in 5m');
  assert.strictEqual(tw.band(ahead(59), now), 'in 59m');
  assert.strictEqual(tw.band(ahead(60), now), 'in 1h');
  assert.strictEqual(tw.band(ahead(1439), now), 'in 23h');
  assert.strictEqual(tw.band(ahead(1440), now), 'in 1d');
  assert.strictEqual(tw.band('2026-09-28 10:00:00', now), '2h');
});

test('a task pulled onto the table from outside the pile sits under On you, not where its last message would', async () => {
  const { pulledRow } = await import("../src/funnelPile.js");
  // an open task looked up from search: its card speaks through a GitHub notification, so the server calls it fyi
  const card = { key: 'processing:p1', kind: 'fyi', lane: 'fyi', order_band: 4, tid: 46 };
  assert.equal(levelOf(pulledRow(card)), 'task');
  // ...but a CLOSED one is only shown, never a row under Tasks (the owner, 2026-11-08: Tasks went 20 -> 21 on opening a done task)
  assert.equal(pulledRow({ ...card, closed: true }), null);
  // ...a message with no task behind it stays where its own lane puts it
  assert.equal(levelOf(pulledRow({ key: 'msg:9', kind: 'fyi', lane: 'fyi', order_band: 4 })), 'fyi');
});

test('an agent on the table keeps its own lane on the rail when the walk has taken its row out of the pile (G7)', async () => {
  const { pulledRow } = await import("../src/funnelPile.js");
  // it asked while it stood there: the rail said "on you" under a header saying the agent waited on you
  assert.equal(pulledRow({ key: 'processing:p2', kind: 'agent', lane: 'blocked', order_band: 2, tid: 37 }).lane, 'blocked');
  assert.equal(pulledRow({ key: 'processing:p2', kind: 'agent', lane: 'working', order_band: 2, tid: 37 }).lane, 'working');
  // ...a task's own card is still on you while it is open
  assert.equal(pulledRow({ key: 'processing:p3', kind: 'todo', lane: 'queued', order_band: 2, tid: 38 }).lane, 'yours');
});
