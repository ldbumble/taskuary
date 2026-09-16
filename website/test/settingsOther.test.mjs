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
  // ...and a real knob that merely looks similar is still offered
  const stateBlock = src.slice(src.indexOf("const STATE = new Set"), src.indexOf("const isState"));
  assert.ok(!/"assistant_card"/.test(stateBlock), "assistant_card is a real toggle, not state");
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
