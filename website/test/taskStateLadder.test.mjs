// One verdict per task on the rail. The run row says `running` for as long as the pty is up -
// including while the CLI waits at its prompt - so reading it first put "agent working" on a row
// whose page header, Wall cell and toast all said the coder had stopped and was waiting (TQ-0004,
// 2026-09-18). A live session speaks for itself; the run row decides only when there is none.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const ui = fs.readFileSync(path.join(process.cwd(), "src", "ui.jsx"), "utf8");
const at = ui.indexOf("export const busyNow");
const src = ui.slice(at, ui.indexOf(";", at) + 1);
const isWaiting = (s) => (s?.waiting ?? (s?.idle >= 45));
const busyNow = new Function("isWaiting", src.replace("export const busyNow =", "return"))(isWaiting);

test("a live session that is waiting is not 'agent working', whatever the run row says", () => {
  assert.equal(busyNow({ RunStatus: "running", Session: { alive: true, waiting: true } }), false);
  assert.equal(busyNow({ RunStatus: "running", Session: { alive: true, waiting: false } }), true);
});
test("with no live session the run row decides", () => {
  assert.equal(busyNow({ RunStatus: "running", Session: null }), true);
  assert.equal(busyNow({ RunStatus: null, Session: { alive: false } }), false);
});
test("an older session row without a verdict falls back to the clock", () => {
  assert.equal(busyNow({ Session: { alive: true, idle: 3 } }), true);
  assert.equal(busyNow({ Session: { alive: true, idle: 120 } }), false);
});
