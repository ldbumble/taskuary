// The "Other" tab is a catch-all: any row in the settings table without a KNOB_META entry lands
// there as an editable box. The settings table is ALSO where the app keeps its own bookkeeping -
// which CLI session a chat is on (concierge_cli_sid:<id>), where a per-task cursor got to
// (assistant_current:<id>), when a sweep last ran - so the tab filled with machine state you
// could type over: 185 of 249 rows on a real install, 162 of them per-entity ids and timestamps
// (the owner, 2026-09-16: "what is this? does not feel useful").
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = fs.readFileSync(path.join(process.cwd(), "src", "SettingsView.jsx"), "utf8");

test("per-entity state never renders as a knob", () => {
  assert.match(src, /const isState = \(name\) => name\.includes\(":"\) \|\| STATE\.has\(name\);/,
    "a `name:<id>` key is state by construction - there are hundreds of them and they are not settings");
  const at = src.indexOf("const hidden = (name) =>");
  assert.notEqual(at, -1);
  assert.ok(src.slice(at, at + 220).includes("isState(name)"),
    "hidden() is the one filter both the tab list and the search use, so the rule belongs there");
});

test("the scalar bookkeeping keys are named, not guessed at", () => {
  // Deliberately a list, not a prefix rule: `assistant_notes` is state, `assistant_card` is a
  // real toggle, and no prefix tells them apart. Anything added here stops being offered as a
  // knob, so it has to be a decision somebody made rather than a pattern that swept it up.
  for (const k of ["app_sessions", "assistant_last_run", "chat_cleanup_at",
                   "ingest_last_fetch_completed_at", "wall_rolled_on"]) {
    assert.ok(new RegExp(`"${k}"`).test(src.slice(src.indexOf("const STATE = new Set"), src.indexOf("const isState"))),
      `${k} is machine state and must not be offered as a setting`);
  }
  // `assistant_card` was in here as "a real toggle, not state" on the strength of it RENDERING
  // as a switch. It has no reader in any Python module or any browser file - it is dead, like
  // send_enabled and the rest, and the label was the only evidence for it. Assert the rule that
  // actually holds instead: a key in STATE is one nothing reads or one the app writes itself.
  const stateBlock = src.slice(src.indexOf("const STATE = new Set"), src.indexOf("const isState"));
  assert.ok(/"assistant_card"/.test(stateBlock) && /"counsel_enabled"/.test(stateBlock),
    "a knob with no reader is not offered, however much it looks like one");
});

test("a key the AI-defaults panel owns is suppressed on every tab, not just its own", () => {
  // assistant_ai lost its KNOB_META entry when it became a card, so meta() defaulted it to the
  // "Other" group - where the old tab-scoped guard did not run, and it came back as a bare
  // unlabelled text box next to the machine state (d3bde8bd).
  const at = src.indexOf("const rows = settings.filter");
  assert.notEqual(at, -1);
  const filter = src.slice(at, at + 260);
  assert.ok(filter.includes("!(panelOk && PANEL_OWNED.has(s.Name))"),
    "the suppression must not be scoped to one tab");
  assert.ok(!/cfgTab === "Triage & agents" && panelOk/.test(filter),
    "the old tab-scoped form is what let an owned key leak onto Other");
});

test("every panel-owned key still has a labelled fallback row", () => {
  // panelOk puts the plain rows back when the panel cannot load. A key with no KNOB_META entry
  // falls back to a box labelled with its own raw name, which is not a fallback.
  const from = src.indexOf("const PANEL_OWNED");
  const owned = src.slice(from, src.indexOf("]);", from));   // its own declaration, not the block after it
  for (const key of owned.match(/"([a-z_0-9]+)"/g).map((m) => m.slice(1, -1))) {
    assert.ok(new RegExp(`^  ${key}: \\{`, "m").test(src),
      `${key} is hidden by the panel but has no KNOB_META entry to fall back to`);
  }
});

test("one question gets one row: the three trust switches are a single control", () => {
  // Who may start a worker without you was three separate switches, so knowing the answer meant
  // reading all three (the owner, 2026-09-16: "combine trust own domain, sent history etc").
  const at = src.indexOf("  trust_own_domain: {");
  assert.notEqual(at, -1);
  const row = src.slice(at, at + 1400);
  assert.ok(row.includes('type: "flags"'), "it is one control over several boolean settings");
  for (const k of ["trust_own_domain", "trust_sent_history", "trust_non_email"]) {
    assert.ok(row.includes(`${k}: { label:`), `${k} must still be one of the pills`);
  }
  // no new key, no migration: senders.py keeps reading exactly what it read before
  assert.ok(!/trust_sources|trust_csv/.test(src), "combining the ROW must not invent a fourth setting");
  // ...and the two it now owns must not also appear as their own rows
  const state = src.slice(src.indexOf("const STATE = new Set"), src.indexOf("const isState"));
  for (const k of ["trust_sent_history", "trust_non_email"]) {
    assert.ok(state.includes(`"${k}"`), `${k} is drawn by the combined row, so it is not its own row`);
  }
});

test("every row the page offers is a knob somebody reads", () => {
  // The audit's own rule, kept honest: a key with no KNOB_META entry renders with its raw name
  // and no explanation, which is what the "Other" tab was. Nothing should reach it now.
  const keys = [...src.slice(src.indexOf("const KNOB_META = {")).matchAll(/^  ([a-z_0-9]+): \{/gm)].map((m) => m[1]);
  for (const dead of ["send_enabled", "outlook_drafts_enabled", "attach_threshold", "backup_agents",
                      "assistant_card", "counsel_enabled"]) {
    assert.ok(!keys.includes(dead), `${dead} has no reader - it must not be offered as a setting`);
  }
  for (const real of ["default_brain", "backup_brains", "profile_brains"]) {
    assert.ok(keys.includes(real), `${real} is read by agents.py and needs a row that explains it`);
  }
});

// ── a quiet assistant post promises only what it renders ─────────────────────────────────
test("the quiet post does not point at a block it has not got", () => {
  const feed = fs.readFileSync(path.join(process.cwd(), "src", "FeedView.jsx"), "utf8");
  const at = feed.indexOf("Nothing worth saying this time");
  assert.notEqual(at, -1);
  const line = feed.slice(at - 60, at + 220);
  assert.ok(/\{rv \? " What it read is below\." : ""\}/.test(line),
    "the promise must be conditional on the `what it reviewed` block actually being there");
});
