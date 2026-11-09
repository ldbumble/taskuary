import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// A PRESS IS AN EVENT (the owner, 2026-11-09): "You changed its workstream." was drawn in a bubble under "You", as if typed
const ws = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
const src = ws.slice(ws.indexOf("export const pressLine"), ws.indexOf("// what a check-back come due"));
const pressLine = new Function(`${src.replace("export ", "")}; return pressLine;`)();

test("a press reads as an event line: its words, no stop, then the time", () => {
  assert.equal(pressLine("You changed its workstream.", "3:12 PM"), "You changed its workstream · 3:12 PM");
  assert.equal(pressLine("You set a reminder for 9:00 AM.", ""), "You set a reminder for 9:00 AM");
});

test("a press is drawn as the quiet event line, never the owner's bubble", () => {
  const user = ws.slice(ws.indexOf("const UserMessage = "), ws.indexOf("// what each answer published or showed"));
  const at = user.indexOf("if (press) return"), bubble = user.indexOf('tq-aui-user-bubble');
  assert.ok(at > 0 && at < bubble, "the press returns before any bubble is drawn");
  assert.match(user.slice(at, user.indexOf("\n", user.indexOf("</MessagePrimitive.Root>", at))), /tq-aui-press-line/);
  assert.doesNotMatch(user.slice(at, user.indexOf("</MessagePrimitive.Root>", at)), /tq-aui-user|PersonOutlineIcon/);
});

test("a typed line after a press still gets its own 'You' head", () => {
  assert.match(ws, /!p\.metadata\?\.custom\?\.brief && !p\.metadata\?\.custom\?\.press \?/);
});
