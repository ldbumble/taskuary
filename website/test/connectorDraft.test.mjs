// One Save per connection card (the owner, 2026-09-28: "all connectors should have save button and show pending
// change? better ux"). The rules in connectorDraft.js, and a guard that no settings control posts behind its back.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { applied, changes, saveBody, say, stage, stageable } from "../src/connectorDraft.js";

const conn = { ConnectorId: 3, Active: 1, Roles: "trigger", Scope: "read", ConfigJson: JSON.stringify({ bulk: "clear", reply_comments: false }) };

test("a control's settings post is held; an action is not", () => {
  assert.equal(stageable({ ConnectorId: 3, ConfigJson: "{}" }, "ConnectorId"), true);
  assert.equal(stageable({ ConnectorId: 3, Active: false, Roles: "feed" }, "ConnectorId"), true);
  assert.equal(stageable({ Type: "github", Name: "x" }, "ConnectorId"), false);          // creating one
  assert.equal(stageable({ Channel: "github", Address: "org/app" }, "SourceId"), false);  // adding a source
});

test("the draft is what the controls want, laid over what is saved", () => {
  let want = stage(null, { ConnectorId: 3, ConfigJson: JSON.stringify({ bulk: "rank", reply_comments: false }) });
  // the next control builds on the draft it was drawn from, so it carries the first change too
  want = stage(want, { ConnectorId: 3, ConfigJson: JSON.stringify({ ...JSON.parse(applied(conn, want).ConfigJson), bulk_head: 6 }) });
  want = stage(want, { ConnectorId: 3, Roles: "trigger,feed" });
  const draft = applied(conn, want);
  assert.deepEqual(JSON.parse(draft.ConfigJson), { bulk: "rank", reply_comments: false, bulk_head: 6 });
  assert.equal(draft.Roles, "trigger,feed");
  assert.deepEqual(changes(conn, want).map((c) => `${c.key}:${c.from}->${c.to}`),
    ["Roles:trigger->feed,trigger", "bulk:clear->rank", "bulk_head:undefined->6"]);
});

test("changing a setting back to what is saved leaves nothing pending, and nothing to post", () => {
  const want = stage(stage(null, { ConnectorId: 3, Active: false }), { ConnectorId: 3, Active: true });
  assert.deepEqual(changes(conn, want), []);
  assert.equal(saveBody(conn, want, "ConnectorId"), null);
});

test("Save posts only the fields that changed", () => {
  const want = stage(null, { ConnectorId: 3, Scope: "write", ConfigJson: conn.ConfigJson });
  assert.deepEqual(saveBody(conn, want, "ConnectorId"), { ConnectorId: 3, Scope: "write" });
});

test("the bar says values in words", () => {
  const words = { bulk: { rank: "Ranked together", clear: "One by one", "": "One by one" } };
  assert.equal(say("rank", "bulk", words), "Ranked together");
  assert.equal(say(undefined, "bulk", words), "One by one");
  assert.equal(say(true, "x"), "on");
  assert.equal(say(undefined, "x"), "off");
  assert.equal(say(["inbox", "sent"], "folders"), "inbox, sent");
});

test("no settings control on a connection card saves by itself any more", () => {
  const src = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");
  // every connector post left is an action: a rename, or a credential save that tests the connection right after
  const posts = src.match(/api\.post\("\/api\/connectors", \{ ConnectorId: conn\.ConnectorId,.*$/gm) || [];
  assert.ok(posts.every((p) => /Name: value|Active: true/.test(p)), posts.join("\n"));
  assert.ok(!/api\.post\("\/api\/sources", \{ SourceId/.test(src), "a source setting posted by itself");
  assert.ok(!src.includes("Save prompts"));
  assert.match(src, /<SaveBar draft=\{draft\} labels=\{DRAFT_LABELS\} words=\{DRAFT_WORDS\} \/>/);
});
