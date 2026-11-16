// The pure piece of the filled button (website/src/advice.js): what the strip lights for the item on the table.
// A real function under test, not a source regex.
import test from "node:test";
import assert from "node:assert/strict";
import { stripWord } from "../src/advice.js";

// C2 (the UI audit, 2026-10-21): the strip's word and the lit button are one decision (advice.stripWord)
test("a working agent lights Next and says nothing, and no missing AI lights a Connect (the owner, 2026-11-15)", () => {
  const w = stripWord({ speaks: true, key: "task:9", lane: "working" });
  assert.deepEqual(w, { pick: { verb: "next", line: "", for: "task:9" } });
  const s = { verb: "send_close", line: "x" };
  assert.equal(stripWord({ speaks: true, shown: s, key: "k", lane: "asked" }).pick, s, "a decision lights its verb");
  assert.deepEqual(stripWord({ speaks: true, advice: { none: "nothing", for: "k" }, key: "k", lane: "asked" }).pick, { verb: "next", line: "", for: "k" }, "any none: Next, silent");
});

// WHEN THE STRIP SPEAKS (the owner, 2026-10-13: "not while waiting or walking through things"): only the decision read for the
// item on the table now, only at rest; an agent at work is Next; and the OBVIOUS move is silent - lit, said by nothing (2026-10-23)
test("the strip speaks only for the item on the table, at rest, and an agent at work is Next", async () => {
  const { adviceShown } = await import("../src/advice.js");
  const a = { verb: "continue", line: "You usually continue it.", for: "processing:7" };
  const item = { key: "processing:7", lane: "blocked" };
  assert.equal(adviceShown(a, item, false), a);
  assert.equal(adviceShown(a, { key: "processing:8", lane: "blocked" }, false), null, "the last item's line over the next one");
  assert.equal(adviceShown(a, item, true), null, "an act in flight");
  assert.deepEqual(adviceShown(a, { ...item, lane: "working" }, false), { ...a, verb: "next", line: "", state: "working" }, "an agent continued and at work");
  assert.equal(adviceShown({ ...a, for: undefined }, item, false), null, "a line nobody read for this table");
  assert.equal(adviceShown(a, null, false), null);
  assert.deepEqual(adviceShown({ ...a, line: "" }, item, false), { ...a, line: "" }, "a silent decision still lights its button");
  assert.equal(adviceShown({ ...a, verb: null }, item, false), null, "a decision that lights nothing (an agent asking) is not shown");
});

test("the page draws the gated line, starts each item with none, and drops a read the table outran", async () => {
  const fs = await import("node:fs"), path = await import("node:path");
  const src = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");
  assert.doesNotMatch(src, /<AdvisorNext/, "nothing joins the row for an Advisor (the owner, 2026-11-15)");
  // ...and a move the server runs at once (Not ours) runs at once from the Advisor's copy too - never a proposal card with Cancel
  // ...and every press runs where it is proposed (the 2026-10-25 sweep): proposeDirect runs it, so no caller runs it a second time
  assert.match(src, /try \{ return await proposeDirect\(a\.verb, key, true, a\.revision\); \}/);
  assert.match(src, /if \(c\.revision\) await pressAdvice\(\{ verb, key, revision: c\.revision \}\); else await proposeDirect\(verb, key, true, null\);/, "a stamped chip's move is not run twice");
  assert.match(src, /if \(data\.auto\) \{ await runProposal\(data\); return \{ \.\.\.data, ran: true \}; \}/, "a press draws no proposal card with Cancel while it runs");
  // ...and a press REFUSED before anything ran says why on the row or card it was made on, through the catch each caller already has:
  // no line in the Assistant's chat, no window opening (the owner, 2026-11-10: "the agents don't tell the assistant anything")
  assert.match(src, /if \(!data\.id\) throw refusedPress\(data\.say\);/);
  assert.doesNotMatch(src, /text: data\.say, options: \[\], refused: true/, "a refused press is a line in the Assistant's chat");
  const refusedPress = eval(src.match(/const refusedPress = ([^\n]+);\n/)[1]);
  assert.equal(refusedPress("Nothing to send yet.").response.data.detail, "Nothing to send yet.", "the row's line (errText, failOf) reads the server's reason");
  assert.match(src, /advised=\{stripPick \|\| setupLit\}/);
  assert.match(src, /if \(!keep\) setAdvice\(null\)/);
  // the read is for the key ON THE TABLE - the walk's item or a task opened by name - and shown only for it
  assert.match(src, /useEffect\(\(\) => \{ readAdvice\(onTable\); setChanged\(null\); \}, \[onTable, readAdvice\]\);/);
  assert.match(src, /table\.speaks && !litNow \? adviceShown\(advice, \{ key: table\.key, lane: currentItem\?\.lane \}, busy\) : null/);
  // ...and while it is out, nothing: no "Thinking..." (the owner, 2026-10-23) - the rule's button is lit at once
  assert.doesNotMatch(src, /data-tq-advice-thinking|Thinking about this one/);
  assert.doesNotMatch(src, /picks up where it left off, and comes back here/, "the continue receipt is gone");
});

