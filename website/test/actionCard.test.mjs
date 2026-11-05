import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { actionFor, cardOf, changed, fieldsOf, isCardReview, stateOf, textKey, valuesOf, wordsOf } from "../src/actionCard.js";
import { turnFiles } from "../src/taskOutputs.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
const rv = (p, extra = {}) => ({ ReviewId: 7, Kind: "action", Status: "pending", DraftText: JSON.stringify(p), ...extra });
const POST = { action: "run_tool", type: "linkedin_post", connector_id: 3, text: "Gas rose 4 cents.", image: "gas.png", visibility: "CONNECTIONS", publish: "now" };

// EACH CONNECTOR DECLARES ITS ACT'S CARD (the owner, 2026-11-05): the catalogue's `actions`, read here; one card draws whatever is declared
test("a run_tool on a tool a connector declares a card for is a card; another tool run is not", () => {
  assert.ok(isCardReview(rv(POST)));
  assert.ok(isCardReview(rv({ action: "run_tool", type: "jira_comment", item: "NW-12", body: "Done." })));
  assert.ok(!isCardReview(rv({ action: "run_tool", type: "sharepoint_save" })));
  assert.ok(!isCardReview({ Kind: "reply", DraftText: "hi" }));
  assert.equal(cardOf(rv(POST)).network, "LinkedIn");
});

test("the card's fields map from the declaration: values from the proposal, else the catalogue's default; editable only while it waits", () => {
  const act = actionFor("linkedin_post");
  const f = fieldsOf(act, { ...POST, visibility: undefined, publish: undefined }, true);
  assert.deepEqual(f.map((x) => [x.key, x.type, x.value]), [["text", "text", "Gas rose 4 cents."], ["image", "image", "gas.png"],
    ["visibility", "choice", "PUBLIC"], ["publish", "choice", "now"]]);
  assert.deepEqual(f.filter((x) => x.editable).map((x) => x.key), ["text", "visibility", "publish"]);
  assert.deepEqual(fieldsOf(act, POST, undefined).filter((x) => x.editable), []);       // an older turn's card is read-only, live unsaid included
  assert.equal(textKey(actionFor("jira_comment")), "body");
  assert.equal(textKey(act), "text");
});

test("the press's words follow the pick: Post to LinkedIn, or Save as draft", () => {
  const act = actionFor("linkedin_post");
  assert.deepEqual(wordsOf(act, valuesOf(act, POST)), { press: "Post to LinkedIn", busy: "Posting…", done: "Posted", undone: "Not posted" });
  assert.equal(wordsOf(act, { ...valuesOf(act, POST), publish: "draft" }).press, "Save as draft");
  assert.equal(wordsOf(actionFor("bluesky_post"), {}).press, "Post to Bluesky");
  assert.equal(wordsOf(actionFor("jira_comment"), {}).press, "Post comment");
});

test("only the choices the owner moved go with the press", () => {
  const act = actionFor("linkedin_post");
  assert.deepEqual(changed(act, POST, valuesOf(act, POST)), {});
  assert.deepEqual(changed(act, POST, { ...valuesOf(act, POST), publish: "draft" }), { publish: "draft" });
  assert.deepEqual(changed(act, { ...POST, visibility: undefined }, { ...valuesOf(act, POST), visibility: "PUBLIC" }), {});   // the default, unmoved
});

test("waiting is live only on the newest turn; done keeps its words and link; an older one reads not posted", () => {
  const row = (Status, post = POST) => ({ Status, post });
  assert.deepEqual(stateOf(row("pending"), true), { live: true });
  assert.equal(stateOf(row("pending"), false).said, "Not posted");
  const done = cardOf(rv(POST, { Status: "approved", FinalText: JSON.stringify({ ...POST, result: { url: "https://www.linkedin.com/feed/update/x" } }) }));
  assert.deepEqual(stateOf(done, false), { done: true, said: "Posted", url: "https://www.linkedin.com/feed/update/x" });
  assert.equal(stateOf(row("approved", { ...POST, publish: "draft" })).said, "Saved as a draft");
  assert.equal(stateOf(row("rejected"), true).said, "Not posted · dismissed");
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

// ...and the card leads Next steps, the action section; Close out never draws it a second time in the chat
test("the action card leads Next steps and is drawn once", () => {
  const s = read("AgentSummary.jsx");
  const at = s.indexOf("\n      {lead}\n");
  assert.ok(at > s.indexOf("<DraftHead />") && at < s.indexOf("<OnYou items={onYou} />"));
  assert.match(read("TaskPage.jsx"), /const chatAsks = proposals\.filter\(\(p\) => !isCardReview\(p\)\)/);
  assert.match(read("ReviewDecision.jsx"), /act \? <ActionCard/);
  assert.match(read("ActionCard.jsx"), /\/api\/reviews\/\$\{row\.ReviewId\}\/decide/);       // the one decide road, no second approval
});
