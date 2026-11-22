import test from "node:test";
import assert from "node:assert/strict";


import { pickFor } from "../src/assistantProvider.js";


const cli = { id: "cli:claude", label: "Claude Code", type: "cli", model: "" };
const api = { id: "connector:21", label: "Work model (API)", type: "openai", model: "gpt-test" };

test("with no session the picker takes the server's answer, not the first row", () => {
  // provider_options lists CLIs first, so providers[0] nominated a coding agent (TQ-0420)
  assert.equal(pickFor({ providers: [cli, api], defaultPick: "connector:21" })?.id, "connector:21");
  assert.equal(pickFor({ providers: [cli], defaultPick: "cli:claude" })?.id, "cli:claude");
});

test("a live session still names its own provider", () => {
  assert.equal(pickFor({ providers: [cli, api], defaultPick: "connector:21",
    session: { pick: "cli:claude" } })?.id, "cli:claude");
  assert.equal(pickFor({ providers: [cli, api], defaultPick: "cli:claude",
    session: { provider: "Work model (API)" } })?.id, "connector:21");
});

test("an older server, or a pick that no longer exists, still lands on something", () => {
  assert.equal(pickFor({ providers: [cli, api] })?.id, "cli:claude");
  assert.equal(pickFor({ providers: [cli, api], defaultPick: "connector:999" })?.id, "cli:claude");
  assert.equal(pickFor({ providers: [] }), null);
  assert.equal(pickFor(null), null);
});
