import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { pickFor } from "../src/assistantProvider.js";
import { agentCardView } from "../src/agentCardView.js";

const read = (f) => readFileSync(fileURLToPath(new URL(f, import.meta.url)), "utf8");
const cli = { id: "cli:coder", label: "Claude Code · coder (your CLI)", type: "cli", model: "" };
const api = { id: "connector:21", label: "Work model (API)", type: "openai", model: "gpt-test" };

test("with no session the picker takes the server's answer, not the first row", () => {
  // provider_options lists CLIs first, so providers[0] nominated a coding agent (TQ-0420)
  assert.equal(pickFor({ providers: [cli, api], defaultPick: "connector:21" })?.id, "connector:21");
  assert.equal(pickFor({ providers: [cli], defaultPick: "cli:coder" })?.id, "cli:coder");
});

test("a live session still names its own provider", () => {
  assert.equal(pickFor({ providers: [cli, api], defaultPick: "connector:21",
    session: { pick: "cli:coder" } })?.id, "cli:coder");
  assert.equal(pickFor({ providers: [cli, api], defaultPick: "cli:coder",
    session: { provider: "Work model (API)" } })?.id, "connector:21");
});

test("an older server, or a pick that no longer exists, still lands on something", () => {
  assert.equal(pickFor({ providers: [cli, api] })?.id, "cli:coder");
  assert.equal(pickFor({ providers: [cli, api], defaultPick: "connector:999" })?.id, "cli:coder");
  assert.equal(pickFor({ providers: [] }), null);
  assert.equal(pickFor(null), null);
});

test("an assistant chat is not a terminal to look at", () => {
  assert.equal(agentCardView("assistant"), "chat");
  assert.equal(agentCardView("terminal"), "terminal");
  assert.equal(agentCardView(undefined), "terminal");
});

test("the workspace and the agent card use those readings", () => {
  assert.match(read("../src/GeneralWorkspace.jsx"), /pickFor\(payload\)/);
  const card = read("../src/assistantCards.jsx");
  assert.match(card, /agentCardView\(card\.mode\)/);
  const body = card.slice(card.indexOf("export function AgentCard"));
  assert.ok(body.indexOf("tq-card-chat") < body.indexOf("tq-card-term"),
    "the chat branch must be reached before the terminal one, so an assistant is never drawn as a screen");
  assert.match(body, /!\(chat && live\) && <TextField/, "the waiting-room box is not offered beside a live chat composer");
});
