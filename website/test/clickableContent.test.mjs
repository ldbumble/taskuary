import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("task and attachment actions use keyboard-operable buttons", () => {
  const wall = read("AgentWall.jsx");
  const attachments = read("Attachments.jsx");
  const taskPage = read("TaskPage.jsx");
  const learned = read("LearnedView.jsx");

  assert.match(wall, /<Typography component="button" type="button"[^>]+onClick=\{\(\) => onOpenTask\?\.\(n\.TaskId\)\}/);
  assert.match(attachments, /<Typography variant="caption" component="button" type="button"[^>]+onClick=\{fetchNow\}/);
  assert.match(attachments, /<Box key=\{a\.id\} component="button" type="button"[^>]+onClick=\{\(\) => setBig\(a\)\}/);
  assert.match(taskPage, /<Box component="button" type="button" onClick=\{\(\) => \{ const next = diffScope === "task" \? "checkout" : "task";/);
  assert.match(learned, /<Typography component="button" type="button" aria-expanded=\{looseOpen\} onClick=\{\(\) => setLooseOpen\(\(o\) => !o\)\}/);
});

test("a failed report run offers Try again as a real button, not a span", () => {
  // Reports shows "This run's details could not be loaded. Try again" when a
  // run's details fail to load; the retry must take keyboard focus (#142).
  // Anchor on setMissed: other Box components exist in the same file.
  const source = read("ReportsView.jsx");
  const retry = source.match(
    /<Box component="(\w+)"((?:(?!<Box)[\s\S])*?setMissed\(null\)(?:(?!<Box)[\s\S])*?)>Try again<\/Box>/
  );
  assert.ok(retry, "Try again control exists in ReportsView.jsx");
  assert.equal(retry[1], "button");
  assert.match(retry[2], /type="button"/);
  assert.match(retry[2], /border: 0/);
  assert.match(retry[2], /bgcolor: "transparent"/);
  assert.match(retry[2], /font: "inherit"/);
});

test("AI defaults navigation links are keyboard-operable buttons", () => {
  const aiDefaults = read("AiDefaults.jsx");
  assert.ok(aiDefaults.includes('<Typography component="button" type="button" variant="caption" onClick={() => onGo(slot.owner_link)}'));
  assert.ok(aiDefaults.includes('<Typography component="button" type="button" variant="body2" onClick={() => onGo("connectors")}'));
});
