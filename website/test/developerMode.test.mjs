// DEVELOPER MODE (the owner, 2026-11-02): "for regular people everything should be a general agent, not coding ... in setup you should
// have to enable developer mode and then connect GitHub" - a plain switch step in setup, an optional Connect GitHub only once it is on,
// and the same switch in Settings, which reads capabilities again so coding comes or goes on every screen.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import schema from "../../taskuary/settings_schema.json" with { type: "json" };
import { doneOf, nextOf, prevOf } from "../src/setupSteps.js";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const OPTIONAL = ["dev", "github", "other"];
const rail = (keys) => ({ rail: keys.map((key) => ({ key, done: false, open: true, optional: OPTIONAL.includes(key) })) });
const OFF = rail(["ai", "mail", "about", "dev", "other", "finish"]), ON = rail(["ai", "mail", "about", "dev", "github", "other", "finish"]);

test("Connect GitHub is a step only while the server's rail draws it - Developer mode on", () => {
  assert.equal(nextOf("about", OFF), "dev"); assert.equal(nextOf("dev", OFF), "other", "off: no GitHub step");
  assert.equal(nextOf("dev", ON), "github"); assert.equal(nextOf("github", ON), "other");
  assert.equal(prevOf("other", OFF), "dev"); assert.equal(prevOf("other", ON), "github");
});

test("both are optional: Next never waits on them", () => {
  assert.ok(doneOf(ON, "dev")); assert.ok(doneOf(ON, "github"));
});

test("setup's step is one plain switch, saved like any knob, and GitHub is the catalogue's own card", () => {
  const fr = read("FirstRun.jsx");
  assert.match(fr, />Are you a developer\?</);
  assert.match(fr, /<Switch checked=\{!!st\.developer_mode\} disabled=\{devBusy\} onChange=\{\(e\) => setDev\(e\.target\.checked\)\} \/>/);
  assert.match(fr, /api\.patch\("\/api\/settings", \{ name: "developer_mode", value: on \? "1" : "0" \}\)/);
  assert.match(fr, /\{shelf\("github", byType\(\["github"\]\)\.map\(\(c\) => card\(c, false\)\), "More"\)\}/);
});

test("Settings: the switch is a schema knob in a group always shown, and saving it reads capabilities again", () => {
  const k = schema.knobs.developer_mode;
  assert.equal(k.label, "Developer mode"); assert.equal(k.type, "switch"); assert.notEqual(k.group, "Coding agent", "the Coding agent group hides with coding");
  assert.match(k.desc, /Off: every job goes to a general agent\./);
  assert.match(read("SettingsView.jsx"), /if \(ok && name === "developer_mode"\) refreshCapabilities\(\);/);
});
