import test from "node:test";
import assert from "node:assert/strict";
import { canRevealTerminal, changedTerminalSize, usableTerminalBox } from "../src/terminalSizing.js";

test("unchanged terminal geometry does not produce another PTY resize", () => {
  assert.equal(changedTerminalSize("32x110", 32, 110), null);
  assert.equal(changedTerminalSize("32x110", 33, 110), "33x110");
  assert.equal(changedTerminalSize("32x110", 32, 111), "32x111");
});

test("hidden and half-laid-out panes never resize the PTY", () => {
  assert.equal(usableTerminalBox(0, 0), false);
  assert.equal(usableTerminalBox(900, 0), false);
  assert.equal(usableTerminalBox(79, 500), false);
  assert.equal(usableTerminalBox(900, 500), true);
});

test("the curtain waits for both the server repaint barrier and every xterm write", () => {
  assert.equal(canRevealTerminal(false, 0), false);
  assert.equal(canRevealTerminal(true, 2), false);
  assert.equal(canRevealTerminal(true, 0), true);
});
