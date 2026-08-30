import test from "node:test";
import assert from "node:assert/strict";
import { DEFAULT_RATIO, clampRatio, fitFrame, keyMessage, layoutFor, mouseMessage, parseMessage, ratioFromPointer,
  shortUrl, toPage, wheelMessage } from "../src/browserSplit.js";

test("the split stays between a third and four fifths, and defaults when unset", () => {
  assert.equal(clampRatio(0.58), 0.58);
  assert.equal(clampRatio(0.1), 0.3);
  assert.equal(clampRatio(0.95), 0.8);
  assert.equal(clampRatio(NaN), DEFAULT_RATIO);
});

test("dragging the handle sets the browser's share from the pointer's place across the slot", () => {
  assert.equal(ratioFromPointer(400, 0, 1000), 0.6);        // pointer at 40%: terminal 40, browser 60
  assert.equal(ratioFromPointer(950, 0, 1000), 0.3);        // past the minimum: pinned
  assert.equal(ratioFromPointer(100, 0, 0), DEFAULT_RATIO);
});

test("a frame is letterboxed whole into its box, never cropped or stretched", () => {
  assert.deepEqual(fitFrame(1280, 720, 640, 640), { x: 0, y: 140, w: 640, h: 360, scale: 0.5 });
  assert.deepEqual(fitFrame(1280, 720, 1000, 360), { x: 180, y: 0, w: 640, h: 360, scale: 0.5 });
  assert.equal(fitFrame(0, 0, 100, 100).scale, 0);
});

test("a pointer on the canvas maps back to page pixels, and the margin is nowhere", () => {
  const fit = fitFrame(1280, 720, 640, 640);
  assert.deepEqual(toPage(320, 320, fit), { x: 640, y: 360 });
  assert.equal(toPage(10, 10, fit), null);                  // on the letterbox above the page
  assert.equal(toPage(10, 10, null), null);
});

test("mouse and wheel events become CDP input at page coordinates", () => {
  const fit = fitFrame(1280, 720, 640, 640);
  assert.deepEqual(mouseMessage("mousedown", { offsetX: 320, offsetY: 320, button: 0 }, fit),
    { type: "input_mouse", eventType: "mousePressed", x: 640, y: 360, button: "left", clickCount: 1, modifiers: 0 });
  assert.equal(mouseMessage("mousemove", { offsetX: 320, offsetY: 320, button: 0 }, fit).clickCount, 0);
  assert.equal(mouseMessage("mousedown", { offsetX: 1, offsetY: 1, button: 0 }, fit), null);
  assert.equal(mouseMessage("dblclick", { offsetX: 320, offsetY: 320, button: 0 }, fit), null);
  const w = wheelMessage({ offsetX: 320, offsetY: 320, deltaY: 120, shiftKey: true }, fit);
  assert.equal(w.eventType, "mouseWheel"); assert.equal(w.deltaY, 120); assert.equal(w.modifiers, 8);
});

test("keystrokes carry text for printable keys and Enter, none for chords and specials", () => {
  assert.deepEqual(keyMessage("keydown", { key: "a", code: "KeyA" }),
    { type: "input_keyboard", eventType: "keyDown", key: "a", code: "KeyA", modifiers: 0, text: "a" });
  assert.equal(keyMessage("keydown", { key: "a", code: "KeyA", ctrlKey: true }).text, undefined);
  assert.equal(keyMessage("keydown", { key: "Enter", code: "Enter" }).text, "\r");
  assert.equal(keyMessage("keydown", { key: "Tab", code: "Tab" }).eventType, "rawKeyDown");
  assert.equal(keyMessage("keyup", { key: "a", code: "KeyA" }).eventType, "keyUp");
  assert.equal(keyMessage("keypress", { key: "a", code: "KeyA" }), null);
});

test("frames parse into something drawable; other messages pass through; junk is dropped", () => {
  const f = parseMessage(JSON.stringify({ type: "frame", seq: 3, data: "AAAA", metadata: { deviceWidth: 800, deviceHeight: 600, timestamp: 5 } }));
  assert.deepEqual(f, { type: "frame", seq: 3, src: "data:image/jpeg;base64,AAAA", w: 800, h: 600, at: 5 });
  assert.deepEqual(parseMessage('{"type":"url","url":"https://a.test/"}'), { type: "url", url: "https://a.test/" });
  assert.equal(parseMessage("not json"), null);
  assert.equal(parseMessage("42"), null);
});

test("urls are shown without scheme, cut in the middle when long", () => {
  assert.equal(shortUrl("https://login.pointclickcare.com/home/userLogin.xhtml"), "login.pointclickcare.com/home/userLogin.xhtml");
  assert.equal(shortUrl("https://a.test/"), "a.test");
  assert.equal(shortUrl(""), "");
  const long = shortUrl(`https://a.test/${"x".repeat(200)}`, 40);
  assert.ok(long.length <= 41 && long.includes("…"));
});

test("the slot decides: no browser is nothing, a narrow slot is a chip, otherwise the split unless folded", () => {
  assert.equal(layoutFor(1200, false, false), "none");
  assert.equal(layoutFor(500, true, false), "chip");
  assert.equal(layoutFor(1200, true, false), "split");
  assert.equal(layoutFor(1200, true, true), "folded");
});
