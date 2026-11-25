// A write to what an AI or a source is moves setup, and every view reading which AI answers reads it again (walk 19: the AI card came back on,
// and the top bar still said "Setup: pick your AI" over a greyed AI pill while the AI answered). Invented world.
import assert from "node:assert/strict";
import test from "node:test";
import { movesSetup, noteSetup, SETUP_CHANGED } from "../src/wrote.js";

test("switching an AI card, a setting or a setup step moves setup; a read or any other write does not", () => {
  assert.equal(movesSetup({ method: "post", url: "/api/connectors" }), true);
  assert.equal(movesSetup({ method: "patch", url: "/api/settings" }), true);
  assert.equal(movesSetup({ method: "post", url: "/api/setup/first-run/choose" }), true);
  assert.equal(movesSetup({ method: "get", url: "/api/connectors" }), false);
  assert.equal(movesSetup({ method: "post", url: "/api/tasks/4/send" }), false);
  assert.equal(movesSetup({ method: "post", url: "/api/connectorsX" }), false);
});

test("the move is said once, as the event the setup chip, the AI pill and the chat listen for", () => {
  const heard = [];
  globalThis.window = { dispatchEvent: (e) => heard.push(e.type) };
  noteSetup({ method: "post", url: "/api/connectors" }); noteSetup({ method: "get", url: "/api/connectors" });
  assert.deepEqual(heard, [SETUP_CHANGED]);
  assert.equal(SETUP_CHANGED, "tq-setup-changed");
  delete globalThis.window;
});
