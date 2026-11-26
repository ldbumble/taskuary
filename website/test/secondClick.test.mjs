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

// THE BUTTON MOVED WHILE THE POINTER WAS DOWN (the owner, 2026-11-26: "most buttons on our app you have to click twice for it to go?"): the Ask
// box shut with words in it opens as the pointer goes down, its up-arrow rises a line, and the release lands 29px under it - the browser's
// click went to the box, the words stayed, and he pressed again
function moving() {
  const on = {}, w = { t: 0, under: null, check: null };
  class MouseEvent { constructor(type, o) { Object.assign(this, o, { type, isTrusted: false, stopped: false }); } preventDefault() {} stopImmediatePropagation() { this.stopped = true; } }
  const doc = { addEventListener: (k, f) => { on[k] = f; }, removeEventListener: (k) => { delete on[k]; }, elementFromPoint: () => w.under, defaultView: { MouseEvent } };
  installSecondClick(doc, { now: () => w.t, watch: (f) => { w.check = f; return () => { w.check = null; }; } });
  // `presses`: the clicks that reached it, as the page under this listener would hear them
  w.control = () => { const c = { matches: () => false, contains: (x) => x === c, disabled: false, isConnected: true, shown: true, presses: [], getClientRects: () => (c.shown ? [1] : []),
    dispatchEvent(e) { e.target = c; e.timeStamp = w.t; on.click(e); if (!e.stopped) c.presses.push([e.clientX, e.clientY]); } }; c.closest = () => c; return c; };
  w.bare = { matches: () => false, closest: () => null };          // the box's own middle, the page: nothing that takes a press
  const ev = (target, x, y) => ({ target, timeStamp: w.t, clientX: x, clientY: y, isTrusted: true, button: 0, stopped: false, preventDefault() {}, stopImmediatePropagation() { this.stopped = true; } });
  w.down = (target, x, y) => on.pointerdown(ev(target, x, y));
  // ...the browser's own click: on the button when the release was on it too (and then it presses it), else on what holds both ends
  w.click = (target, x, y) => { const e = ev(target, x, y); on.click(e); if (!e.stopped) target.presses?.push([x, y]); return e; };
  w.move = (x, y) => on.pointermove({ clientX: x, clientY: y });
  return w;
}

test("a press whose button moved from under the still pointer presses that button, once, where the hand made it", () => {
  const w = moving(), send = w.control();
  w.t = 1000; w.down(send, 1383, 850);
  w.t = 1090; const stray = w.click(w.bare, 1383, 850);
  assert.ok(stray.stopped, "the click the browser gave the box is not the page's");
  assert.deepEqual(send.presses, [[1383, 850]], "the up-arrow he pressed is pressed");
  // ...and a press that stayed on its button is the browser's own: nothing is added to it
  w.move(900, 300); w.t = 5000; w.down(send, 1383, 821); w.t = 5090;
  assert.ok(!w.click(send, 1384, 821).stopped);
  assert.equal(send.presses.length, 2, "one press, one click");
});

test("a hand that moved off before letting go cancels as before, and a button greyed, gone or hidden by the release is not pressed", () => {
  const w = moving(), b = w.control();
  w.t = 1000; w.down(b, 500, 400); w.t = 1300;
  assert.ok(!w.click(w.bare, 500, 420).stopped, "dragged off it: the browser's click stands");
  for (const gone of [{ disabled: true }, { isConnected: false }, { shown: false }]) {
    const c = w.control(); w.move(0, 0); w.t += 5000; w.down(c, 700, 400); Object.assign(c, gone); w.t += 90;
    assert.ok(!w.click(w.bare, 700, 400).stopped, JSON.stringify(gone));
    assert.equal(c.presses.length, 0, JSON.stringify(gone));
  }
  assert.equal(b.presses.length, 0);
  // ...a key's click, and the page's own click(), come with no pointer down: never moved to another button
  w.move(0, 0); w.t += 5000; w.down(b, 500, 400); w.t += 90; w.click(b, 500, 400);
  w.t += 5000; assert.ok(!w.click(w.bare, 500, 400).stopped);
  assert.equal(b.presses.length, 1);
});

test("a button that came under the still pointer a moment ago takes no press, moved or not: the next letter is never sent unread", () => {
  const w = moving(), first = w.control(), second = w.control();
  w.under = first; w.t = 1000; w.down(first, 477, 702); w.click(first, 477, 702);
  w.t = 9000; w.under = second; w.check();                 // ...the next card, drawn where his press landed
  w.t = 9200; w.down(second, 477, 702);
  w.under = w.bare; w.t = 9290;                            // ...and it moved while he held it
  assert.ok(w.click(w.bare, 477, 702).stopped);
  assert.equal(second.presses.length, 0, "not his choice of it");
  w.under = second; w.t = 10300; w.down(second, 477, 702); w.under = w.bare; w.t = 10390; w.click(w.bare, 477, 702);
  assert.equal(second.presses.length, 1, "a moment later it is his to press, and the press lands though it moved");
});
