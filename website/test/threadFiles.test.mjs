// EVERY FILE BELONGS TO ITS MESSAGE (the owner, 2026-10-20): a voice note was drawn loose under the Came from card, outside the
// thread, named by the bridge's hash. Each message's attachments ride under its own row; a voice note is called one.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { filesByMessage, rowText } from "../src/taskSources.js";

const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");
const att = fs.readFileSync(new URL("../src/Attachments.jsx", import.meta.url), "utf8");
const cameFrom = page.slice(page.indexOf('<Part label="Came from"'), page.indexOf("</Part>", page.indexOf('<Part label="Came from"')));
const rowsFn = page.slice(page.indexOf("function ConversationRows("), page.indexOf("// the repo is a filter like the others"));

test("the detail's attachments are grouped by the message they came in", () => {
  const by = filesByMessage([{ MessageId: 7, Name: "3EB0C431D5E6F7A8.ogg" }, { MessageId: 9, Name: "a.png" }, { MessageId: 7, Name: "b.pdf" }, { Name: "orphan" }]);
  assert.deepEqual([...by.keys()], [7, 9]);
  assert.equal(by.get(7).length, 2);
  assert.equal(filesByMessage(undefined).size, 0);
});

test("a condensed row reads the transcript, says Voice note for a bare one, and never the attachment placeholder", () => {
  const ogg = [{ MessageId: 1, Name: "3EB0C431D5E6F7A8.ogg", ContentType: "audio/ogg" }];
  assert.equal(rowText({ excerpt: "Running late, start without me. (🎤 voice note (9s) from WhatsApp, transcribed by Groq (Whisper))" }, ogg),
    "Running late, start without me.");
  assert.equal(rowText({ excerpt: "(no text - see the attachment)" }, ogg), "Voice note");
  assert.equal(rowText({ excerpt: "(no text - see the attachment)" }, [{ Name: "plan.pdf", ContentType: "application/pdf" }]), "1 attachment");
  assert.equal(rowText({ excerpt: "" }), "(no text)");
  assert.equal(rowText({ excerpt: "see the deck", Subject: "Deck" }, []), "see the deck");
});

test("nothing is drawn loose under the card: each row draws its own message's files", () => {
  assert.doesNotMatch(cameFrom, /<Attachments messageId=\{inbound\[0\]/, "the opener's files are not drawn outside the thread");
  assert.match(cameFrom, /files=\{sourceFiles\} fetchFor=\{fetchFor\}/);
  assert.match(page, /const sourceFiles = filesByMessage\(detail\?\.attachments\);/);
  assert.match(rowsFn, /open !== r\.m\.MessageId && \(files\.has\(r\.m\.MessageId\) \|\| fetchFor === r\.m\.MessageId\) && \(/);
  assert.match(rowsFn, /<Attachments messageId=\{r\.m\.MessageId\} canFetch=\{fetchFor === r\.m\.MessageId\} dense \/>/);
});

test("a voice note named by the bridge's hash is called a voice note; a named file keeps its name", () => {
  const src = att.slice(att.indexOf("const HASHED"), att.indexOf("const kb ="));
  const { clipName } = new Function(`${src.replace(/export /g, "")}; return { clipName };`)();
  assert.equal(clipName({ name: "3EB0C431D5E6F7A8B9C0.ogg" }), "Voice note");
  assert.equal(clipName({ name: "board-call.m4a" }), "board-call.m4a");
  assert.equal(clipName({}), "Voice note");
  assert.match(att, /noWrap title=\{a\.name\}>\{clipName\(a\)\}<\/Typography>/, "the stored name stays on hover");
});
