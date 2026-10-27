import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

// A PRESS THAT FAILS SAYS SO WHERE IT WAS PRESSED (the UI audit, 2026-10-21): Re-plan, a step's Send to agent, the Wall's x and Plan it with no AI each spun or did nothing, with no word anywhere
const src = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const body = (text, head) => { const i = text.indexOf(head); assert.ok(i >= 0, `${head} is there`); return text.slice(i, text.indexOf("\n  };", i)); };

test("a goal step that does not start, and a Re-plan that cannot or does not run, say so under the steps", () => {
  const page = src("TaskPage.jsx");
  const start = body(page, "const start = async (s) => {");
  assert.match(start, /try \{[^\n]*steps\/\$\{s\.id\}\/start/);
  assert.match(start, /catch \(e\) \{ setStepErr\(/);
  const replan = body(page, "const replan = async () => {");
  assert.match(replan, /caps\.ai === false\) \{ setStepErr\("No AI is connected/);
  assert.match(replan, /catch \(e\) \{ setReplanning\(false\); setStepErr\(/);
});

test("the Wall's close-session x says a refused close on the pane", () => {
  const close = body(src("WallView.jsx"), "const closeSession = async (c) => {");
  assert.match(close, /try \{ await api\.delete\(`\/api\/terminals\/\$\{c\.sid\}`\); \}/);
  assert.match(close, /catch \(e\) \{ setWrapErrors\(/);
});

test("New > Set a goal > Plan it promises no steps when no AI is connected", () => {
  const sheet = src("NewSheet.jsx");
  assert.match(sheet, /const noAi = useCapabilities\(\)\.ai === false;/);
  assert.match(sheet, /if \(plan && !noAi\) api\.post/);
  assert.match(sheet, /noAi \? "on your rail\. No AI is connected, so nothing can plan the steps/);
});
