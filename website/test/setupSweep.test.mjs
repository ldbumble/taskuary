// THE SETUP SWEEP (2026-10-28): setup, Connections, Settings and Reports read as a first-time owner, the approved fixes pinned here.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const cv = src("ConnectorsView.jsx");

test("a local model connects with its key box empty, and names its model", () => {
  assert.match(cv, /const KEYLESS_AI = \["ollama"\];/);
  assert.match(cv, /\(keyless \? !!\(cfg\.model \|\| ""\)\.trim\(\) : !!secret\.trim\(\)\)/);
  assert.match(cv, /\(k !== "model" \|\| keyless\)/);
});

test("mail setup says what it reads, under the sign-in and above Connect", () => {
  assert.match(cv, /export const MAIL_READS = "Reads your inbox and sent mail\. Never sends without you\.";/);
  assert.equal((cv.match(/\{reads\}/g) || []).length, 2);
});

test("a sign-in card draws no Get AI to set it up", () => {
  assert.match(cv, /const NO_AI_WALK = \["whatsapp", \.\.\.MS_SIGNIN, "gmail"\];/);
  assert.match(cv, /\{!NO_AI_WALK\.includes\(conn\.Type\) && <AiSetup conn=\{conn\}/);
});

test("WhatsApp's chats step is called Chats, its why in the step's text, no JID or bridge URL in a label", () => {
  const wa = cv.slice(cv.indexOf("  whatsapp: {"), cv.indexOf("  imessage: {"));
  assert.match(wa, /srcLabel: "Chats"/);
  assert.match(wa, /srcNote: "Only the chats switched on here come in\./);
  const labels = [...wa.matchAll(/fields: \[\[("[^"]+")|\],\s+\[("[^"]+")/g)].map((x) => x[1] || x[2]).join(" ");
  assert.doesNotMatch(labels, /JID|bridge URL/);
  assert.match(cv, /\{m\.srcNote && <Typography/);
});

test("required boxes, then the key, then the ones with a default; the fast clock under Advanced", () => {
  assert.match(cv, /const isOptional = \(\[label\]\) => \/optional\|blank\|default\/i\.test\(label\) && !\/required\/i\.test\(label\);/);
  const creds = cv.slice(cv.indexOf('{ label: "Credentials", done: creds'), cv.indexOf('{ label: "Test", done:'));
  const at = (s) => creds.indexOf(s);
  assert.ok(at("{need.map(") < at("helperText={SECRET_HELP}") && at("helperText={SECRET_HELP}") < at("{maybe.map(")
    && at("{maybe.map(") < at("data-tq-advanced-fold"), "need, key, maybe, Advanced");
  assert.doesNotMatch(cv, /Write-only: stored server-side/);
});

test("the steps after Credentials are not ticked before it is", () => {
  assert.match(cv, /const creds = credsDone\(conn, cfg, m\);/);
  assert.match(cv, /label: "Inbound — what becomes work", done: creds && inboundDone\(conn, mine\)/);
  assert.match(cv, /label: "More roles — reports, agents", done: creds,/);
});

test("the SQL and data cards' first tab is Setup, as every other card's", () => {
  assert.doesNotMatch(cv, /tabs=\{\["Connection", "Guide", "Agent"\]\}/);
  assert.equal((cv.match(/tabs=\{\["Setup", "Guide", "Agent"\]\}/g) || []).length, 3);
  assert.doesNotMatch(cv, /Paste a PAT/);
});

test("a failed install stands alone with its words, as ChatGPT's failed sign-in does", () => {
  const fr = src("FirstRun.jsx");
  assert.match(fr, /setInstFail\(\{ name: ai\.name, focus: true \}\)/);
  assert.match(fr, /instFail\?\.focus \? `cli-\$\{instFail\.name\}` : null/);
  assert.match(fr, /\["failing", "Didn't install - pick it to try again"\]/);
});

test("Your job, with a mailbox connected but not read yet, says wait - not connect one", () => {
  const ab = src("FirstRunAbout.jsx");
  assert.match(ab, /const soon = \/first read is still running\/i\.test\(draft\?\.why \|\| ""\);/);
});
