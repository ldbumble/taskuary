import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
// the "Session closed - here is what it did" card, from its heading to the end of its box
const card = () => {
  const page = read("TaskPage.jsx"), at = page.indexOf("Session closed — here is what it did");
  return page.slice(at, page.indexOf(") : workspaceMode ===", at));
};

// The wrap's own reply carried the report without the agent's last message, so the card showed the one-line summary
// while the write-up on the task held what the agent actually said (2026-10-11).
test("the closed-session card shows the write-up as filed, not the wrap's summary", () => {
  assert.match(card(), /<CoderReport body=\{filedReport \|\| wrapped\.report\}/);
  assert.match(card(), /artifacts=\{detail\?\.artifacts/, "and what the session saved");
});

// With Close out already open under the card, "Read the draft" opened what was open and did nothing.
test("Read the draft is offered only while the draft is out of sight", () => {
  const c = card();
  assert.match(c.slice(0, c.indexOf("Read the draft")), /wrapped\.drafting && stage !== "reply" &&/);
});
