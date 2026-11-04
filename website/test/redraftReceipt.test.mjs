// A REWRITE THAT DID NOT HAPPEN IS DRAWN AS A FAILURE (2026-10-26): when the drafting AI failed, the page's receipt read
// "✓ I could not rewrite it here" - a receipt with no status wears the tick (AssistantView's receipt: ✗ only for a status
// other than done). The failed redraft carries status "failed", so it draws ✗.
// ...and one that came back EMPTY or UNCHANGED did not happen either (2026-11-04): "✓ Rewritten" stood over a box that stayed empty.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { rewriteReceipt } from "../src/replyDraft.js";

const view = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");

test("a redraft's receipt is rewriteReceipt's, and a status-less receipt is the only one that ticks", () => {
  const at = view.indexOf('if (verb === "redraft" && cur?.rid && mid)');
  const block = view.slice(at, view.indexOf("return;", at));
  assert.match(block, /\.\.\.rewriteReceipt\(data, there\.tid \? ref : ""\)/);
  assert.match(view, /m\.status && m\.status !== "done" \? "✗ " : "✓ "/);
});

test("Rewritten only when the draft changed into something; otherwise it did not come back, and why", () => {
  assert.deepEqual(rewriteReceipt({ draft: "Friday at ten, Gail.", changed: true }), { text: "Rewritten - read it below before you send it." });
  assert.equal(rewriteReceipt({ draft: "Friday.", changed: true }, "TQ-0042").text, "Rewritten on TQ-0042 - read it there before you send it.");
  const empty = rewriteReceipt({ draft: "", changed: false, why: "the draft came back empty" });
  assert.equal(empty.status, "failed");
  assert.match(empty.text, /didn't come back - the draft came back empty\. The draft below is as it was/);
  const same = rewriteReceipt({ draft: "Friday at ten works.", changed: false, why: "it came back the same as before" });
  assert.equal(same.status, "failed");
  assert.match(same.text, /the same as before/);
  assert.equal(rewriteReceipt({ draft: "   ", changed: true }).status, "failed");        // blanks are no rewrite
  assert.equal(rewriteReceipt({ draft: "Friday." }).status, undefined);                   // an older server: its draft decides
  assert.equal(rewriteReceipt({ draft: "" }).status, "failed");
});
