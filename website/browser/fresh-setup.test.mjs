// SETUP NEVER ASSUMES AN AI, on the rendered page (the owner, 2026-10-20: "every time someone is installing a fresh install of the
// .exe, the advisor says claude is installed, set it up?? first of all it was not, and stop assuming that ... It should let them
// choose the AIs"). A first start - not the demo - on a PATH with no AI tool, then with one fake CLI on it.
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile, chmod } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { startHarness } from "./harness.mjs";

const VENDORS = /claude|codex|gemini|chatgpt|openai|anthropic|copilot|qwen|cursor|devin|kimi|opencode|muse/i;

async function firstRun(harness) {
  const page = await harness.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-tq-firstrun="ai"] [data-tq-card^="cli-"]', { timeout: 45000 });
  await page.waitForFunction(() => /What AI do you have\?/.test(document.querySelector(".tq-next-txt")?.innerText || ""), { timeout: 20000 });
  const seen = await page.evaluate(() => ({
    line: document.querySelector(".tq-next-txt").innerText,
    lit: [...document.querySelectorAll("[data-tq-firstrun] [data-tq-setup-lit]")].map((e) => e.innerText),
    cards: Object.fromEntries([...document.querySelectorAll("[data-tq-card]")].map((e) => [e.getAttribute("data-tq-card"), e.innerText])),
  }));
  return { page, errors, ...seen };
}

test("a fresh install with no AI tool lights no AI, names none and calls none installed or connected", { timeout: 180000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const { line, lit, cards, errors } = await firstRun(harness);
  assert.doesNotMatch(line, VENDORS, `the Advisor line picks no vendor: ${line}`);
  assert.doesNotMatch(line, /installed|connected|set it up/i, line);
  assert.deepEqual(lit, [], "no card is lit - the person chooses");
  for (const [k, text] of Object.entries(cards)) assert.doesNotMatch(text, /Connected|On this computer|Installed/, `${k}: ${text}`);
  assert.ok(cards["cli-claude"] && cards["cli-codex"], "the coding tools are still offered, as choices");
  assert.deepEqual(errors, []);
});

// THE ADVISOR'S STRIP IS ONE LINE (the owner, 2026-10-20: it wrapped onto two lines - "never want that, it looks weird"): every strip
// is a .tq-next with its .tq-next-txt (setup's SetupLine, the canvas and a task page's AdvisorNext/AdviceNone), so the setup strip
// itself and a strip carrying Why? and a lit button are measured with a sentence far longer than either width
test("the Advisor's strip stays one line at 1366 and 390 px, its buttons whole, the sentence in its tooltip", { timeout: 180000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const { page, errors } = await firstRun(harness);
  const long = "Taskuary read every message in the folder you connected and found one that waits on you: the vendor invoice for the third quarter, which needs an approval before Friday so it goes out in this run, and two reminders about it.";
  for (const width of [1366, 390]) {
    await page.setViewport({ width, height: 900, deviceScaleFactor: 1 });
    const m = await page.evaluate((text) => {
      const setup = document.querySelector("[data-tq-setup-line] .tq-next-txt");
      setup.textContent = text;
      const strip = document.createElement("div"); strip.className = "tq-next"; strip.id = "one-line-probe";
      strip.innerHTML = `<div class="tq-next-txt">${text}</div><button type="button" class="tq-next-why">Why?</button><button type="button" class="tq-next-go">Approve</button>`;
      setup.closest(".tq-next").after(strip);
      const one = (el) => { const lh = parseFloat(getComputedStyle(el).lineHeight); return { h: el.getBoundingClientRect().height, lh }; };
      const btn = (sel) => { const b = strip.querySelector(sel).getBoundingClientRect(); return b.width > 20 && b.right <= strip.getBoundingClientRect().right + 1; };
      const out = { setup: one(setup), probe: one(strip.querySelector(".tq-next-txt")), why: btn(".tq-next-why"), go: btn(".tq-next-go"),
        pageWide: document.documentElement.scrollWidth <= window.innerWidth + 1 };
      setup.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
      out.title = setup.title;
      strip.remove();
      return out;
    }, long);
    for (const k of ["setup", "probe"]) assert.ok(m[k].h <= m[k].lh * 1.5, `${width}px ${k}: ${m[k].h}px tall for a ${m[k].lh}px line`);
    assert.ok(m.why && m.go, `${width}px: Why? and the lit button stay whole on the strip`);
    assert.equal(m.title, long, "the whole sentence is its tooltip");
  }
  assert.deepEqual(errors, []);
});

test("one CLI genuinely on PATH is said to be found - as one choice, never lit, never connected", { timeout: 180000 }, async (t) => {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-cli-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const fake = path.join(bin, win ? "claude.cmd" : "claude");
  await writeFile(fake, win ? "@echo ok\r\n" : "#!/bin/sh\necho ok\n"); if (!win) await chmod(fake, 0o755);
  const harness = await startHarness({ fresh: true, bin }); t.after(() => harness.close());
  const { line, lit, cards, errors } = await firstRun(harness);
  assert.match(line, /Claude is on this computer - pick it if that is the one you use, or pick any other/, line);
  assert.doesNotMatch(line, /connected|set it up/i, line);
  assert.deepEqual(lit, [], "found is offered, not picked");
  assert.match(cards["cli-claude"], /On this computer - pick it to check it works/);
  assert.doesNotMatch(cards["cli-codex"], /On this computer|Connected/, "only the one that is here");
  assert.deepEqual(errors, []);
});

// SETUP IS NOT LOST (W2, the 2026-10-21 UI audit): a page opened from the sidebar during setup replaced it, and the rail's step, the
// Setup chip and Chat all left that page on screen - only a reload brought setup back, on its first card. A task found in Search
// never opened at all. Setup now waits, mounted, under whatever is opened over it, and each of the three takes that away.
test("setup comes back as it was left from the rail, the Setup chip and Chat - and a task found in Search opens over it", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true }); t.after(() => harness.close());
  const { page, errors } = await firstRun(harness);
  const shelfOpen = () => page.evaluate(() => {
    const fr = document.querySelector("[data-tq-firstrun]");
    const shown = !!fr && fr.getBoundingClientRect().height > 0;
    return { shown, more: !!fr?.querySelector("[data-tq-shelf-more]"), fewer: [...(fr?.querySelectorAll("button") || [])].some((b) => b.innerText === "Show fewer") };
  });
  // a state of the step that only lives on the screen: every AI card open (the shelf's own Show all)
  await page.click("[data-tq-firstrun] [data-tq-shelf-more]");
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-firstrun] button")].some((b) => b.innerText === "Show fewer"));
  const away = async () => {
    await page.evaluate(() => document.querySelector('[data-tq-nav="connections"]').click());
    await page.waitForFunction(() => document.querySelector("[data-tq-setup-back]") && !(document.querySelector("[data-tq-firstrun]")?.getBoundingClientRect().height > 0));
  };
  const back = async (how) => {
    await page.waitForFunction(() => !document.querySelector("[data-tq-setup-back]") && document.querySelector("[data-tq-firstrun]")?.getBoundingClientRect().height > 0,
      { timeout: 10000 }).catch(() => { throw new Error(`${how} did not bring setup back`); });
    assert.deepEqual(await shelfOpen(), { shown: true, more: false, fewer: true }, `${how}: setup is where it was left - every AI card still open`);
  };
  await away();
  await page.click('[data-tq-setup-step="ai"]'); await back("the rail's step");
  await away();
  await page.evaluate(() => [...document.querySelectorAll("#tqTopNav p, #tqTopNav span")].find((e) => /^Setup:/.test(e.innerText || ""))?.click());
  await back("the Setup chip");
  await away();
  await page.click('[data-tq-view="chat"]'); await back("Chat");
  // a task made during setup, found in Search, opens over setup - and setup is still there behind it
  const made = await fetch(`${harness.fixtureApi}/api/tasks`, { method: "POST", headers: { "Content-Type": "application/json", "X-Taskuary-Token": harness.token },
    body: JSON.stringify({ Title: "Chase the Payworth invoice for Northwind", Summary: "Ask Erin Blake where the invoice is", Kind: "task" }) }).then((r) => r.json());
  assert.ok(made.taskId, JSON.stringify(made));
  await page.click("[data-tq-search-open]");
  await page.waitForSelector("[data-tq-search-input]");
  await page.type("[data-tq-search-input]", "Payworth invoice");
  await page.waitForSelector(`[data-tq-search-task="${made.taskId}"], [data-tq-search-hit]`, { timeout: 20000 });
  await page.evaluate((tid) => (document.querySelector(`[data-tq-search-task="${tid}"]`) || document.querySelector("[data-tq-search-hit]")).click(), made.taskId);
  await page.waitForFunction((tid) => document.querySelector(`[data-tq-task-page="${tid}"]`)?.getBoundingClientRect().height > 0, { timeout: 30000 }, made.taskId)
    .catch(() => { throw new Error("the task found in Search did not open during setup"); });
  assert.ok(await page.$("[data-tq-setup-back]"), "the way back to setup stands over the task");
  await page.click('[data-tq-setup-step="ai"]'); await back("the rail's step, from the task");
  assert.deepEqual(errors, []);
});
