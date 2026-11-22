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
// the knob table itself lives in taskuary/settings_schema.json now (one file for the page and the
// assistant, 2026-09-18); the tests about WHAT the knobs are read it from there
const SCHEMA = JSON.parse(fs.readFileSync(path.join(process.cwd(), "..", "taskuary", "settings_schema.json"), "utf8"));
const KNOBS = SCHEMA.knobs, PANEL_OWNED = SCHEMA.panel_owned;


// THE SCHEMA IS THE ALLOWLIST (the 2026-10-19 UI walk): twelve one-shot migration flags - "_renamed_advisor", "_removed",
// "_backfilled", "_healed", "_line_set" - fell through every suffix rule into Other as switches. A key the schema does not name is
// never drawn, whatever it is called.
test("no stored key without a schema entry is drawn", async () => {
  const at = src.indexOf("const hidden = (name) =>");
  assert.match(src.slice(at, at + 60), /!KNOB_META\[name\] \|\|/, "hidden() starts with the allowlist");
  const KNOB_META = KNOBS, HIDDEN = new Set(), STATE = new Set();
  const isState = (n) => n.includes(":") || n.endsWith("_at") || STATE.has(n);
  const hidden = eval(src.slice(at + "const hidden = ".length, src.indexOf(";", at)));
  for (const k of ["assistant_report_renamed_advisor", "automate_report_removed", "first_run_dismissed", "report_triage_line_set",
                   "review_task_backfilled", "seeded_report_owner_healed", "some_future_flag"]) assert.equal(hidden(k), true, k);
  for (const k of Object.keys(KNOBS).filter((k) => !k.endsWith("_seeded") && !k.startsWith("owner_"))) assert.equal(hidden(k), false, k);
  // ...and Configuration's list offers no card for a group with nothing in it: Other read "its own panel" over an empty page
  assert.match(src, /const cfgShown = GROUPS\.filter\(\(g\) => g !== PHONE_GROUP && knobsIn\(g\) &&/);
  assert.match(src, /section === "config" \? cfgShown\.map\(/);
});
