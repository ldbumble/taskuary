// A task that saved its progress before the server stripped the markers still drew them (2026-10-15): the box strips them as well.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dropEcho, forScreen } from "../src/agentMarkers.js";

test("the progress box shows the agent's words, never Taskuary's markers or the reply a second time", () => {
  assert.equal(forScreen("Looked it up.\n[[TASKUARY-REPLY]]\n2 + 2 is 4.\n[[/TASKUARY-REPLY]]\n[[TASKUARY-ATTACH: C:/work/sum.csv]]"), "Looked it up.");
  assert.equal(forScreen("[[TASKUARY-REPLY]]\n2 + 2 is 4.\n[[/TASKUARY-REPLY]]"), "");
  assert.equal(forScreen("plain words"), "plain words");
  // the canvas's steps say the agent's words through it (agentSteps.js: its prose, its thinking)
  const steps = readFileSync(new URL("../src/agentSteps.js", import.meta.url), "utf8");
  assert.match(steps, /const t = forScreen\(text\);/);
  assert.match(steps, /flat\(forScreen\(e\.detail\)\)/);
});

test("a progress line that only says what the answer says leaves the box; the box goes when nothing is left", () => {
  const msg = [{ type: "reasoning", text: "session started · model claude-opus-5-5\n\n3 + 3 is 6." }, { type: "text", text: "3 + 3 is 6." }];
  assert.deepEqual(dropEcho(msg), [{ type: "reasoning", text: "session started · model claude-opus-5-5" }, msg[1]]);
  assert.deepEqual(dropEcho([{ type: "reasoning", text: "3 + 3 is 6." }, { type: "text", text: "3 + 3 is 6." }]), [{ type: "text", text: "3 + 3 is 6." }]);
  const working = [{ type: "reasoning", text: "Reading the census." }];
  assert.deepEqual(dropEcho(working), working);
});

test("the done marker leaves the box, so the answer's last paragraph is seen as the echo it is (walk 2026-10-29)", () => {
  assert.equal(forScreen("Booked the room for Thursday.\n[[TASKUARY-DONE]] Booked the room."), "Booked the room for Thursday.");
  const msg = [{ type: "reasoning", text: "Checking rooms.\n\nBooked the room for Thursday.\n[[TASKUARY-DONE]] Booked the room." },
               { type: "text", text: "Booked the room for Thursday." }];
  assert.deepEqual(dropEcho(msg), [{ type: "reasoning", text: "Checking rooms." }, msg[1]]);
});
