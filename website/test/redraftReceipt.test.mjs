// A REWRITE THAT DID NOT HAPPEN IS DRAWN AS A FAILURE (2026-10-26): when the drafting AI failed, the page's receipt read
// "✓ I could not rewrite it here" - a receipt with no status wears the tick (AssistantView's receipt: ✗ only for a status
// other than done). The failed redraft carries status "failed", so it draws ✗.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const view = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");

test("a redraft that came back with no draft is a failed receipt, and a status-less receipt is the only one that ticks", () => {
  const at = view.indexOf('if (verb === "redraft" && cur?.rid && mid)');
  const block = view.slice(at, view.indexOf("return;", view.indexOf("I could not rewrite it here", at)));
  assert.match(block, /\.\.\.\(data\.draft \? \{\} : \{ status: "failed" \}\)/);
  assert.match(view, /m\.status && m\.status !== "done" \? "✗ " : "✓ "/);
});
