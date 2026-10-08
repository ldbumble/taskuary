// NEVER LEFT HANGING (the owner, 2026-10-08: "assistant is leaving user hanging. We need Next button on bottom at least and say hit next
// to continue"): a Next refused because the list moved said so in red, every card above had folded, and nothing was left to press.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");

test("with nothing on the table the row's floor is Next, and the chat says to press it", () => {
  assert.match(view, /const hanging = [^\n]*!onTable[^\n]*\(canAdvance \|\| !!err\)/);
  assert.match(view, /useVerbs\("floor", \[\{ id: "floor:next", group: "next", label: "Next"/);
  assert.match(view, /\{hanging && <Typography[^>]*data-tq-hanging="">Press <b>Next<\/b> below to continue\.<\/Typography>\}/);
});
