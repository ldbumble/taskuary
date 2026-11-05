import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { isPostReview, postOf, postState } from "../src/reviewProposal.js";
import { turnFiles } from "../src/taskOutputs.js";
import { label } from "../src/buttons.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
const rv = (p, extra = {}) => ({ ReviewId: 7, Kind: "action", Status: "pending", DraftText: JSON.stringify(p), ...extra });
const POST = { action: "run_tool", type: "linkedin_post", connector_id: 3, text: "Gas rose 4 cents.", image: "gas.png" };

// A POST IS DRAWN AS THE POST (the owner, 2026-11-05): a run_tool on a posting connector, read as one, its press named for the network
test("a linkedin_post proposal is a post; another tool run is not", () => {
  assert.ok(isPostReview(rv(POST)));
  assert.ok(!isPostReview(rv({ action: "run_tool", type: "sharepoint_save" })));
  assert.ok(!isPostReview({ Kind: "reply", DraftText: "hi" }));
  assert.equal(postOf(rv(POST)).network, "LinkedIn");
  assert.equal(label("approve", "post").replace("{network}", "LinkedIn"), "Post to LinkedIn");
});

test("waiting is live only on the newest turn; posted keeps its link; an older one reads not posted", () => {
  assert.deepEqual(postState({ Status: "pending" }, true), { live: true });
  assert.equal(postState({ Status: "pending" }, false).said, "Not posted");
  const done = postOf(rv(POST, { Status: "approved", FinalText: JSON.stringify({ ...POST, result: { url: "https://www.linkedin.com/feed/update/x" } }) }));
  assert.deepEqual(postState(done, false), { posted: true, url: "https://www.linkedin.com/feed/update/x" });
  assert.equal(postState({ Status: "rejected" }, true).said, "Not posted · dismissed");
});

// WHAT A TURN MADE, IN THE TURN: placed by `after` or named in its words, each thing once, never a working file or the post's own picture
test("a turn's files: placed or named, newest of a family, no working files, the post's picture skipped", () => {
  const row = (path, after, at) => ({ id: `output:${path}`, name: path, path, kind: "output", after, at, content_type: path.endsWith(".png") ? "image/png" : "text/csv" });
  const listed = [row("chart.png", "m2", "2026-11-05 10:02:00"), row("prices v2.csv", "m2", "2026-11-05 10:03:00"), row("prices v1.csv", "m2", "2026-11-05 10:01:00"),
    row("fetch.py", "m2", "2026-11-05 10:00:00"), row("gas.png", "m2", "2026-11-05 10:04:00"), row("older.csv", "m1", "2026-11-05 09:00:00")];
  const got = turnFiles({ listed, id: "m2", tid: 5, skip: ["gas.png"] }).map((f) => f.path).sort();
  assert.deepEqual(got, ["chart.png", "prices v2.csv"]);
  assert.deepEqual(turnFiles({ listed, id: "m1", tid: 5, words: "See `/x/scratch/outputs/TQ-0005/chart.png`" }).map((f) => f.path).sort(), ["chart.png", "older.csv"]);
});

// ...and the card leads Next steps, the action section; Close out never draws the post a second time in the chat
test("the post card leads Next steps and is drawn once", () => {
  const s = read("AgentSummary.jsx");
  const at = s.indexOf("\n      {lead}\n");
  assert.ok(at > s.indexOf("<DraftHead />") && at < s.indexOf("<OnYou items={onYou} />"));
  assert.match(read("TaskPage.jsx"), /const chatAsks = proposals\.filter\(\(p\) => !isPostReview\(p\)\)/);
  assert.match(read("ReviewDecision.jsx"), /post \? <PostCard/);
  assert.match(read("PostCard.jsx"), /\/api\/reviews\/\$\{row\.ReviewId\}\/decide/);       // the one decide road, no second approval
});
