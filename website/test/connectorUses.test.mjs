import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { removeWords, usedBy } from "../src/connectorUses.js";

// #238: what leans on a connection is said on its card beside Remove, before the press - not in a dialog after it
test("one of a kind is named, several are counted, in the server's order", () => {
  assert.equal(usedBy([{ kind: "workflow", names: ["Month close", "Invoice run"] }, { kind: "report", names: ["Morning"] }]),
    "Used by: 2 workflows, the Morning report");
  assert.equal(usedBy([{ kind: "report", names: ["Daily sales report"] }]), "Used by: the Daily sales report", "the kind is not said twice");
  assert.equal(usedBy([{ kind: "brain", names: ["Triage brain"] }, { kind: "card", names: ["Teams"] }]), "Used by: the Triage brain, the Teams card");
  assert.equal(usedBy([{ kind: "brain", names: ["Triage brain", "report judge"] }]), "Used by: 2 AI brains");
});

test("drafts and sources are counted, never named", () => {
  assert.equal(usedBy([{ kind: "draft", names: [""] }]), "Used by: 1 reply draft waiting");
  assert.equal(usedBy([{ kind: "draft", names: ["", ""] }, { kind: "source", names: ["alex@northwind.example"] }]),
    "Used by: 2 reply drafts waiting, 1 source it reads");
  assert.equal(usedBy([{ kind: "report", names: [""] }]), "Used by: 1 report", "a report with no title is counted");
});

test("nothing leaning says nothing", () => {
  for (const x of [[], null, undefined, [{ kind: "report", names: [] }]]) assert.equal(usedBy(x), "");
});

test("the line sits on the card beside Remove, and Remove asks once", () => {
  const cv = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");
  const rc = cv.slice(cv.indexOf("function RemoveConnection("), cv.indexOf("\nfunction ", cv.indexOf("function RemoveConnection(") + 10));
  // ...the read and the press are useRemove's, shared with the card's face (CardRemove, the owner 2026-11-05)
  const ur = cv.slice(cv.indexOf("function useRemove("), cv.indexOf("function RemoveConnection("));
  assert.match(ur, /api\.get\(`\/api\/connectors\/\$\{conn\.ConnectorId\}\/uses`\)/);
  assert.match(ur, /words: removeWords\(conn, channel, uses\)/);
  assert.match(ur, /after\?\.\(\); await reload\?\.\(\);/);
  assert.match(rc, /useRemove\(conn, channel, reload, onBack\)/);
  assert.match(rc, /const line = usedBy\(uses\);/);
  assert.match(rc, /\{line && <Typography data-tq-used-by="" variant="caption"[^>]*>\{line\}<\/Typography>\}/);
  assert.match(rc, /Remove connection<\/Button>\s+\{line && <Typography data-tq-used-by=""/, "beside the button, on its row");
  // ONE PRESS, ONE QUESTION (the owner, 2026-11-05), and on yes the page is back on the list
  assert.equal((rc.match(/<ConfirmDelete|window\.confirm|<Dialog/g) || []).length, 1, "one question");
  assert.match(rc, /<ConfirmDelete open=\{asking\} title=\{words\.title\} consequence=\{words\.text\} confirmLabel="Remove" undoable/);
  // ...and the same one press, one question on the card's face, the card's own press never firing under it
  const cr = cv.slice(cv.indexOf("function CardRemove("), cv.indexOf("\n/* ── Apple Messages"));
  assert.equal((cr.match(/<ConfirmDelete|window\.confirm|<Dialog/g) || []).length, 1, "one question on the face too");
  assert.match(cr, /onClick=\{stop\} onKeyDown=\{stop\}/);
  assert.match(cv, /\{c\.remove && <CardRemove \{\.\.\.c\.remove\} \/>\}/);
});

test("the question names the card, what stays, what goes and what stops with it", () => {
  const rows = [{ kind: "report", names: ["AP ageing"] }, { kind: "draft", names: ["", ""] }];
  const w = removeWords({ Name: "Work mail", Type: "imap" }, "email", rows);
  assert.equal(w.title, "Remove Work mail?");
  assert.equal(w.text, "Its mail stays in Taskuary. Its sign-in and settings are wiped and it stops reading. "
    + "Still using it, and stopping with it: the AP ageing report, 2 reply drafts waiting. Undo on the list brings it back for ten minutes.");
  assert.equal(removeWords({ Name: "Claude key", Type: "anthropic" }, "ai", []).text,
    "Its sign-in and settings are wiped. Undo on the list brings it back for ten minutes.");
  assert.match(removeWords({ Name: "Team chat", Type: "slack" }, "slack", null).text, /^What it brought in stays in Taskuary\. .* stops reading\./);
});
