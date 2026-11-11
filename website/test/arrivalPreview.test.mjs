import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

// THE ARRIVAL CARD LEADS WITH THE SENDER'S NEW WORDS (the owner, 2026-11-09: "preview of the email is the bottom of the email?? ... you can't see
// anything about the email"): the server sends `words` with the stamped banner, the quoted chain and the signature gone (general.mail_row,
// tests/test_mail_preview_new_words.py), and the card draws a mail's subject in bold over them.
const ws = readFileSync(new URL("../src/GeneralWorkspace.jsx", import.meta.url), "utf8");
const css = readFileSync(new URL("../src/generalWorkspace.css", import.meta.url), "utf8");
const body = /export const subjectOf = (\(x, prev\) => \{[\s\S]*?\n  return [^\n]*; \});/.exec(ws)[1];
const subjectOf = new Function(`return ${body}`)();

test("the subject rides over a mail's words, bold, and its whole words stay on hover", () => {
  assert.match(ws, /\{!!subjectOf\(x, all\[i - 1\]\) && <span className="tq-aui-arrived-subject" dir="auto">\{x\.subject\}<\/span>\}\r?\n\s*\{!!mailWords\(x\) && <ArrivedWords words=\{mailWords\(x\)\} \/>\}/);
  // ...its words read in place: a few lines, and one toggle only where they are cut (the owner, 2026-11-11)
  assert.match(ws, /<span ref=\{el\} className=\{`tq-aui-arrived-words\$\{open \? " tq-aui-arrived-open" : ""\}`\} dir="auto">\{words\}<\/span>/);
  assert.match(css, /\.tq-aui-arrived-subject \{ color: var\(--tq-text, #2b2925\); font-weight: 600;/);
});

test("the subject is said once a run, never over a chat line, the owner's own, or words that are only it", () => {
  const m = { subject: "Invoice for October", words: "Attached is the October invoice." };
  assert.equal(subjectOf(m, null), "Invoice for October");
  assert.equal(subjectOf({ ...m, subject: "RE: Invoice for October" }, m), "");
  assert.equal(subjectOf({ ...m, subject: "" }, null), "");
  assert.equal(subjectOf({ ...m, own: true }, null), "");
  assert.equal(subjectOf({ subject: "Fwd: Lunch?", words: "Lunch?" }, null), "");
});
