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

// WHAT A TURN MADE, IN THE TURN: placed by `after` or named in its words, each thing once, whatever its kind - less the post's own picture
test("a turn's files: placed or named, newest of a family, the helper script too, the post's picture skipped", () => {
  const row = (path, after, at) => ({ id: `output:${path}`, name: path, path, kind: "output", after, at, content_type: path.endsWith(".png") ? "image/png" : "text/csv" });
  const listed = [row("chart.png", "m2", "2026-11-05 10:02:00"), row("prices v2.csv", "m2", "2026-11-05 10:03:00"), row("prices v1.csv", "m2", "2026-11-05 10:01:00"),
    row("fetch.py", "m2", "2026-11-05 10:00:00"), row("gas.png", "m2", "2026-11-05 10:04:00"), row("older.csv", "m1", "2026-11-05 09:00:00")];
  const got = turnFiles({ listed, id: "m2", tid: 5, skip: ["gas.png"] }).map((f) => f.path).sort();
  assert.deepEqual(got, ["chart.png", "fetch.py", "prices v2.csv"]);
  // ...and a file another turn made is drawn there, never again under an answer that only names it (the walk, 2026-11-18)
  assert.deepEqual(turnFiles({ listed, id: "m1", tid: 5, words: "See `/x/scratch/outputs/TQ-0005/chart.png`" }).map((f) => f.path).sort(), ["older.csv"]);
});


test("a post whose press failed is over: no box, no button, its error the line", async () => {
  const { stateOf } = await import("../src/actionCard.js");
  const st = stateOf({ Status: "superseded", ActError: "the network refused the post", post: { type: "linkedin_post" } });
  assert.equal(st.live, undefined); assert.equal(st.failed, true); assert.equal(st.done, false);
});

// ...ITS CONNECTION NOT MADE, SAID ON EVERY ROAD (the card round, 2026-11-18): the review the page reads carries `Connect` (server
// _review_connect), and the card drawn from it - a review list, a batch - lost it, so its Post was lit where the chat's card said Connect
test("a card read from its review keeps the review's Connect", () => {
  const fix = { says: "Jira isn't connected", label: "Connect Jira", href: "#connector=jira" };
  assert.deepEqual(cardOf(rv({ action: "run_tool", type: "jira_comment", item: "NW-12", body: "Done." }, { Connect: fix })).connect, fix);
  assert.equal(cardOf(rv(POST)).connect, null);
  assert.equal(cardOf(rv(POST, { Connect: fix, Status: "approved" })).connect, null);
  // ...and a press that failed is said as failed, never "Not posted · dismissed" - he dismissed nothing
  const failed = cardOf(rv(POST, { Status: "superseded", ActError: "the network refused the post" }));
  assert.equal(stateOf(failed).failed, true);
});

// AN ACT WHOSE WORDS ARE OPTIONAL IS NOT HELD ON AN EMPTY BOX (the stress round, 2026-11-18): an agent set up "close northwind/ledger#12"
// with no comment - the executor takes none (github.run_github_close) - and the card drew Close issue greyed over its empty box, a press
// nothing could light. A comment the agent wrote and the owner emptied still holds it: an empty box is never sent as the agent's words.
test("Close issue with no comment proposed can be pressed; a comment or a post the box needs cannot go empty", async () => {
  const { pressable } = await import("../src/actionCard.js");
  const close = actionFor("github_close"), CLOSE = { action: "run_tool", type: "github_close", repo: "northwind/ledger", number: 12 };
  assert.ok(pressable(close, CLOSE, ""));
  assert.ok(pressable(close, CLOSE, "Fixed in the last release."));
  assert.ok(!pressable(close, { ...CLOSE, comment: "Fixed." }, "  "));
  assert.ok(pressable(actionFor("github_issue"), { action: "run_tool", type: "github_issue", repo: "northwind/ledger", title: "Totals off" }, ""));
  assert.ok(!pressable(actionFor("jira_comment"), { action: "run_tool", type: "jira_comment", item: "NW-12" }, ""));
  assert.ok(!pressable(actionFor("linkedin_post"), { ...POST, text: "" }, ""));
});

// THE CARD'S FACE BY THE ONE RULE A FACE READS (design round 6, D3: the X card's avatar read "X(" - the first mark of "(Twitter)")
test("a post card's avatar is the account's initials by profileAvatar's rule, never a bracket", async () => {
  const { initialsOf } = await import("../src/profileAvatar.js");
  assert.equal(initialsOf("X (Twitter)"), "X");
  assert.equal(initialsOf("Northwind Social"), "NS");
  const ac = readFileSync(new URL("../src/ActionCard.jsx", import.meta.url), "utf8");
  assert.match(ac, /const initials = \(s\) => \(String\(s \|\| ""\)\.trim\(\) \? initialsOf\(s\) : "in"\);/);
});
