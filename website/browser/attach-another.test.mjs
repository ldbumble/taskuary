import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

/* ATTACH ANOTHER ADDS ANOTHER (the owner, 2026-11-04: a Close out card with two files on its draft, and "I can't attach more things").
   A draft that already carries files takes a third and a fourth from the same button, pressed where the owner presses it, each a chip of
   its own; one too big for any mailbox is refused by its name, where the files are, and the next still goes on. And a file the agent named
   that did not ride (three named, two attached - the third over the cap) is said on the card too, until a file of that name goes on. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("Attach another adds each further file as its own chip, and a file that did not ride is said on the card", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
  const errors = [], seen = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("response", (r) => { if (/attachment/.test(r.url())) seen.push(`${r.request().method()} ${r.status()}`); });
  const tasks = (await (await fetch(`${harness.fixtureApi}/api/tasks`, { headers: { "X-Taskuary-Token": harness.token } })).json()).data;
  const inv = tasks.find((x) => /^Invoice 88213/.test(x.Title));
  assert.ok(inv, "the demo's invoice reply, a draft waiting for Send");
  execFileSync(process.env.TASKUARY_TEST_PYTHON || (process.platform === "win32" ? "python" : "python3"), ["-c", `
import sys
sys.path.insert(0, sys.argv[1])
from pathlib import Path
from taskuary import verdicts
from taskuary.store import SQLiteStore
s = SQLiteStore(str(Path(sys.argv[2]) / 'taskuary.db'))
(rid,) = [r['ReviewId'] for r in s.list_reviews('pending') if r['TaskId'] == int(sys.argv[3])]
verdicts.refused(s, rid,'Northwind summary - south group.xlsx',
                 'that file is over 25MB, which no mailbox will accept')
`, root, harness.home, String(inv.TaskId)], { env: { ...process.env, TASKUARY_HOME: harness.home }, stdio: "pipe" });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  await page.evaluate((id) => { location.hash = `task=${id}`; }, inv.TaskId);
  const card = `[data-tq-task-page="${inv.TaskId}"] [data-tq-closeout]`;
  await page.waitForSelector(card, { timeout: 20000 });
  await sleep(1500);
  const dir = mkdtempSync(path.join(os.tmpdir(), "tq-attach-"));
  const file = (name, n = 64) => { const p = path.join(dir, name); writeFileSync(p, Buffer.alloc(n, 120)); return p; };
  const chips = () => page.$$eval(`${card} .MuiChip-label`, (els) => els.map((e) => e.textContent.split(" · ")[0]));
  // ...pressed as the owner presses it, by its label: the card's own button, Close out's moves, or behind a ▾ - and the picker opens
  const want = (n) => new RegExp(`^${n ? "Attach another" : "Attach a file"}`);
  const where = `${card} button, [data-tq-pane-moves] button, [data-tq-spine-moves] button, [data-tq-row] button, [role=menuitem]`;
  const button = async (n) => {
    const at = () => page.evaluate((sel, re) => {
      const b = [...document.querySelectorAll(sel)].find((x) => new RegExp(re).test(x.textContent.trim()) && x.offsetParent);
      if (!b) return null; const r = b.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2, dis: b.disabled || b.getAttribute("aria-disabled") === "true" };
    }, where, want(n).source);
    let p = await at();
    if (!p) for (const more of await page.$$("[data-tq-pane-moves] [data-tq-more], [data-tq-row] [data-tq-more]")) {
      await more.click(); await sleep(300); if ((p = await at())) break; await page.keyboard.press("Escape");
    }
    return p;
  };
  let last = 0;
  const add = async (p, n) => {
    const b = await button(n);
    const row = b ? "" : await page.evaluate(async (sel) => [...document.querySelectorAll(sel)].map((x) => x.textContent.trim().slice(0, 24)).join(" | "), where);
    assert.ok(b && !b.dis, `"${want(n).source.slice(1)}" is there to press with ${n} file(s) on: ${JSON.stringify(b)} ${row}`);
    const hit = await page.evaluate((x, y) => { const e = document.elementFromPoint(x, y); return `${e?.tagName}:${e?.textContent?.trim().slice(0, 30)}`; }, b.x, b.y);
    // ...at a hand's pace: two presses of one verb inside actionRow's REPEAT_MS are one double-click, and the second opens nothing
    await sleep(Math.max(0, 700 - (Date.now() - last))); last = Date.now();
    const [chooser] = await Promise.all([page.waitForFileChooser({ timeout: 5000 }).catch((e) => assert.fail(`${e.message} - clicked ${hit} at ${JSON.stringify(b)}, file ${n}`)),
      page.mouse.click(b.x, b.y)]);
    await chooser.accept([p]);
  };
  const short = () => page.$$eval(`${card} [data-tq-not-attached]`, (els) => els.map((e) => e.textContent));
  assert.deepEqual(await short(), ["Not attached: Northwind summary - south group.xlsx — that file is over 25MB, which no mailbox will accept."]);
  const names = ["Northwind summary - east group.xlsx", "Northwind summary - west group.xlsx", "Northwind summary - north group.xlsx", "remittance.pdf"];
  for (const [i, name] of names.entries()) {
    await add(file(name), i);
    await page.waitForFunction((sel, n) => document.querySelectorAll(`${sel} .MuiChip-label`).length >= n, { timeout: 15000 }, card, i + 1).catch(() => {});
    const said = await page.$eval(card, (e) => e.textContent.slice(0, 600));
    assert.deepEqual(await chips(), names.slice(0, i + 1), `file ${i + 1} is on the card: ${said} / ${JSON.stringify(seen)}`);
  }
  // ...one too big for any mailbox is refused out loud, by its name, where the files are - and the next one still goes on
  await add(file("Northwind summary - all sites.xlsx", 26 * 1024 * 1024), names.length);
  await page.waitForFunction((sel) => /all sites\.xlsx.*over 25MB/.test(document.querySelector(sel)?.textContent || ""), { timeout: 30000 }, card)
    .catch(async (e) => assert.fail(`${e.message}: ${await page.$eval(card, (c) => c.textContent.slice(0, 900))} / ${JSON.stringify(seen)}`));
  assert.deepEqual(await chips(), names, "the refused file is no chip");
  await add(file("cover note.txt"), names.length);
  await page.waitForFunction((sel, n) => document.querySelectorAll(`${sel} .MuiChip-label`).length > n, { timeout: 15000 }, card, names.length);
  assert.deepEqual(await chips(), [...names, "cover note.txt"]);
  // ...and the file the agent could not attach, put on by hand after all: its line comes off
  await add(file("Northwind summary - south group.xlsx"), names.length);
  await page.waitForFunction((sel) => !document.querySelector(`${sel} [data-tq-not-attached]`), { timeout: 15000 }, card);
  assert.equal((await chips()).length, names.length + 2);
  assert.deepEqual(errors, []);
});
