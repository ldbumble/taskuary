// SENDING AND CLOSING ARE TWO STEPS (the owner, 2026-10-18): the button under a draft is Send and it only sends; Approve runs only the
// agent's act; Mark done is the one close. A send leaves the item on the table, its card badged Send - Mark done and Next on the row by the prompt.
// ...save Close out's own Send and close (the owner, 2026-11-03), the one send that closes - pinned in sendAndClose.test.mjs; Send itself never does.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { hint, label } from "../src/buttons.js";


test("Send only sends and Approve only runs - each says the task stays open until Mark done", () => {
  assert.equal(label("approve"), "Send");
  assert.match(hint("approve"), /stays open until you Mark done/);
  assert.equal(label("approve", "action"), "Approve");
  assert.match(hint("approve", "action"), /^Runs only what the agent proposes/);
  assert.equal(label("close"), "Mark done");
  const all = JSON.stringify(JSON.parse(readFileSync(new URL("../../taskuary/buttons.json", import.meta.url), "utf8")).verbs);
  assert.doesNotMatch(all, /Send & close|no_close/);
});


test("the dead-end walk takes a failed send's fix by its own words: an id ending ':fix' is a named button", () => {
  const d = readFileSync(new URL("../deadend_check.mjs", import.meta.url), "utf8");
  const line = d.split("\n").find((l) => l.startsWith("const named = "));
  const further = d.split("\n").filter((l) => /^const (CHOICE_WORDS|isFurther) = /.test(l)).join("\n");
  const named = new Function("NAMED", "CHOICES", `${further}\n${line.replace("const named = ", "return ")}`)(new Set(["Send", "Next"]),
    { _: "answers", not_ours: [["not_ours", "Just this once"], ["not_ours_sender", "From now on - their mail is filed for you"]] });
  // ...a receipt's further button lent to the next row is named by its own verb's answer (4cb3e165), and only by that
  assert.equal(named("From now on - their mail is filed for you", "chat:5d:not_ours_sender"), true);
  assert.equal(named("From now on - their mail is filed for you", "chat:5d:not_ours"), false);
  assert.equal(named("From now on - their mail is filed for you", "12:not_ours_sender"), false);
  assert.equal(named("Something new", "chat:5d:not_ours_sender"), false);
  assert.equal(named("Connect a mailbox", "12:fix"), true);
  assert.equal(named("Connect a mailbox", "12:approve"), false);
  assert.equal(named("Connect a coding tool", "chat:go"), true);
  assert.equal(named("Connect a coding tool", "chat:3:go"), true);
  assert.equal(named("Send", ""), true);
  assert.match(d, /id: b\.getAttribute\("data-tq-verb"\) \|\| ""/);
  assert.match(d, /s\.verbs\.filter\(\(v\) => !named\(v\.word, v\.id\)\)/);
});
