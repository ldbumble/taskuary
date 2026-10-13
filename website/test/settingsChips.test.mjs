// The Settings page's flag chips and channel chips change real settings, but each one was a
// plain clickable <Box>: Tab never reached them, and nothing announced whether the thing was on
// or off - the only signal was the fill colour (#154).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("settings flag chips are keyboard-operable buttons that say their state", () => {
  const settings = read("SettingsView.jsx");

  // component="button" is what puts it in the tab order; aria-pressed is what says on or off.
  assert.match(settings,
    /<Box key=\{k\} component="button" type="button" title=\{m\.flags\[k\]\.help\} aria-pressed=\{!!val\(k\)\}/,
    "the flag chip is a button, keeps its tooltip, and publishes its state");
  // a native <button> does not inherit the page's typeface - the chip must not change font
  assert.match(settings, /cursor: "pointer", fontFamily: "inherit", fontSize: 11\.5, fontWeight: val\(k\) \? 700 : 500/,
    "the chip keeps the type it had as a Box");
});

test("settings channel chips are keyboard-operable buttons that say their state", () => {
  const settings = read("SettingsView.jsx");

  assert.match(settings,
    /<Box key=\{ch\} component="button" type="button" aria-pressed=\{on\.has\(ch\)\} onClick=\{\(\) => toggle\(ch\)\}/,
    "the channel chip is a button and publishes whether that channel is on");
  assert.match(settings, /cursor: "pointer", fontFamily: "inherit", fontSize: 11\.5, fontWeight: on\.has\(ch\) \? 700 : 500/,
    "the chip keeps the type it had as a Box");
});
