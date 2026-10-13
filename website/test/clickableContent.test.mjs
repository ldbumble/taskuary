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

test("Hub topic rows are keyboard-operable buttons", () => {
  const hub = read("HubView.jsx");

  assert.ok(hub.includes('component="button"'));
  assert.ok(hub.includes('type="button"'));
  assert.ok(hub.includes('aria-current={topic === t.Topic ? "true" : undefined}'));
  assert.ok(hub.includes('onClick={() => setTopic(t.Topic)}'));
});

test("Settings help links are keyboard-operable buttons", () => {
  const settings = read("SettingsView.jsx");

  assert.ok(settings.includes('component="button"'));
  assert.ok(settings.includes('type="button"'));
  assert.ok(settings.includes('onClick={() => setHelp(SECTION_HELP.audit)}'));
});

test("LEARNED.md view switch uses accessible buttons", () => {
  const docs = read("DocsView.jsx");

  assert.ok(docs.includes('component="button"'));
  assert.ok(docs.includes('type="button"'));
  assert.ok(docs.includes("aria-pressed={view === k}"));
  assert.ok(docs.includes("onClick={() => setView(k)}"));
});

test("pasted screenshot thumbnails offer Remove as a real button", () => {
  // Each pasted thumbnail carries a × to remove it; it must take keyboard
  // focus and announce itself (#139). Anchor on onDrop: other Boxes exist.
  const source = read("ui.jsx");
  const remove = source.match(
    /<Box component="(\w+)"((?:(?!<Box)[\s\S])*?onDrop\(im\.id\)(?:(?!<Box)[\s\S])*?)>×<\/Box>/
  );
  assert.ok(remove, "Remove control exists in ui.jsx PromptThumbs");
  assert.equal(remove[1], "button");
  assert.match(remove[2], /type="button"/);
  assert.match(remove[2], /aria-label="Remove this image"/);
  assert.match(remove[2], /border: 0/);
});

test("re-check CI in the PR status line is a real button", () => {
  // "re-check CI" was a clickable span, so it could not be reached with Tab and its
  // busy state was signalled by colour alone (#158). Anchor on act("ci"): ui.jsx
  // holds many other Box components.
  const source = read("ui.jsx");
  const recheck = source.match(
    /<Box component="(\w+)"((?:(?!<Box)[\s\S])*?act\("ci"\)(?:(?!<Box)[\s\S])*?)>\s*\{busy === "ci"/
  );
  assert.ok(recheck, "re-check CI control exists in ui.jsx");
  assert.equal(recheck[1], "button");
  assert.match(recheck[2], /type="button"/);
  assert.match(recheck[2], /disabled=\{!!busy\}/);
  assert.match(recheck[2], /border: 0/);
  assert.match(source, /\{busy === "ci" \? "Checking CI…" : "re-check CI"\}/);
});
