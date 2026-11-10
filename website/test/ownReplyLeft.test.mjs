import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// THE OWNER'S OWN REPLY FROM THEIR PHONE (the owner, 2026-11-08: "it should be left side thing but written as you responded"): it stands among
// the other side's lines in time order, on the LEFT, headed "You · on WhatsApp · 5:20 PM" - never dropped from the stream, never a prompt
test("an own row is drawn among the arrivals, on the left, headed You · on WhatsApp", () => {
  const ws = read("GeneralWorkspace.jsx"), arrived = ws.slice(ws.indexOf("const ON_WORD = "), ws.indexOf("// what a check-back come due"));
  assert.match(arrived, /const Arrived = \(\{ mail \}\) => mail\.map\(/, "own rows are no longer filtered out");
  assert.match(arrived, /const ON_WORD = \{ email: "by email", whatsapp: "on WhatsApp",/);
  assert.match(arrived, /const headOf = \(x\) => x\.own \? \["You", ON_WORD\[String\(x\.channel \|\| ""\)\.toLowerCase\(\)\] \|\| "outside Taskuary"\]/);
  assert.match(arrived, /\{\[\.\.\.headOf\(x\), stamp\]\.filter\(Boolean\)\.join\(" · "\)\}/);
  assert.match(arrived, /\$\{x\.own \? " tq-aui-arrived-own" : ""\}`\} data-tq-chat-arrived=\{x\.own \? "own" : ""\}/);
  // ...a brief whose only mail is the owner's own reply draws it (its own words are Taskuary's, never drawn)
  assert.match(ws, /if \(brief && chat\) return mail\?\.length \? <><MessagePrimitive\.Root className="tq-aui-message tq-aui-brief"><Arrived mail=\{mail\} \/>/);
  // ...and on the left, where the arrivals beside it stand right
  const css = read("generalWorkspace.css");
  assert.match(css, /\.tq-aui-chat \.tq-aui-brief \{ justify-items: end; \}\r?\n\.tq-aui-chat \.tq-aui-arrived-own \{ justify-self: start;/);
});
