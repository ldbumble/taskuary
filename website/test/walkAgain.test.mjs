// THE END OF A WALK (the owner, 2026-10-22: "just have ... button on bottom on top of the prompt box"): the server's end chips lead with
// `walk` (concierge.surface), and the row by the prompt box runs it as the day card's own button - same words, same handler.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { label } from "../src/buttons.js";

const src = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");

test("the walk's again is the day card's button: one name in buttons.json, one handler", () => {
  assert.equal(label("walk"), "Walk me through my tasks");
  assert.match(src, /if \(c\.verb === "walk"\) \{ start\(null\); return; \}/, "the row's chip runs the opener's start");
  assert.match(src, /onClick=\{\(\) => \(counting \|\| walkOff \? setWalkQueued\(true\) : start\(null\)\)\}/);
  assert.match(src, /: btn\("walk"\)\}<\/button>/, "the opener says the same words, from buttons.json");
});
