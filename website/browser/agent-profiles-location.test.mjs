import assert from "node:assert/strict";
import test from "node:test";
import { mkdir } from "node:fs/promises";
import { clickNav, startHarness } from "./harness.mjs";

async function clickText(page, text, selector = "button,p,div") {
  await page.waitForFunction(({ text, selector }) => [...document.querySelectorAll(selector)]
    .some((el) => el.textContent.trim() === text && el.getBoundingClientRect().height), {}, { text, selector });
  await page.evaluate(({ text, selector }) => [...document.querySelectorAll(selector)]
    .find((el) => el.textContent.trim() === text && el.getBoundingClientRect().height).click(), { text, selector });
}

test("CLI connections show tools; Docs owns named profiles and their settings", { timeout: 120000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  const writes = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const profiles = {
    coder: { cmd: "claude", args: ["-p"], kind: "coding", rules_doc: "coder", purpose: "Edit code" },
    codex: { cmd: "codex", args: ["exec"], kind: "coding", rules_doc: "coder", purpose: "Edit code" },
    researcher: { cmd: "claude", args: ["-p"], kind: "research", purpose: "Research public information" },
  };
  const clis = [
    { name: "claude", label: "Claude Code", cmd: "claude", args: ["-p"], installed: true, setup: "claude" },
    { name: "devin", label: "Devin CLI", cmd: "devin", args: ["-p"], installed: false, installable: true, install: "devin" },
    { name: "researcher", label: "Researcher", cmd: "claude", profile: "researcher", args: ["-p"] },
  ];
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    let data;
    if (path === "/api/agents") data = { config: profiles, models: {}, default: "coder",
      data: Object.entries(profiles).map(([Name, config]) => ({ Name, Config: JSON.stringify(config), installed: true })) };
    if (path === "/api/cli/detect") data = { data: clis };
    if (path === "/api/doc/researcher") data = { content: "# Researcher\nRead public sources and cite findings." };
    if (path === "/api/doc/scout") data = { content: "# Scout\nCompare vendors and cite public sources." };
    if (path.startsWith("/api/agents/") && request.method() === "PUT") {
      const name = decodeURIComponent(path.slice("/api/agents/".length));
      const update = JSON.parse(request.postData());
      writes.push({ name, update });
      profiles[name] = { ...profiles[name], ...update };
      data = { ok: true, rules_doc: update.rules_doc };
    }
    if (data) return request.respond({ status: 200, contentType: "application/json", body: JSON.stringify(data) });
    page.fixtureRequestGuard(request);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded" });
  await clickNav(page, "Connections");
  await page.waitForSelector('input[placeholder^="Search connectors"]');
  await page.type('input[placeholder^="Search connectors"]', "AI CLI agents");
  await clickText(page, "AI CLI agents", "p");
  await clickText(page, "Manage profiles in Docs", "button");
  await page.waitForFunction(() => document.body.innerText.includes("RESEARCHER.md"));
  assert.doesNotMatch(await page.evaluate(() => document.body.innerText), /CODEX\.md/);
  assert.match(await page.evaluate(() => document.body.innerText), /Used by coder, codex/);
  await clickText(page, "RESEARCHER.md", "p");
  await page.waitForFunction(() => [...document.querySelectorAll("textarea")].some((el) => el.value.includes("Read public sources")));
  await clickText(page, "Add profile", "button");
  await page.waitForSelector('[role="dialog"] input', { visible: true });
  assert.equal(await page.$eval('[role="dialog"]', (el) => {
    const box = el.getBoundingClientRect();
    return box.top >= 0 && box.bottom <= window.innerHeight && el.contains(document.activeElement);
  }), true, "Add opens a focused dialog in the viewport, even below a long profile list");
  await page.type('[role="dialog"] input', "scout");
  const fields = await page.$$('[role="dialog"] input');
  await fields[1].type("claude");
  await page.type('[role="dialog"] textarea', "Compare vendors and cite public sources.");
  await clickText(page, "Save", "button");
  await page.waitForFunction(() => !document.querySelector('[role="dialog"]'));
  assert.equal(writes[0].name, "scout");
  assert.equal(writes[0].update.cmd, "claude");
  assert.equal(writes[0].update.purpose, "Compare vendors and cite public sources.");
  assert.equal(writes[0].update.kind, "general");
  assert.equal(writes[0].update.triage_enabled, true);
  await page.waitForFunction(() => document.body.innerText.includes("SCOUT.md"));
  await clickText(page, "Manage profiles", "button");
  await page.waitForFunction(() => [...document.querySelectorAll(".MuiChip-label")].some((el) => el.textContent === "researcher"));
  await page.evaluate(() => {
    const chip = [...document.querySelectorAll(".MuiChip-label")].find((el) => el.textContent === "researcher");
    [...chip.parentElement.parentElement.querySelectorAll("button")].find((el) => el.textContent === "Edit").click();
  });
  await page.waitForFunction(() => document.body.innerText.includes("Edit profile · researcher"));
  const input = await page.$('[role="dialog"] input[value="claude"]');
  await input.focus();
  await page.keyboard.down("Control");
  await page.keyboard.press("KeyA");
  await page.keyboard.up("Control");
  await page.keyboard.press("Backspace");
  await input.type("research-wrapper");
  await clickText(page, "Save", "button");
  await page.waitForFunction(() => document.body.innerText.includes("research-wrapper"));
  assert.equal(writes.length, 2);
  assert.equal(writes[1].name, "researcher");
  assert.equal(writes[1].update.cmd, "research-wrapper");
  assert.equal(writes[1].update.purpose, "Research public information");
  assert.equal(writes[1].update.kind, "research");
  assert.equal(profiles.coder.cmd, "claude");
  await mkdir("../.codex-tmp", { recursive: true });
  await page.screenshot({ path: "../.codex-tmp/docs-profiles.png", fullPage: true });

  await clickNav(page, "Connections");
  await page.waitForSelector('input[placeholder^="Search connectors"]');
  await page.type('input[placeholder^="Search connectors"]', "AI CLI agents");
  await clickText(page, "AI CLI agents", "p");
  await page.waitForFunction(() => document.body.innerText.includes("Devin CLI"));
  const text = await page.evaluate(() => document.body.innerText);
  assert.match(text, /Claude Code/);
  assert.match(text, /Set it up/);
  assert.match(text, /Install/);
  assert.doesNotMatch(text, /researcher|Researcher|Who does the triage\?|Add profile|make default/);
  await page.screenshot({ path: "../.codex-tmp/cli-connections.png", fullPage: true });
  assert.deepEqual(errors, []);
  assert.deepEqual(page.fixtureEscapes, []);
});
