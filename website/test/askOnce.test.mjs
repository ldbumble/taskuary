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

// ...and a coding agent's too: its turn's words are said parts drawn from its session (chatStream.partsMessage)
test("a coding turn's words drop the question the box shows", () => {
  const turn = { role: "assistant", content: [{ type: "data", name: "agent_parts", data: { parts: [{ type: "said", text: `Read totals.py.\n\n${asking.text} (Keep / Drop)` }, { type: "work", steps: [] }] } }] };
  const [shown] = withoutAsked([turn], asking);
  assert.deepEqual(shown.content[0].data.parts, [{ type: "said", text: "Read totals.py." }, { type: "work", steps: [] }]);
});

test("the canvas draws the box from the same question it took out of the answer - both sources, one read", () => {
  const g = readFileSync(fileURLToPath(new URL("../src/GeneralWorkspace.jsx", import.meta.url)), "utf8");
  assert.match(g, /const ask = \(coding \? cc\.got : data\)\?\.asking, asking = ask && ask\.request_id !== answered \? ask : null;/);
  assert.match(g, /const shownMessages = withoutAsked\(/);
  assert.match(g, /\}\)\(\), dock \? null : asking\);/);
});
