import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { withoutAsked } from "../src/askOnce.js";

// A general agent's question is said ONCE on its canvas - in the Agent work pane's answer box (the owner, 2026-10-21)
const asking = { request_id: "q1", text: "Keep the inter-company rows, or drop them as before?", choices: ["Keep", "Drop"] };
const say = (text) => ({ role: "assistant", content: [{ type: "text", text }] });
const count = (msgs) => msgs.flatMap((m) => m.content).filter((c) => c.type === "text")
  .reduce((n, c) => n + c.text.split(asking.text).length - 1, 0);

test("the answer above the box drops the question the box shows, and keeps the rest", () => {
  for (const tail of [asking.text, `${asking.text} (Keep / Drop)`]) {
    const msgs = [say("Earlier."), { role: "user", content: [{ type: "text", text: "go" }] }, say(`I reconciled the export.\n\n${tail}`)];
    const shown = withoutAsked(msgs, asking);
    assert.equal(count(shown), 0, "the box is the one place it is said");
    assert.equal(shown[2].content[0].text, "I reconciled the export.");
    assert.equal(shown[0], msgs[0], "earlier turns untouched");
  }
});

test("with no open question nothing changes", () => {
  const msgs = [say(`Done.\n\n${asking.text}`)];
  assert.equal(withoutAsked(msgs, null), msgs);
});

test("the canvas draws the box from the same question it took out of the answer", () => {
  const g = readFileSync(fileURLToPath(new URL("../src/GeneralWorkspace.jsx", import.meta.url)), "utf8");
  assert.match(g, /withoutAsked\(messagesWithTrace\(data\?\.messages, session, dock\),\s*!dock && data\?\.asking && data\.asking\.request_id !== answered \? data\.asking : null\)/);
});
