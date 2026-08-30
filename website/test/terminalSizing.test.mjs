import test from "node:test";
import assert from "node:assert/strict";
import { changedTerminalSize } from "../src/terminalSizing.js";

test("unchanged terminal geometry does not produce another PTY resize", () => {
  assert.equal(changedTerminalSize("32x110", 32, 110), null);
  assert.equal(changedTerminalSize("32x110", 33, 110), "33x110");
  assert.equal(changedTerminalSize("32x110", 32, 111), "32x111");
});
