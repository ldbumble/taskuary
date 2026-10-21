import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { usedBy } from "../src/connectorUses.js";

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

test("the line sits on the card beside Remove, and Remove asks nothing new", () => {
  const cv = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");
  const rc = cv.slice(cv.indexOf("function RemoveConnection("), cv.indexOf("\nfunction ", cv.indexOf("function RemoveConnection(") + 10));
  assert.match(rc, /api\.get\(`\/api\/connectors\/\$\{conn\.ConnectorId\}\/uses`\)/);
  assert.match(rc, /const line = usedBy\(uses\);/);
  assert.match(rc, /\{line && <Typography data-tq-used-by="" variant="caption"[^>]*>\{line\}<\/Typography>\}/);
  assert.match(rc, /Remove connection<\/Button>\s+\{line && <Typography data-tq-used-by=""/, "beside the button, on its row");
  assert.ok((rc.match(/<ConfirmDelete|window\.confirm|<Dialog/g) || []).length <= 1, "no question added to Remove");
});
