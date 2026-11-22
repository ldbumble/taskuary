import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { oneOf } from "../src/connectorCatalog.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");


// the owner, 2026-10-20: Add another says WHAT it adds - read off the catalogue in one place (connectorCatalog.oneOf), not per card
test("Add another names what one card is, and a card that is one by nature has none", () => {
  const want = { outlook: "Outlook mailbox", gmail: "Gmail account", imap: "IMAP mailbox", teams: "Teams account", slack: "Slack workspace",
    github: "GitHub account", database: "database", postgresql: "PostgreSQL database", sharepoint: "SharePoint site", teller: "bank",
    simplefin: "bank", anthropic: "Anthropic API key", jira: "Jira account" };
  for (const [t, one] of Object.entries(want)) assert.equal(oneOf(t), one, t);
  // WhatsApp's paired phone, this Mac's Messages, the app's own knowledge, a keyless public feed
  for (const t of ["whatsapp", "imessage", "knowledge", "handbook", "local_whisper", "fred", "frankfurter"]) assert.equal(oneOf(t), null, t);
  // ...and the AI CLI agents page is not a connector card: it draws no identity row at all
  assert.doesNotMatch(read("AgentsPanel.jsx"), /ConnectorIdentity|Add another/);
});
