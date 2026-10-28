import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { oneOf } from "../src/connectorCatalog.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// the owner, 2026-10-20: "does every connector allow multiple of the same connector? Like Outlook - I only see a way to connect
// one, not more". Every card's detail carries Add another (a clean instance of the same type), and so does setup's mailbox card.
test("every connector detail draws Add another, on the card's own identity row", () => {
  const cv = read("ConnectorsView.jsx");
  assert.match(cv, /function ConnectorIdentity\(\{ conn, reload, onCreated, addOnly = false \}\)/);
  assert.match(cv, /api\.post\("\/api\/connectors", \{ Type: conn\.Type, Name: value \}\)/, "a new instance of the same type, no credentials");
  assert.match(cv, /\{!one \|\| !connected \? null : !adding \? \(\s+<Button .*>Add another \{one\}<\/Button>/, "says what it adds, or is not drawn");
  // ...and only once this card is connected: a second before there is a first (the setup sweep, 2026-10-28)
  assert.match(cv, /const connected = !!\(conn\.HasSecret \|\| conn\.LastSyncAt\);/);
  assert.match(cv, /const one = oneOf\(conn\.Type\);/);
  // channel cards (Outlook, Gmail, IMAP, Teams, Slack, GitHub, the AI cards ...), SQL Server, WinRM and every data card
  for (const fn of ["ChannelDetail", "MssqlDetail", "WinrmDetail", "DataDetail"]) {
    const body = cv.slice(cv.indexOf(`function ${fn}(`), cv.indexOf("\nfunction ", cv.indexOf(`function ${fn}(`) + 10));
    assert.match(body, /<ConnectorIdentity conn=\{conn\} reload=\{reload\} onCreated=\{onCreated\} \/>/, `${fn} has Add another`);
  }
  // ...and the Outlook card is a ChannelDetail: no detail of its own that could leave the row out
  assert.match(cv, /: <ChannelDetail key=\{conn\.ConnectorId\} \{\.\.\.shared\} sources=\{sources\} onNavigate=\{onNavigate\} \/>;/);
  assert.doesNotMatch(cv, /conn\.Type === "outlook" \? <[A-Z]\w*Detail/);
});

test("setup's mailbox cards keep Add another, so a second Outlook account has a way in from the first run", () => {
  const cv = read("ConnectorsView.jsx"), fr = read("FirstRun.jsx");
  assert.match(cv, /const another = MAIL_CARDS\.includes\(conn\.Type\) && <ConnectorIdentity conn=\{conn\} reload=\{reload\} onCreated=\{onCreated\} addOnly \/>;/);
  assert.match(cv, /<MsSignIn conn=\{conn\} cfg=\{cfg\} reload=\{reload\} onSignedIn=\{onConnected\} plain \/>\s+\{reads\}\s+\{another\}/, "under the Microsoft sign-in");
  assert.match(cv, /<TestLine test=\{test\} mt=\{0\} \/>\s+\{another\}\s+<\/Box>\s+\);\s+\}\s+return \(/, "under Gmail's and IMAP's Connect");
  assert.match(cv, /const MAIL_CARDS = \["outlook", "gmail", "imap"\];/);
  // addOnly draws the door alone - setup has no name to edit
  assert.match(cv, /\{!addOnly && <>\s+<TextField size="small" label="Connection name"/);
  assert.match(cv, /if \(addOnly && \(!one \|\| !connected\)\) return null;/);
  // the card that was added opens in place, still simple; and Connect names the card pressed, not the first of its type
  assert.match(fr, /onCreated=\{\(id\) => \{ setOpen\(\{ id, simple: open\.simple \}\); reload\(\); \}\}/);
  assert.match(cv, /\{ type: conn\.Type, cid: conn\.ConnectorId, address: cfg\.address \|\| "", password: secret, host: cfg\.imap_host \|\| "" \}/);
  assert.match(fr, /a second one of the same kind is Add another on its card/);
});

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
