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

// THE PAGE CHANGED UNDER A STILL POINTER (the button stress, 2026-11-02): a triple-click on Not a task ticked a to-do box of the task drawn in
// its place; a double-click on Change ▾'s Priority picked a priority from the menu it opened at the same spot
test("a click at the same spot a moment later on another control is the first click's repeat; the same control, a moved hand or a later click are not", () => {
  const on = {};
  const doc = { addEventListener: (k, f) => { on[k] = f; }, removeEventListener: (k) => { delete on[k]; } };
  installSecondClick(doc);
  const control = () => { const c = { matches: () => false, contains: (x) => x === c }; c.closest = () => c; return c; };
  const click = (target, timeStamp, x = 100, y = 200) => { const e = { target, timeStamp, clientX: x, clientY: y, isTrusted: true, stopped: false,
    preventDefault() {}, stopImmediatePropagation() { this.stopped = true; } }; on.click(e); return e; };
  const done = control(), box = control(), label = control();
  click(done, 1000);
  assert.ok(click(box, 1070).stopped, "the next task's box under the pointer was ticked");
  assert.ok(click(box, 1140).stopped, "...nor by the third click");
  assert.ok(!click(box, 1000 + GRACE_MS + 10).stopped, "a press after the moment is a press");
  click(done, 3000);
  assert.ok(!click(done, 3070).stopped, "the same button's second click is the page's to judge");
  assert.ok(!click(box, 3100, 300, 200).stopped, "another place is another press");
  label.control = box;
  click(label, 5000);
  assert.ok(!click(box, 5001).stopped, "a label's click on its own box is one control");
  click(done, 7000);
  const code = { target: box, timeStamp: 7050, clientX: 100, clientY: 200, isTrusted: false, stopped: false, preventDefault() {}, stopImmediatePropagation() { this.stopped = true; } };
  on.click(code);
  assert.ok(!code.stopped, "the page's own click() is never a hand's repeat");
});

test("the page installs it once, at start", () => {
  const main = readFileSync(new URL("../src/main.jsx", import.meta.url), "utf8");
  assert.match(main, /import \{ installSecondClick \} from "\.\/secondClick\.js";\ninstallSecondClick\(\);/);
  const doc = { addEventListener() {}, removeEventListener() {} };
  installSecondClick(doc);
  assert.equal(doc.__tqSecondClick, true);
});

// THE NEXT CARD DRAWN UNDER A STILL POINTER (design round 4, 2026-11-19): Send on the first of two letters, the second card drew where the press
// had landed seconds later - after the agent's answer - and the next press sent a letter he never read
test("a control that came under the pressed spot takes no press for its first moment, however long after the press it came", () => {
  const on = {}; let t = 0, under = null, check = null;
  const doc = { addEventListener: (k, f) => { on[k] = f; }, removeEventListener: (k) => { delete on[k]; }, elementFromPoint: () => under };
  installSecondClick(doc, { now: () => t, watch: (f) => { check = f; return () => { check = null; }; } });
  const control = () => { const c = { matches: () => false, contains: (x) => x === c, disabled: false }; c.closest = () => c; return c; };
  const click = (target, x = 100, y = 200) => { const e = { target, timeStamp: t, clientX: x, clientY: y, isTrusted: true, stopped: false,
    preventDefault() {}, stopImmediatePropagation() { this.stopped = true; } }; on.click(e); return e; };
  const first = control(), second = control();
  under = first; t = 1000; click(first);
  t = 9000; under = second; check();                      // ...drawn eight seconds on, when the agent answered
  t = 9150; assert.ok(click(second).stopped, "a press a beat after it came there is the hand's, not his choice of it");
  t = 9500; assert.ok(click(second).stopped, "...within its first moment");
  t = 10100; assert.ok(!click(second).stopped, "a moment later it is his to press");
  // ...one that comes alive there (greyed while the agent thought) is new from then
  const third = control(); third.disabled = true; under = third; t = 20000; check(); click(second);
  t = 26000; third.disabled = false; check();
  t = 26200; assert.ok(click(third).stopped, "lit under the pointer a beat ago");
  // ...and a hand that moved off the spot is a new press wherever it lands
  t = 40000; click(first); under = second; t = 41000; check(); on.pointermove({ clientX: 300, clientY: 200 });
  t = 41100; assert.ok(!click(second, 300, 200).stopped);
});

// THE HYDROGEN WALK, 2026-11-19: Send on Gail's letter, and the next letter's card was drawn in the same element - its Send one button at
// 477,702 then 477,703 - and the second press of his double-click sent Erin's letter. The card a control presses is part of what it is
test("the next card drawn in the same button takes no press for its first moment: one double-click never sends two letters", () => {
  const on = {}; let t = 0, check = null, card = "11";
  const button = { matches: () => false, contains: (x) => x === button, disabled: false, closest: (sel) => (sel === "[data-tq-review]" ? { getAttribute: () => card } : button) };
  const doc = { addEventListener: (k, f) => { on[k] = f; }, removeEventListener: (k) => { delete on[k]; }, elementFromPoint: () => button };
  installSecondClick(doc, { now: () => t, watch: (f) => { check = f; return () => { check = null; }; } });
  const click = (x = 477, y = 702) => { const e = { target: button, timeStamp: t, clientX: x, clientY: y, isTrusted: true, stopped: false,
    preventDefault() {}, stopImmediatePropagation() { this.stopped = true; } }; on.click(e); return e; };
  t = 1000; assert.ok(!click().stopped, "his Send on Gail's letter");
  t = 1700; card = "12"; check();                          // ...Erin's card, drawn in the same button
  t = 1900; assert.ok(click(477, 703).stopped, "the double-click's second press never sends the letter that just came");
  t = 2800; assert.ok(!click(477, 703).stopped, "a moment later it is his to press");
});
