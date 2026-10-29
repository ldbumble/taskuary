// HAND OFF DISAPPEARS AT THE PRESS (the owner, 2026-10-01): like every close, the task is put down when Send it is pressed -
// folded, off the rail, the "…" under it - while the forward goes out. The server SENDS first and only then sets the task to
// waiting on them (server.handoff - forward only, 2026-10-18); a send that fails brings the task back with the reason and the text.
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

test("the task view's hand-off moves on without closing: the drawer goes, the walk moves on, a failure reopens it", () => {
  const page = read("TaskPage.jsx");
  assert.match(page, /<Drawer anchor="right" open=\{handoff === true && !!t && !handInPane\}[^\n]*ModalProps=\{\{ keepMounted: !!handoff && !handInPane \}\}/,
    "the form stays mounted while it sends, so a failure brings back what was typed");
  // ...and on a desk's canvas the same form is a card in Close out (the owner, 2026-10-29), mounted through "sending" there too
  assert.match(page, /\{handInPane && handoff && <Box data-tq-handoff-card="" sx=\{\{[^\n]*display: handoff === true \? "block" : "none"/);
  assert.match(page, /<Handoff taskId=\{selected\} onLeave=\{\(\) => \{ setHandoff\("sending"\); onLeave\?\.\(\); \}\}/);
  assert.match(page, /onStay=\{\(msg\) => \{ setHandoff\(true\); onStay\?\.\(msg\); \}\}/);
  assert.match(page, /onSent=\{handedOff\}/);
  const done = page.slice(page.indexOf("const handedOff = async"), page.indexOf("const handedOff = async") + 600);
  assert.match(done, /closedHere\("waiting"\)/, "the list and the walk move on - the task waits on them, still open");
  assert.match(page, /onFinish \? onFinish\(status, async \(\) => \{\}\)/);
});
