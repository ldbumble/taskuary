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


test("Settings: the switch is a schema knob in a group always shown, and saving it reads capabilities again", () => {
  const k = schema.knobs.developer_mode;
  assert.equal(k.label, "Developer mode"); assert.equal(k.type, "switch"); assert.notEqual(k.group, "Coding agent", "the Coding agent group hides with coding");
  assert.match(k.desc, /Off: every job goes to a general agent\./);
  assert.match(read("SettingsView.jsx"), /if \(ok && name === "developer_mode"\) refreshCapabilities\(\);/);
});

// WALK 25 (2026-11-26): "the top bar changes between shots: Board appears and disappears" - Developer mode read off until its first read
// landed, so each load drew Chat · Game and pushed Board in a beat later. The last read is drawn from the first frame
test("the top bar opens on Developer mode as this browser last read it, and off where it never has", async () => {
  const { devSeen, rememberDev } = await import("../src/devSeen.js");
  const kept = new Map(), store = { getItem: (k) => kept.get(k) ?? null, setItem: (k, v) => kept.set(k, String(v)) };
  assert.equal(devSeen(store), false, "never read: off, no coding door flashes");
  rememberDev(true, store); assert.equal(devSeen(store), true, "on at the last read: Board from the first frame");
  rememberDev(false, store); assert.equal(devSeen(store), false, "switched off: gone from the first frame");
  const shut = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  rememberDev(true, shut); assert.equal(devSeen(shut), false, "storage refused: it reads as before");
  assert.equal(devSeen(null), false);
});
