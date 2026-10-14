import test from "node:test";
import assert from "node:assert/strict";
import { issueBody, issueUrl, fullReport } from "../src/bugReport.js";

const d = { title: "Save fails on the board", explanation: "Pressing Save showed a red banner.", where: "Board screen", error: "ValueError: bad thing",
  env: "Taskuary 1.2.3 (pip) · Windows 11 · Python 3.12", log: "line one\nline two", fingerprint: "abc123" };
const NEW = "https://github.com/ldbumble/taskuary/issues/new";

test("the body has every section of the template, in order", () => {
  const b = issueBody(d), at = ["### What happened", "### Where", "### Error", "### Environment", "<details><summary>Log lines</summary>", "</details>", "fingerprint: abc123"].map((s) => b.indexOf(s));
  assert.ok(at.every((i) => i >= 0), b); assert.deepEqual(at, [...at].sort((a, b) => a - b));
  assert.ok(b.includes("Pressing Save showed a red banner.") && b.includes("line two"));
});

test("the link opens a new issue labelled bug, from exactly the given text", () => {
  const { url, cut } = issueUrl(d.title, issueBody(d)), p = new URL(url).searchParams;
  assert.ok(url.startsWith(NEW + "?")); assert.equal(cut, false);
  assert.equal(p.get("labels"), "bug"); assert.equal(p.get("title"), d.title); assert.equal(p.get("body"), issueBody(d));
  assert.notEqual(issueUrl("Edited title", issueBody(d)).url, url);
});

test("a 20 KB log is cut first, keeping title and explanation", () => {
  const b = issueBody({ ...d, log: "x".repeat(20000) }), { url, cut } = issueUrl(d.title, b), p = new URL(url).searchParams;
  assert.ok(cut && url.length <= 7500);
  assert.equal(p.get("title"), d.title); assert.ok(p.get("body").includes(d.explanation)); assert.ok(!p.get("body").includes("xxxx"));
});

test("a long error goes next, with a note, and the whole report is still what gets copied", () => {
  const b = issueBody({ ...d, error: "é".repeat(5000) }), { url, cut } = issueUrl(d.title, b), body = new URL(url).searchParams.get("body");
  assert.ok(cut && url.length <= 7500 && body.includes("(cut - the full report was copied to your clipboard)") && body.includes(d.explanation));
  assert.ok(fullReport(d.title, b).includes("é".repeat(5000)));
});

test("a huge explanation loses its tail, never the title", () => {
  const b = issueBody({ ...d, explanation: "word ".repeat(3000) }), { url, cut } = issueUrl(d.title, b), p = new URL(url).searchParams;
  assert.ok(cut && url.length <= 7500); assert.equal(p.get("title"), d.title); assert.ok(p.get("body").includes("(cut - the full report"));
});
