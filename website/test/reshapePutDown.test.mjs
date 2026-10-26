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
  assert.ok(go.indexOf("onLeave?.(src)") > -1 && go.indexOf("onLeave?.(src)") < go.indexOf('runOperation(api, "task.merge"'), "put down at the press");
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

// ANY TASK, OPEN OR CLOSED (the owner, 2026-10-26: "we can't merge this with other tasks only open tasks?"): what is typed asks the
// server (?q=, a number or title words), a closed candidate says so, and folding into one says before the press that it reopens
test("the fold picker searches the server, marks a closed task, and says a closed survivor is reopened", () => {
  const fold = part(read("Reshape.jsx"), "const FoldIntoAnother", "\n};");
  assert.match(fold, /merge-candidates`, \{ params: \{ q \} \}/, "typing searches every task server-side");
  assert.match(fold, /options=\{found \?\? cands\}[^\n]*\n[^\n]*filterOptions=\{\(x\) => x\}/, "the server's answer is shown as it came");
  assert.match(fold, /o\.closed && <span[^>]*> · closed<\/span>/);
  assert.match(fold, /pick\.closed \? `, and \$\{pick\.ref\} is reopened`/, "said on the survivor chip before the press");
  assert.match(fold, /done\.reopened \? `, and \$\{done\.ref\} is reopened`/, "and on the confirmation line");
});
