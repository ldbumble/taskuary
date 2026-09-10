// A set-up proposed in the chat (PW-194/195): the card shows the configuration facts, can dry-run a report before the
// click, and links to the created resource's own screen afterwards.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe } from "../src/proposalCard.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("the card shows the report's facts, not the raw config, and offers a dry run", () => {
  const p = { id: "r1", kind: "report.create", target: 0, version: 1, params: { config: { type: "sqlite" }, title: "Open tasks", schedule: "cron 0 8 * * 1", enabled: "yes", triage: "informational" }, label: "Create the report", summary: "Open tasks (sqlite)" };
  const d = describe(p);
  assert.deepEqual(d.params, [["title", "Open tasks"], ["schedule", "cron 0 8 * * 1"], ["enabled", "yes"], ["triage", "informational"]]);
  assert.equal(d.preview, true);
  assert.equal(describe({ ...p, kind: "connection.create" }).preview, false);
});

test("preview and the link after the click are wired through the shared card", () => {
  const card = read("ProposalCard.jsx");
  assert.match(card, /onPreview\?\.\(p\)/);
  assert.match(card, />\{peek\?\.busy \? "Running…" : "Preview"\}<\/button>/);
  assert.match(card, /p\.status === "done" && p\.outcome\?\.link && <div[^>]*><a href=\{p\.outcome\.link\}/);
  const view = read("AssistantView.jsx");
  assert.match(view, /api\.post\(`\/api\/operations\/\$\{p\.id\}\/preview`\)/);
  assert.match(view, /outcome: res\?\.outcome \|\| null/);
  assert.match(view, /onPreview=\{actions\.preview\}/);
});
