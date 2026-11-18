import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { chmod, mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* THE OWNER'S OWN MAIL ON THE THREAD (the stress round, 2026-11-18): a reply to Erin waits on the task; he answers from his mailbox instead,
   or forwards her mail to Gail. The card never leaves the chat: it stays where it stood, greyed, with its words, and says what happened - he
   answered her, or whom he wrote to. Every DOM change from his mail landing is read, so a card gone for a beat is caught too. Invented people. */
const here = path.dirname(fileURLToPath(import.meta.url)), repo = path.resolve(here, "..", "..");
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "own-reply");
const at = (m) => { const d = new Date(Date.now() + m * 60000), z = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${z(d.getMonth() + 1)}-${z(d.getDate())} ${z(d.getHours())}:${z(d.getMinutes())}:${z(d.getSeconds())}`; };

async function world(t) {
  const bin = await mkdtemp(path.join(os.tmpdir(), "taskuary-fake-claude-"));
  t.after(() => rm(bin, { recursive: true, force: true }).catch(() => {}));
  const win = process.platform === "win32";
  const py = execFileSync(win ? "python" : "python3", ["-c", "import sys; print(sys.executable)"], { encoding: "utf8" }).trim();
  const fake = path.join(repo, "tests", "fake_claude.py");
  await writeFile(path.join(bin, win ? "claude.cmd" : "claude"), win ? `@${py} ${fake} %*\r\n` : `#!/bin/sh\nexec "${py}" "${fake}" "$@"\n`);
  if (!win) await chmod(path.join(bin, "claude"), 0o755);
  await writeFile(path.join(bin, "script.json"), "[]");
  Object.assign(process.env, { FAKE_CLAUDE_SCRIPT: path.join(bin, "script.json"), FAKE_CLAUDE_SPAWN: "0.5", FAKE_CLAUDE_THINK: "1" });
  const h = await startHarness({ fresh: true, bin });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/first-run/ai", { name: "claude" });
  await api("/api/setup/dismiss", { dismissed: true });
  return { ...h, api };
}

for (const [name, to, said] of [["answered", ["erin@northwind.example"], /you answered Erin Blake yourself/],
                                 ["forwarded", ["gail@northwind.example"], /you wrote to gail@northwind\.example yourself/]]) {
  test(`his own mail on the thread (${name}) leaves the reply's card greyed where it stood, saying so`, { timeout: 300000 }, async (t) => {
    const w = await world(t), page = await w.newPage();
    await page.setViewport({ width: 1400, height: 1000 });
    const errors = []; page.on("pageerror", (e) => errors.push(e.message));
    const made = await w.api("/api/fixture/mail-task", { conversation: `conv-${name}`, sent: at(-60) });
    assert.ok(made.reviewId, JSON.stringify(made));
    await page.goto(w.ui, { waitUntil: "domcontentloaded" });
    await page.evaluate((id) => { location.hash = `task=${id}`; }, made.taskId);
    await page.waitForSelector(`[data-tq-task-page] [data-tq-review="${made.reviewId}"]`, { visible: true, timeout: 60000 });
    await new Promise((r) => setTimeout(r, 2000));
    const dir = path.join(out, name); await mkdir(dir, { recursive: true });
    const rec = await record(page, dir);
    // every committed state from here: the draft - its live card, its greyed record, or nowhere - and its words
    await page.evaluate((rid) => { const pane = () => document.querySelector("[data-tq-task-page]"); window.__seen = [];
      const read = () => { const live = pane()?.querySelector(`[data-tq-review="${rid}"]`), past = [...(pane()?.querySelectorAll("[data-tq-past-card]") || [])].find((e) => e.innerText.includes("long review"));
        const s = past ? "past" : live && live.getBoundingClientRect().height > 0 ? "live" : "gone", last = window.__seen.at(-1);
        if (last?.s !== s) window.__seen.push({ s, text: (past || live)?.innerText?.slice(0, 160) || "" }); };
      new MutationObserver(read).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true }); read(); }, made.reviewId);
    await w.api("/api/fixture/own-reply", { id: `own-${name}`, conversation: `conv-${name}`, channel: "email", source: "alex@northwind.example", to,
      subject: "RE: Your review of the tool?", body: "Review attached, two flaws worth fixing. Alex", sent: at(0) });
    await page.waitForFunction(() => window.__seen.at(-1)?.s === "past", { timeout: 30000 }).catch(() => {});
    await new Promise((r) => setTimeout(r, 4000));
    const seen = await page.evaluate(() => window.__seen);
    await rec.stop();
    await page.screenshot({ path: path.join(dir, "after.png") });
    await note(dir, { done: `A reply to Erin waits; the owner's own mail lands on the thread (${name}).`, expect: "The card stays where it stood, greyed with its words, saying what happened - never gone for a beat.",
      saw: JSON.stringify(seen), verdict: seen.every((x) => x.s !== "gone") && seen.at(-1)?.s === "past" && said.test(seen.at(-1)?.text) ? "PASS" : "FAIL" });
    assert.deepEqual(seen.filter((x) => x.s === "gone"), [], `the card left the chat: ${JSON.stringify(seen)}`);
    assert.equal(seen.at(-1)?.s, "past", JSON.stringify(seen));
    assert.match(seen.at(-1).text, said);
    assert.deepEqual(errors, []);
  });
}
