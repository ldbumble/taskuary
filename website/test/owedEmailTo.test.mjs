// CLOSE OUT'S "TO" IS THE EMAIL'S OWN (the owner, 2026-11-02): a chat asked the owner to email somebody, the task owed that email, and
// Close out drew "To <the chat's sender> in <the group>" under the owed address - the sender read as the To of the email. The owed email's
// To is its own address, drafted or not; a reply back to the sender keeps its own line, said as the reply's ("Reply to ...").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { owedEmails } from "../src/taskLifecycle.js";
import { closeStatus } from "../src/taskLayout.js";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const owed = { id: "s1", text: "Email Paula Vance - the 2:30 meeting", out: { kind: "email", to: "paula@vendor.example", name: "Paula Vance" }, done: false };

test("the emails a task owes, each with its own address and where it stands", () => {
  assert.deepEqual(owedEmails([owed, { id: "c", text: "a plain to-do" }], []), [{ id: "s1", to: "paula@vendor.example", name: "Paula Vance", state: "to draft" }]);
  const rv = { ReviewId: 9, Kind: "slot", Status: "pending" };
  assert.equal(owedEmails([{ ...owed, rid: 9 }], [rv])[0].state, "waits for your yes");
  assert.deepEqual(owedEmails([{ ...owed, done: true }], []), [], "a sent or dropped one is owed no more");
});

test("Close out's tab leads with the email owed and its To; the reply to the sender is its own line after it", () => {
  const owes = owedEmails([owed], []);
  assert.deepEqual(closeStatus({ to: "Gail Moreno", where: "WhatsApp", owed: true, owes }).lines,
    ["Email to paula@vendor.example · to draft", "Reply to Gail Moreno in WhatsApp", "Not drafted yet"]);
  // ...a drafted one says it waits, once - not again as a count
  assert.deepEqual(closeStatus({ emails: 1, owes: owedEmails([{ ...owed, rid: 9 }], [{ ReviewId: 9, Kind: "slot", Status: "pending" }]) }).lines,
    ["Email to paula@vendor.example · waits for your yes"]);
});

test("in Close out the owed email wears its own To, and the sender's line is the reply's", () => {
  assert.match(src("SlotList.jsx"), /data-tq-slot-to=\{i\.id\}[^>]*>To</);
  const page = src("TaskPage.jsx");
  assert.match(page, /<Typography sx=\{\{ \.\.\.label, flexShrink: 0 \}\} data-tq-reply-to="">\{owesEmails \? "Reply to" : "To"\}<\/Typography>/);
  assert.match(page, /owes: owedEmails\(detail\?\.checklist, detail\?\.reviews\)/);
});
