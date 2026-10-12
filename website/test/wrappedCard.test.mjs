import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { sentElsewhere, unsentReplyReview, replyPhase } from "../src/taskLifecycle.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
// Close out, from its heading to the Context & history fold under it
const closeOut = () => {
  const page = read("TaskPage.jsx"), at = page.indexOf('<WorkflowHeading number="3" title="Close out"');
  return page.slice(at, page.indexOf("<Fold title={`Context & history", at));
};

// The card drew the NEWEST CODER REPORT, and the poll that saw the agent's own merge filed a second one whose "last
// message" was our sentence - the agent's account was there, then gone (2026-10-12). Then it was a second telling of the run
// under the step's own: the ended session is the step's record now, with the ending added to it.
test("an ended session has no card of its own - the step's record is it, with the ending added", () => {
  const page = read("TaskPage.jsx");
  assert.doesNotMatch(page, /Session closed — here is what it did|workspaceMode === "wrapped"/);
  assert.doesNotMatch(page, /reply separately if someone is waiting/, "no boilerplate paragraph under it");
  assert.equal(page.match(/<AgentRecord \{\.\.\.recordProps\} story=\{storyAt === "record"/g).length, 1, "the open step draws the record once");
  assert.match(read("AgentRecord.jsx"), /since\?\.text && [\s\S]*Since then[\s\S]*since\.text/, "the ending is a line added to it");
});

// Close out of a merged pull request was a bare "To <sender>" over nothing.
test("Close out says what ended it and what already went out, before any envelope", () => {
  const c = closeOut();
  assert.match(c, /\|\| ended \|\| sentOutside\.length\) \?/, "an ended or answered task still opens its Close out");
  assert.ok(c.indexOf("{ended && (") < c.indexOf("THE ENVELOPE"), "the ending leads");
  assert.ok(c.indexOf("{sentOutside.map(") < c.indexOf("THE ENVELOPE"), "then what was sent elsewhere");
  assert.match(c, /\(replyMessage \|\| sentReview\) && \(!ended \|\| sentReview \|\| unsentReview\) &&/, "no envelope over nothing");
});

test("what went out elsewhere is your own outgoing messages, not a send from here", () => {
  const rows = [
    { MessageId: 1, Direction: "in", BodyText: "Fixes the export." },
    { MessageId: 2, Direction: "out", Channel: "github", BodyText: "Merged as reviewed - thanks!" },
    { MessageId: "review:9", Direction: "out", ReviewSent: true, BodyText: "Sent from Close out" },
    { MessageId: 3, Direction: "out", BodyText: "  " },
  ];
  assert.deepEqual(sentElsewhere(rows).map((m) => m.MessageId), [2]);
  assert.deepEqual(sentElsewhere(), []);
});

test("a draft the close swept away stays readable, and a decided one reads not needed", () => {
  const swept = { ReviewId: 4, Kind: "draft_reply", Status: "superseded", DraftText: "Merged - thanks, Erin." };
  assert.equal(unsentReplyReview([swept]).ReviewId, 4);
  assert.equal(replyPhase([{ ...swept, Status: "no_reply" }]), "not needed");
});
