import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { replySource, sentElsewhere, unsentReplyReview, replyPhase } from "../src/taskLifecycle.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
// Close out, from its heading to the Earlier runs fold under it
const closeOut = () => {
  const page = read("TaskPage.jsx"), at = page.indexOf('<WorkflowHeading number="3" title="Close out"');
  return page.slice(at, page.indexOf("<Fold title={`Earlier runs", at));
};

// The card drew the NEWEST AGENT REPORT, and the poll that saw the agent's own merge filed a second one whose "last
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
  assert.ok(c.indexOf("{sentApart.map(") < c.indexOf("THE ENVELOPE"), "then what was sent elsewhere, newest first");
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
  // ...but the Sent copy of a reply approved HERE is that reply, however the provider re-spaced it (2026-10-13)
  const mine = [{ ReviewId: 9, Status: "edited", DraftText: "Yes, keep it.", FinalText: "Gail - any ideas?\n\nThanks,\nAlex" }];
  const copy = { MessageId: 7, Direction: "out", OwnText: "Gail - any ideas?\n\n\nThanks,\n\nAlex" };
  assert.deepEqual(sentElsewhere([copy, { MessageId: 8, Direction: "out", BodyText: "Something else" }], mine).map((m) => m.MessageId), [8]);
});
test("a reply answers the newest row somebody sent - never a report joined on after them (2026-10-13)", () => {
  const rows = [
    { MessageId: 1, Channel: "email", Direction: "in", Status: "routed", BodyText: "First" },
    { MessageId: 2, Channel: "email", Direction: "in", Status: "routed", BodyText: "Wrote again" },
    { MessageId: 3, Channel: "report", Direction: "in", Status: "routed", BodyText: "End of day checkup" },
  ];
  assert.equal(replySource(rows).MessageId, 2);
  assert.equal(replySource([rows[2]]).MessageId, 3);          // nobody behind any row: its newest, as before
});
test("What was sent is the text that left - the owner's edit, not the draft under it", () => {
  assert.match(closeOut(), /\{sentReview\.FinalText \|\| sentReview\.DraftText\}/);
});

test("a draft the close swept away stays readable, and a decided one reads not needed", () => {
  const swept = { ReviewId: 4, Kind: "draft_reply", Status: "superseded", DraftText: "Merged - thanks, Erin." };
  assert.equal(unsentReplyReview([swept]).ReviewId, 4);
  assert.equal(replyPhase([{ ...swept, Status: "no_reply" }]), "not needed");
});

// the owner, 2026-10-14: each sent email says WHEN, the chain reads newest first, in the thread's own drawing
test("the emails on a task read newest first, each with who and when on its first line", () => {
  const page = read("TaskPage.jsx");
  assert.match(page, /export const newestFirst = /);
  // From reads each conversation newest on top, the older ones behind "Show N older" (the redesign, owner-approved 2026-10-21 - it was
  // the first message under the latest two); Close out's thread over the draft stays newest first
  assert.match(page, /fromRows\(g, 3, showAll\)/);
  assert.match(page, /const sentApart = newestFirst\(/);
  assert.match(page, /Sent by you\{m\.SourceName \? ` · \$\{m\.SourceName\}` : ""\}\{m\.SentAt \? ` · \$\{fmtDateTime\(m\.SentAt\)\}` : ""\}/);
  assert.match(page, /What was sent\{sentReview\.DecidedAt \? ` · \$\{fmtDateTime\(sentReview\.DecidedAt\)\}` : ""\}/);
  const sort = (ms) => [...ms].sort((a, b) => String(b.SentAt || "").localeCompare(String(a.SentAt || "")));
  assert.deepEqual(sort([{ SentAt: "2026-10-06 13:26:00" }, { SentAt: "2026-10-14 12:29:30" }, { SentAt: "2026-10-13 17:10:20" }]).map((m) => m.SentAt.slice(5, 10)),
    ["10-14", "10-13", "10-06"]);
});
