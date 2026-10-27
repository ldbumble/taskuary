// A DOUBLE-CLICK OPENS, IT DOES NOT OPEN AND SHUT (the overnight walk, 2026-10-27): the second click of a double-click on Find a
// time or a ▾ landed on the backdrop of what the first opened, and shut it. That click is swallowed; a later one shuts as before.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { GRACE_MS, installSecondClick } from "../src/secondClick.js";

function world() {
  const on = {};
  const doc = { addEventListener: (k, f, cap) => { assert.equal(cap, true, "heard before the page"); on[k] = f; }, removeEventListener: (k) => { delete on[k]; } };
  const el = (backdrop) => ({ matches: (sel) => backdrop && sel.split(",").some((s) => s.trim() === backdrop) });
  const click = (target, timeStamp) => { const e = { target, timeStamp, stopped: false, prevented: false,
    preventDefault() { this.prevented = true; }, stopImmediatePropagation() { this.stopped = true; } }; on.click?.(e); return e; };
  return { doc, el, click, off: installSecondClick(doc) };
}

test("the second click of a double-click on a button does not shut the dialog or menu its first click opened", () => {
  const w = world(), button = w.el(null);
  for (const backdrop of [".MuiBackdrop-root", ".MuiModal-backdrop", ".MuiDialog-container"]) {
    w.click(button, 1000);
    const second = w.click(w.el(backdrop), 1000 + 120);
    assert.ok(second.stopped && second.prevented, `${backdrop}: swallowed`);
  }
  w.off();
});

test("a click on the backdrop after a moment shuts it as before, and a click on anything else is never touched", () => {
  const w = world(), button = w.el(null);
  w.click(button, 1000);
  const later = w.click(w.el(".MuiBackdrop-root"), 1000 + GRACE_MS + 1);
  assert.ok(!later.stopped && !later.prevented, "the owner's own click outside");
  const other = w.click(button, 1100 + GRACE_MS);
  assert.ok(!other.stopped && !other.prevented);
  const again = w.click(button, 1100 + GRACE_MS + 50);
  assert.ok(!again.stopped, "a button's own second click is the page's to judge");
  w.off();
});

test("the page installs it once, at start", () => {
  const main = readFileSync(new URL("../src/main.jsx", import.meta.url), "utf8");
  assert.match(main, /import \{ installSecondClick \} from "\.\/secondClick\.js";\ninstallSecondClick\(\);/);
  const doc = { addEventListener() {}, removeEventListener() {} };
  installSecondClick(doc);
  assert.equal(doc.__tqSecondClick, true);
});
