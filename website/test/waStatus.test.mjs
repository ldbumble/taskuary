// THE WHATSAPP CARD TELLS THE TRUTH (2026-10-23): it said "On — polling on schedule and via Sync now." from its switch while the
// bridge turned chats away, never heard a 1:1 by LID and failed its contact sync every ten minutes. The words are the server's
// (messengers.wa_status_line - tests/test_messengers.py); this pins what the card draws for each state, and where.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { waLine } from "../src/waStatus.js";

const src = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");

test("connected: the server's short words, and the turned-away count apart from them so it can be a link", () => {
  const st = { connected: true, bridge: true, parts: ["Connected", "2 chats", "last message 40 min ago"], turned_away: 12, fix: "" };
  assert.deepEqual(waLine(st), { parts: ["Connected", "2 chats", "last message 40 min ago"], away: 12, fix: "" });
  assert.equal(waLine({ ...st, turned_away: 0 }).away, 0);
});

test("not connected says so and offers Restart bridge; logged out offers Pair again; a failing contact sync offers Pair again", () => {
  assert.deepEqual(waLine({ connected: false, bridge: false, node: true, manager: { phase: "idle" } }), { parts: ["Not connected"], away: 0, fix: "restart" });
  assert.deepEqual(waLine({ connected: false, bridge: true, parts: ["Not connected"], fix: "restart", turned_away: 4 }),
    { parts: ["Not connected"], away: 0, fix: "restart" }, "nothing is turned away by a bridge that is not connected");
  assert.deepEqual(waLine({ connected: false, bridge: true, logged_out: true, parts: ["Logged out"], fix: "pair" }).fix, "pair");
  assert.equal(waLine({ connected: true, bridge: true, parts: ["Connected", "contact names not syncing"], fix: "pair" }).fix, "pair");
});

test("no button while the bridge is still starting or Node is missing - the pairing box says what to do there", () => {
  assert.equal(waLine({ bridge: false, node: true, manager: { phase: "starting" } }).fix, "");
  assert.equal(waLine({ bridge: false, node: false }).fix, "");
  assert.equal(waLine(null), null);
  assert.equal(waLine({ unreachable: true }), null);
});

test("an older bridge without the new fields still reads Connected, not the switch's sentence", () => {
  assert.deepEqual(waLine({ connected: true, bridge: true }), { parts: ["Connected"], away: 0, fix: "" });
});

test("the card draws the line where the switch's sentence was, the count opens the picker, and the fix is a button", () => {
  const line = src.slice(src.indexOf("const WaStatusLine = "), src.indexOf("const TestLine = "));
  assert.match(line, /line\.parts\.join\(" · "\)/);
  assert.match(line, /data-tq-wa-turned-away="" onClick=\{onTurnedAway\}/);
  assert.match(line, /fix === "pair" \? pairAgain\(cid\) : restartBridge\(cid\)/);
  assert.match(src, /conn\.Active && conn\.Type === "whatsapp" && waSt \? <WaStatusLine st=\{waSt\} cid=\{conn\.ConnectorId\} onTurnedAway=\{openPicker\} \/>/);
  assert.match(src, /<WaPair conn=\{conn\} reload=\{reload\} onStatus=\{setWaSt\} onTurnedAway=\{openPicker\} \/>/);
  assert.match(src, /const openPicker = \(\) => \{ if \(m\.srcLabel\) setStep\(2\); \};/);
});
