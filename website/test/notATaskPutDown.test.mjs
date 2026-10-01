// NOT A TASK FLICKERED (press audit B16, 2026-10-01): the row went ON YOU -> For later -> gone -> FYI -> gone. Its mail
// becoming an FYI is right (the owner); the steps between were not. The task view cleared the table only after the
// delete returned, so for that time the rail drew the task as an open one already seen - under For later - until the
// server's pile let it go. It is put down AT THE PRESS now, as Mark done is (ac051beb), and put back if the delete fails.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("Not a task puts the task down before the delete, and back with the reason if it fails", () => {
  const page = read("TaskPage.jsx");
  const nat = page.slice(page.indexOf("const notATask = async"), page.indexOf("// The task's own session"));
  assert.ok(nat.indexOf("onLeave?.()") > -1, "put down at the press");
  assert.ok(nat.indexOf("onLeave?.()") < nat.indexOf("/not-a-task"), "before the request");
  assert.match(nat, /catch \(e\) \{[^}]*onStay\?\.\(msg\)/, "a delete that fails puts it back");
  // the canvas's onLeave is the rail's put-down: the task's row leaves by its tid until the pile no longer carries it,
  // and the FYI its mail becomes (no tid) is drawn as soon as the pile has it
  assert.match(read("AssistantView.jsx"), /onLeave=\{\(\) => canvas\.putDown\(c\.key, c\.tid\)\}/);
});
