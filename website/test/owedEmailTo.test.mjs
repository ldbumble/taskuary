// AN OWED EMAIL'S "TO" IS ITS OWN (the owner, 2026-11-02): a chat asked the owner to email somebody, the task owed that email, and the reply's
// "To <the chat's sender> in <the group>" stood under the owed address - the sender read as the To of the email. The owed email's To is its own
// address, drafted or not; a reply back to the sender keeps its own line in the chat's cards, said as the reply's ("Reply to ...").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("in the chat's cards the owed email wears its own To, and the sender's line is the reply's", () => {
  assert.match(src("SlotList.jsx"), /data-tq-slot-to=\{i\.id\}[^>]*>To</);
  const page = src("TaskPage.jsx");
  assert.match(page, /<Typography sx=\{\{ \.\.\.label, flexShrink: 0 \}\} data-tq-reply-to="">\{owesEmails \? "Reply to" : "To"\}<\/Typography>/);
});

test("a drafted owed email says its To once - on its card, with Change - never again on the slot's own line", () => {
  const slot = src("SlotList.jsx");
  assert.match(slot, /const carded = rv\?\.Status === "pending" && \(i\.out\.kind \|\| "email"\) === "email";/);
  assert.match(slot, /\{carded \? i\.out\.name && <Typography[^]*?: <>\s*<Typography sx=\{\{ \.\.\.label, flexShrink: 0 \}\} data-tq-slot-to/);
  assert.match(src("ReviewDecision.jsx"), /<ToRow to=\{replyContext\(filedDelivery\)\}/);
});
