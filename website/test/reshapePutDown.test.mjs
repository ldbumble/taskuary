// SPLIT OR MERGE, AT THE PRESS (the owner, 2026-10-01). A fold puts the merged-away task down like every close - off the rail,
// the drawer gone - while the server folds it; a fold that fails brings it back with the reason. And "Break it in two" opens at
// once: the AI's suggested split fills in when it arrives, never a spinner in its place.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
const part = (src, from, to) => src.slice(src.indexOf(from), src.indexOf(to, src.indexOf(from)));

test("Fold them together puts the merged-away task down before the request, and back with the reason if it fails", () => {
  const fold = part(read("Reshape.jsx"), "const FoldIntoAnother", "if (done) return");
  const go = fold.slice(fold.indexOf("const go = async"));
  assert.ok(go.indexOf("onLeave?.(src)") > -1 && go.indexOf("onLeave?.(src)") < go.indexOf("/merge`"), "put down at the press");
  assert.match(go, /catch \(e\) \{[^}]*onStay\?\.\(src, msg\)/, "a fold that fails puts it back");
});

test("the task view's fold closes its drawer at the press and moves on as after a close", () => {
  const page = read("TaskPage.jsx");
  assert.match(page, /<Drawer anchor="right" open=\{reshape === true && !!t\}[^\n]*ModalProps=\{\{ keepMounted: !!reshape \}\}/,
    "the drawer goes at the press; the form stays mounted so a failure brings it back");
  assert.match(page, /<Reshape taskId=\{selected\}[^\n]*onLeave=\{\(tid\) => \{ if \(tid === selected\) \{ setReshape\("merging"\); onLeave\?\.\(\); \} \}\}/);
  assert.match(page, /onStay=\{\(tid, msg\) => \{ if \(tid === selected\) \{ setReshape\(true\); onStay\?\.\(msg\); \} \}\}/);
  const done = part(page, "const reshaped = (r) =>", "};");
  assert.match(done, /canvas && onFinish \? onFinish\("dropped", async \(\) => \{\}\)/, "the walk moves on - the server already dropped it");
});

test("the Timeline's fold closes its drawer at the press too", () => {
  const feed = read("FeedView.jsx");
  assert.match(feed, /<Drawer anchor="right" open=\{reshape === true && !!sel\.TaskId\}[^\n]*ModalProps=\{\{ keepMounted: !!reshape \}\}/);
  assert.match(feed, /onLeave=\{\(tid\) => tid === sel\.TaskId && setReshape\("merging"\)\} onStay=\{\(tid\) => tid === sel\.TaskId && setReshape\(true\)\}/);
});
