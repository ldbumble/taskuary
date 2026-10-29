import assert from "node:assert/strict";
import test from "node:test";
import path from "node:path";

import { startHarness } from "./harness.mjs";

/* A TASK THE ADVISOR RAISED SHOWS THE MAIL IT WAS ABOUT (the owner, 2026-10-28, on a laptop: "you don't see the main source task, only
   triage and advisor?? why does it say advisor twice"). Erin's mail was filed as fyi; the Advisor read her follow-up and said the reply
   was still owed; the task that idea opened drew the Advisor's own line as what came in - "Advisor · Advisor", its words run into
   "whose move: the owner the Advisor's suggestion: ...", cut mid-sentence. Now What came in is Erin's follow-up, the history holds both
   her mails, and the Advisor is one line: "Raised by the Advisor: <its sentence>". At 1440x900, invented people only. TASKUARY_SHOT_DIR
   keeps a picture of the card. */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("a task made from an Advisor idea comes from the mail, the Advisor said in one line", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const made = await (await fetch(`${h.fixtureApi}/api/fixture/task/advisor-raised`, { method: "POST",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: "{}" })).json();
  assert.ok(made.taskId, JSON.stringify(made));
  const CUR = `[data-tq-canvas-item]:has([data-tq-task-page="${made.taskId}"])`;
  await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(`${CUR} [data-tq-task-body][data-tq-sections]`, { timeout: 20000 });
  await sleep(1500);
  if (await page.$(`${CUR} [data-tq-section-tab=from]`)) { await page.click(`${CUR} [data-tq-section-tab=from] [data-tq-tab-arrow]`); await sleep(800); }
  await page.waitForSelector(`${CUR} [data-tq-came-in]`, { visible: true, timeout: 10000 });

  const seen = await page.evaluate((CUR) => {
    const item = document.querySelector(CUR), cameIn = item.querySelector("[data-tq-came-in]");
    return { cameIn: cameIn.innerText, words: cameIn.querySelector("[data-tq-came-in-words]")?.innerText || "",
      raised: [...item.querySelectorAll("[data-tq-raised]")].filter((e) => e.offsetParent).map((e) => e.innerText), all: item.innerText,
      rows: [...item.querySelectorAll("[data-tq-from] [data-tq-conversation-row]")].map((e) => e.innerText.replace(/\s+/g, " ")) };
  }, CUR);
  assert.match(seen.cameIn, /Erin Blake · /, `What came in is from Erin: ${seen.cameIn}`);
  // ...her two mails are the conversation under the boxes, oldest first, her follow-up - what came in - last; each drawn once
  assert.equal(seen.rows.length, 2, JSON.stringify(seen.rows));
  assert.match(seen.rows[0], /Could you send the year-end statements/);
  assert.match(seen.rows[1], /Following up on the year-end statements/);
  assert.equal(seen.all.split("Following up on the year-end statements").length - 1, 1, "the follow-up once");
  assert.deepEqual(seen.raised, ["Raised by the Advisor: Triage filed Erin's mail as fyi, but her follow-up shows the year-end statements are still outstanding - I'd send them today."]);
  assert.doesNotMatch(seen.all, /Advisor · Advisor/i, "the name once");
  assert.doesNotMatch(seen.all, /whose move:|the Advisor's suggestion:/i, "no format text");
  if (process.env.TASKUARY_SHOT_DIR) {
    const card = await page.$(`${CUR} [data-tq-from-cards]`) || await page.$(CUR);
    await card.screenshot({ path: path.join(process.env.TASKUARY_SHOT_DIR, "came-from-card.png") });
    await (await page.$(CUR)).screenshot({ path: path.join(process.env.TASKUARY_SHOT_DIR, "came-from-task.png") });
  }
  assert.deepEqual(errors, []);
});
