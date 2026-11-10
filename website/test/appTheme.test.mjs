import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");

test("the saved or system theme is applied before the UI and styles load", () => {
  const script = html.match(/<script id="tq-theme-init">([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script, "missing first-paint theme bootstrap");
  assert.ok(html.indexOf('id="tq-theme-init"') < html.indexOf("<style>"));
  for (const [stored, system, expected] of [["dark", false, "dark"], ["light", true, "light"], [null, true, "dark"], ["broken", false, "light"]]) {
    const root = { dataset: {}, style: {} };
    vm.runInNewContext(script, { document: { documentElement: root }, localStorage: { getItem: () => stored }, window: { matchMedia: () => ({ matches: system }) } });
    assert.equal(root.dataset.theme, expected);
    assert.equal(root.style.colorScheme, expected);
  }
});

test("first paint follows the system even when storage is denied", () => {
  const script = html.match(/<script id="tq-theme-init">([\s\S]*?)<\/script>/)?.[1];
  assert.ok(script, "missing first-paint theme bootstrap");
  const root = { dataset: {}, style: {} };
  vm.runInNewContext(script, { document: { documentElement: root }, localStorage: { getItem() { throw Error("denied"); } }, window: { matchMedia: () => ({ matches: true }) } });
  assert.equal(root.dataset.theme, "dark");
});

async function fixture(stored = null, dark = false, denied = false) {
  const { createThemeController, THEME_KEY } = await import("../src/appTheme.js");
  const root = { dataset: {}, style: {} }, media = new EventTarget(), events = new EventTarget();
  media.matches = dark;
  const storage = { getItem: () => { if (denied) throw Error("denied"); return stored; }, setItem: (key, value) => { assert.equal(key, THEME_KEY); if (denied) throw Error("denied"); stored = value; } };
  const controller = createThemeController({ root, storage: () => storage, media, events });
  const storageEvent = (value, key = THEME_KEY) => { const e = new Event("storage"); Object.assign(e, { key, newValue: value, storageArea: storage }); events.dispatchEvent(e); };
  return { controller, root, media, storageEvent, stored: () => stored };
}

test("toggle saves the choice, updates the document and notifies MUI subscribers", async () => {
  const f = await fixture(null, false), seen = [];
  const off = f.controller.subscribe(() => seen.push(f.controller.getSnapshot()));
  f.controller.toggle();
  assert.equal(f.root.dataset.theme, "dark");
  assert.equal(f.stored(), "dark");
  f.controller.toggle();
  assert.equal(f.root.style.colorScheme, "light");
  assert.deepEqual(seen, ["dark", "light"]);
  off();
  assert.equal((await fixture(f.stored(), true)).controller.getSnapshot(), "light");
});

test("system changes apply until a person chooses, and storage events synchronize tabs", async () => {
  const f = await fixture("invalid"), seen = [];
  const off = f.controller.subscribe(() => seen.push(f.controller.getSnapshot()));
  f.media.matches = true; f.media.dispatchEvent(new Event("change"));
  assert.equal(f.controller.getSnapshot(), "dark");
  f.controller.toggle();
  f.media.matches = true; f.media.dispatchEvent(new Event("change"));
  assert.equal(f.controller.getSnapshot(), "light");
  f.storageEvent("dark", "unrelated");
  assert.equal(f.controller.getSnapshot(), "light");
  f.storageEvent("dark");
  assert.equal(f.root.dataset.theme, "dark");
  f.storageEvent(null); // clearing the preference returns to the system
  f.media.matches = false; f.media.dispatchEvent(new Event("change"));
  assert.equal(f.controller.getSnapshot(), "light");
  off();
  const n = seen.length;
  f.storageEvent("dark");
  assert.equal(seen.length, n);
});

test("switching remains usable when localStorage throws", async () => {
  const f = await fixture(null, true, true);
  const off = f.controller.subscribe(() => {});
  assert.equal(f.controller.getSnapshot(), "dark");
  assert.doesNotThrow(() => f.controller.toggle());
  assert.equal(f.controller.getSnapshot(), "light");
  f.media.dispatchEvent(new Event("change"));
  assert.equal(f.controller.getSnapshot(), "light");
  off();
});
