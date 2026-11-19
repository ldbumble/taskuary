import assert from "node:assert/strict";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { note, record } from "./recorder.mjs";

/* A FAILURE A LATER STEP OVERCAME READS AS THAT OUTCOME (design round 6, D3: "Failed - No account: the site kept its sign-up form up ... run
   `agent-browser signup` again" stood red under the line that said the account was active). The failed sign-up card is drawn; the same sign-up
   is then made on a later try; the card, where it stood, reads done - no red failure left. Recorded. Invented people only. */
const out = path.join(process.env.TQ_REC_DIR || path.join(process.env.TEMP || os.tmpdir(), "claude", "r6a"), "overcome-card");

test("a failed sign-up card a later try made good reads done where it stood", { timeout: 120000 }, async (t) => {
  const h = await startHarness({ fresh: true });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/dismiss", { dismissed: true });
  const made = await api("/api/fixture/overcome", {});
  assert.ok(made.taskId, JSON.stringify(made));
  const page = await h.newPage();
  await page.setViewport({ width: 1400, height: 900 });
  await page.goto(`${h.ui}/#task=${made.taskId}`, { waitUntil: "domcontentloaded" });
  const rec = await record(page, out);
  const pane = () => page.$eval("[data-tq-task-page]", (el) => el.innerText.replace(/\s+/g, " "));
  let before = "", after = "";
  try {
    await page.waitForFunction(() => /kept its sign-up form up/.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 60000 });
    before = await pane(); await page.screenshot({ path: path.join(out, "before.png") });
    const got = await api("/api/fixture/overcome", { taskId: made.taskId });
    assert.deepEqual(got.rids, [made.reviewId]);
    await page.waitForFunction(() => !/kept its sign-up form up/.test(document.querySelector("[data-tq-task-page]")?.innerText || ""), { timeout: 20000 });
    after = await pane(); await page.screenshot({ path: path.join(out, "after.png") });
    assert.match(after, /Submit the sign-up on RentScope/);
    assert.doesNotMatch(after, /Failed|agent-browser signup/);
  } finally {
    await rec.stop();
    await note(out, { done: "A held sign-up whose press failed, then the same sign-up made on a later try (browsergate.overcome).",
      expect: "The red failed card turns, where it stood, into the done card - no red line left, nothing moves.",
      saw: `before: ${before.slice(-400)}\nafter: ${after.slice(-400)}`, verdict: after && !/Failed/.test(after) ? "PASS" : "FAIL" });
  }
});
