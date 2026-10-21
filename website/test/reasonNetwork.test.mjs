import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { cleanTrusted, gateWords, sessionLine, trustOf, withTrust, withoutTrust } from "../src/reasonNetwork.js";

test("the trust list holds people and single sessions, never a group, the way the server keeps it", () => {
  assert.deepEqual(cleanTrusted(["Erin", "erin", " ray/web-codex@ray-xps ", "*", "erin/*", "repo:northwind/ledger", ""]), ["erin", "ray/web-codex"]);
  assert.deepEqual(withTrust(["erin"], "Ray"), ["erin", "ray"]);
  assert.deepEqual(withoutTrust(["erin", "ray"], "ERIN"), ["ray"]);
});

test("an address is trusted as its person, as that one session, or not at all - and the owner is always theirs", () => {
  const t = ["erin", "ray/web-codex"];
  assert.equal(trustOf(t, "erin/api-claude"), "person");
  assert.equal(trustOf(t, "ray/web-codex"), "session");
  assert.equal(trustOf(t, "ray/api-claude"), "");
  assert.equal(trustOf(t, "alex/terminal", "alex"), "you");
});

test("a session reads like `who`, and the gate says what it does in plain words", () => {
  assert.equal(sessionLine({ agent: "codex", repo: "northwind/portal", branch: "main", status: "busy", doing: "login form" }),
    "codex · northwind/portal@main · busy · login form");
  assert.equal(sessionLine({ agent: "claude-code", status: "idle" }), "claude-code · idle");
  assert.match(gateWords({ on: true }), /reaches no agent on this computer until you deliver it/);
  assert.match(gateWords({ on: false, default: "accept" }), /delivers teammates' messages/);
  assert.equal(gateWords(null), "");
});

test("the card is routed to its own page and wears its own mark", () => {
  const view = readFileSync("src/ConnectorsView.jsx", "utf8");
  assert.match(view, /conn\.Type === "reason_network" \? <ReasonDetail/);
  assert.match(view, /specialCards\("reason_network"/);
  assert.match(readFileSync("src/logos.jsx", "utf8"), /LOGOS\.reason_network = /);
  // never installs it: the card links to its own instructions
  assert.doesNotMatch(readFileSync("src/ReasonNetwork.jsx", "utf8"), /install\.sh|install\.ps1|irm https/);
});
