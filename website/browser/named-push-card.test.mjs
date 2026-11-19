import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* THE PUSH CARD THE AGENT WAS TOLD IS UP IS ON HIS SCREEN (design round 6, D1: a general agent committed a fix in the checkout he named and
   proposed the push; Taskuary told it "the owner sees the Push card", and the page - drawing the card only on its own coding switch, off with
   Developer mode - drew nothing. "Press Push" three times on both CLIs, then "run git push in a terminal"). Developer mode off, a general task,
   the push proposed: the card stands with its Push button lit. Recorded. Invented people only. */
const out = path.join(process.env.TQ_REC_DIR || path.join(process.env.TEMP || os.tmpdir(), "claude", "r6a"), "named-push-card");

test("a push proposed from his named checkout stands as its card with Developer mode off", { timeout: 120000 }, async (t) => {
  // ...git on the backend's PATH, as on his computer: the card is read off the checkout itself
  const git = execFileSync(process.platform === "win32" ? "where" : "which", ["git"], { encoding: "utf8" }).trim().split(/\s*\n/)[0].trim();
  const h = await startHarness({ fresh: true, bin: path.dirname(git) });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/dismiss", { dismissed: true });
  const made = await api("/api/fixture/named-push", { git });
  assert.ok(made.taskId, JSON.stringify(made));
  const page = await h.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  await page.goto(`${h.ui}/#task=${made.taskId}`, { waitUntil: "domcontentloaded" });
  const rec = await record(page, out);
  let saw = "";
  try {
    await page.waitForFunction(() => document.querySelector("[data-tq-task-page]")?.innerText.includes("Fix the ledger rounding"), { timeout: 60000 });
    const card = await page.waitForSelector("[data-tq-task-page] [data-tq-landing]", { visible: true, timeout: 20000 }).catch(() => null);
    saw = card ? await card.evaluate((el) => el.innerText.replace(/\s+/g, " ")) : "no landing card";
    await page.screenshot({ path: path.join(out, "shot.png") });
    assert.ok(card, `the Push card is drawn: ${made.says}`);
    assert.match(saw, /Push 1 commit to master of ledger/);
    const lit = await card.evaluate((el) => [...el.querySelectorAll("button")].some((b) => /^Push$/.test(b.innerText.trim()) && !b.disabled));
    assert.ok(lit, `its Push button is lit: ${saw}`);
  } finally {
    await rec.stop();
    await note(out, { done: "A general task with his checkout named in his words, Developer mode off; its agent committed a fix there and proposed the push.",
      expect: "The Push card stands in the chat, its Push button lit, naming the repository.", saw, verdict: saw.includes("Push 1 commit") ? "PASS" : "FAIL" });
  }
});
