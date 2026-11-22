// Section 1 of the task view (the redesign, 2026-10-16): the header's read-only "Triage decided" pills and "Came from",
// the task's messages as conversations, newest first - the latest two, what is between counted, and the first message.
import test from "node:test";
import assert from "node:assert/strict";



let id = 0;


test("a to-do says the message that asked for it, only where there is more than one message", async () => {
  const { todoSources } = await import("../src/taskSources.js");
  const groups = [{ msgs: [{ MessageId: 2, who: "Erin Blake", SentAt: "2026-10-15 09:00:00" }, { MessageId: 1, who: "Ray Colton", SentAt: "2026-10-01 09:00:00" }] }];
  const items = [{ id: "a", text: "Send the metadata URL", src: 1 }, { id: "b", text: "Whitelist the QA addresses", src: 2 }, { id: "c", text: "by hand" }];
  const by = todoSources(items, groups);
  assert.equal(by.get("a").who, "Ray Colton");
  assert.equal(by.get("b").who, "Erin Blake");
  assert.equal(by.has("c"), false, "no source, no line");
  assert.equal(todoSources(items, [{ msgs: [groups[0].msgs[0]] }]).size, 0, "one message needs no 'from' on every row");
});
