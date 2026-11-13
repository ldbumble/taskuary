// What a chat shows the owner (shownPages.js): a page runs with no network, a CSV reads as a table, and each item sits under
// the answer that made it (the owner, 2026-10-09: "only if the agent thinks it's a good way to understand things").
import test from "node:test";
import assert from "node:assert/strict";
import { CSP, csvRows, fitSvg, lockDown, placeShown } from "../src/shownPages.js";

// A WIDE PICTURE FITS ITS FRAME (the stress test, 2026-11-02): a 1600-wide SVG drew at its own width and the preview scrolled sideways
test("an SVG previews at the frame's width: shrunk to fit, its height following, with no sideways scroll", () => {
  const out = fitSvg(`<?xml version="1.0"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "x.dtd">\n<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="400"><rect width="1600" height="400"/></svg>`);
  assert.match(out, /svg\s*\{[^}]*max-width:\s*100%[^}]*height:\s*auto/);
  assert.match(out, /overflow-x:\s*hidden/);
  assert.match(out, /<svg viewBox="0 0 1600 400"/, "a fixed size scales only with a viewBox");
  assert.doesNotMatch(out, /<\?xml|DTD SVG/i, "the file's own prolog is not the page's");
  assert.match(lockDown(out), /^<!doctype html><meta http-equiv="Content-Security-Policy"/i, "standards mode, and the no-network policy still first");
  assert.match(fitSvg(`<svg viewBox="0 0 10 5" width="1000px" height="500px"></svg>`), /<svg viewBox="0 0 10 5" width/, "its own viewBox is kept");
});

test("a page gets the no-network policy first, after its doctype so it keeps standards mode", () => {
  const out = lockDown("<!DOCTYPE html><html><head><script>fetch('http://127.0.0.1:7999/api/tasks')</script>");
  assert.match(out, /^<!DOCTYPE html><meta http-equiv="Content-Security-Policy"/);
  assert.match(lockDown("<div>hi</div>"), /^<meta http-equiv="Content-Security-Policy"[^>]*><div>hi<\/div>$/);
  assert.match(CSP, /connect-src 'none'/);
  assert.match(CSP, /form-action 'none'/);
  assert.doesNotMatch(CSP, /127\.0\.0\.1|localhost|connect-src [^;]*https/);
});

test("a CSV reads as rows, quotes and all", () => {
  assert.deepEqual(csvRows('Category,August\r\nSupplies,"$78,400"\n"Say ""hi""",1\n'),
    [["Category", "August"], ["Supplies", "$78,400"], ['Say "hi"', "1"]]);
});

// ...and nothing is pinned at the chat's foot (the owner, 2026-11-13): one no answer in the thread holds is not drawn in the chat at all
test("each item sits under the answer that made it; one whose answer is not in the thread is drawn nowhere in the chat", () => {
  const msgs = [{ id: "comment-1", role: "user" }, { id: "comment-2", role: "assistant" }];
  const got = placeShown([{ id: 7, after: "comment-2" }, { id: 8, after: "comment-9" }, { id: 9, after: null }], msgs);
  assert.deepEqual(got, { by: { "comment-2": [{ id: 7, after: "comment-2" }] } });
});
