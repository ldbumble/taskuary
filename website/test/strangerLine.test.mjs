import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { strangerLine, trustInBox } from "../src/strangerLine.js";

test("a stranger's task gets the one line in plain words, with the reason for the tooltip", () => {
  const l = strangerLine({ origin: { origin: "stranger", why: "sent by someone not in your people" } });
  assert.equal(l.text, "From someone you haven't worked with here yet - anything risky waits for your OK");
  assert.equal(l.trust, "Trust them");
  assert.equal(l.why, "sent by someone not in your people");
  assert.doesNotMatch(l.text, /auto mode|stranger/i, "no coding-tool words for someone who never ran one");
});
test("words Taskuary wrote from what it read are not 'someone'", () => {
  const l = strangerLine({ origin: { origin: "stranger", why: "written by Taskuary's report from what it read" } });
  assert.match(l.text, /^Written by Taskuary from what it read/);
  assert.equal(l.trust, "Trust it");
});
test("owner, trusted and missing origin say nothing", () => {
  for (const o of ["owner", "trusted"]) assert.equal(strangerLine({ origin: { origin: o, why: "x" } }), null);
  assert.equal(strangerLine({}), null);
  assert.equal(strangerLine(null), null);
});
test("a stranger's task carries what its words read as trying to make an agent do, and only a stranger's", () => {
  assert.equal(strangerLine({ origin: { origin: "stranger", danger: "asks the agent to run a script from a link" } }).danger,
    "asks the agent to run a script from a link");
  assert.equal(strangerLine({ origin: { origin: "stranger" } }).danger, null);
  assert.equal(strangerLine({ origin: { origin: "trusted", danger: "x" } }), null);
});
test("the presses are the server's words for this sender, and no organisation where there is none to name (2026-10-26)", () => {
  const l = (trust) => strangerLine({ origin: { origin: "stranger", why: "x", trust } });
  const erin = l({ person: "Trust Erin", org: "Trust everyone at vendor.example" });
  assert.deepEqual([erin.trust, erin.trustOrg], ["Trust Erin", "Trust everyone at vendor.example"]);
  assert.equal(l({ person: "Trust Gail", org: "Trust Vendor Co" }).trustOrg, "Trust Vendor Co");
  assert.equal(l({ person: "Trust Omar", org: null }).trustOrg, null);
  assert.equal(l(undefined).trustOrg, null, "never an organisation button the server could not name");
});
test("the held box carries the presses; Came from then carries none (one place, one wording)", () => {
  assert.equal(trustInBox({ kind: "held", line: "Waiting for you.", trust: { person: "Trust Erin", org: null } }), true);
  assert.equal(trustInBox({ kind: "held", line: "Waiting for you." }), false, "a hold that is not the sender's (no repository) offers no trust");
  assert.equal(trustInBox({ kind: "idle", line: "Not started yet.", trust: { person: "Trust Erin" } }), false);
  const story = readFileSync(new URL("../src/AgentStory.jsx", import.meta.url), "utf8");
  assert.match(story, /onTrust && trustInBox\(story\) && <TrustButtons/);
  assert.match(story, /data-tq-trust-org="" [^>]*onClick=\{\(\) => onTrust\("org"\)\}>\{trust\.org\}/);
  const page = readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
  assert.match(page, /<AgentStory story=\{story\} compact=\{storyAt === "line"\} onTrust=\{trustPress\} \/>/);
  assert.match(page, /const trustBoxed = trustInBox\(story\) && \["line", "story"\]\.includes\(storyAt\)/);
  assert.match(page, /\{!trustBoxed && <>\{" · "\}/);
  assert.match(page, /runOperation\(api, "task\.trust", selected, scope \? \{ scope \} : undefined\)/);
});
