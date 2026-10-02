// HAND OFF DISAPPEARS AT THE PRESS (the owner, 2026-10-01): like every close, the task is put down when Send it is pressed -
// folded, off the rail, the "…" under it - while the forward goes out. The server SENDS first and closes the task only once
// it has (server.handoff); a send that fails brings the task back with the reason, and the form with the owner's text.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("Send it puts the task down before the request, and a failed send puts it back with the reason", () => {
  const src = read("Handoff.jsx");
  const send = src.slice(src.indexOf("const send = async"), src.indexOf("if (sent) return"));
  assert.ok(send.indexOf("onLeave?.()") > -1 && send.indexOf("onLeave?.()") < send.indexOf("call({ to, channel, text })"), "put down at the press");
  assert.match(send, /catch \(e\) \{[^}]*onStay\?\.\(msg\)/, "a send that fails puts it back");
});

test("the task view's hand-off closes the way Mark done does: the drawer goes, the walk moves on, a failure reopens it", () => {
  const page = read("TaskPage.jsx");
  assert.match(page, /<Drawer anchor="right" open=\{handoff === true && !!t\}[^\n]*ModalProps=\{\{ keepMounted: !!handoff \}\}/,
    "the form stays mounted while it sends, so a failure brings back what was typed");
  assert.match(page, /<Handoff taskId=\{selected\} onLeave=\{\(\) => \{ setHandoff\("sending"\); onLeave\?\.\(\); \}\}/);
  assert.match(page, /onStay=\{\(msg\) => \{ setHandoff\(true\); onStay\?\.\(msg\); \}\}/);
  assert.match(page, /onSent=\{handedOff\}/);
  const done = page.slice(page.indexOf("const handedOff = async"), page.indexOf("const handedOff = async") + 600);
  assert.match(done, /onFinish \? onFinish\("done", async \(\) => \{\}\)/, "the list and the walk move on as after a close - the server already closed it");
});

test("the Timeline's hand-off closes its drawer at the press and drops the panel once it is sent", () => {
  const feed = read("FeedView.jsx");
  assert.match(feed, /<Handoff taskId=\{sel\.TaskId\} onLeave=\{\(\) => setHandoff\("sending"\)\} onStay=\{\(\) => setHandoff\(true\)\}/);
  assert.match(feed, /onSent=\{\(\) => \{ setHandoff\(false\); onSkipped\?\.\(\); \}\}/);
  assert.match(feed, /<Drawer anchor="right" open=\{handoff === true && !!sel\.TaskId\}[^\n]*ModalProps=\{\{ keepMounted: !!handoff \}\}/);
});
