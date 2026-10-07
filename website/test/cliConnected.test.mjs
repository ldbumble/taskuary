// A CLI ON THIS COMPUTER IS NOT A CONNECTED ONE, AND THE CARD SAYS WHICH (the owner, 2026-10-07: "it should not be installed
// automatically unless you say detect it.. and you should be able to disconnect them from the app"). A found CLI carried the
// same command line and buttons as a connected one, so it read as set up without asking, and a disconnected one as back again.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/AgentsPanel.jsx", import.meta.url), "utf8");

test("every card says Connected or Not connected", () => {
  assert.match(src, /label=\{cli\.configured \? "Connected" : "Not connected"\}/);
});

test("only a connected card shows its command; the rest offer Connect", () => {
  assert.match(src, /\{cli\.configured\s*\? <Typography sx=\{\{ \.\.\.mono/);
  assert.match(src, /cli\.installed && <Button[^>]*onClick=\{\(\) => connect\(cli\)\}/);
});

test("a connected card disconnects, and the dialog says it can be undone", () => {
  assert.match(src, /setConfirmDel\(cli\.name\)\}>Disconnect<\/Button>/);
  assert.match(src, /confirmLabel="Disconnect" undoable/);
  assert.doesNotMatch(src, /Set it up connects it again/);
});
