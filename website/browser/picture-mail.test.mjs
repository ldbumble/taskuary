import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* A MAIL THAT IS ONLY A PICTURE, AND A LINK BEHIND WORDS (the owner, 2026-11-03: "in a fyi email where entire email was a image it showed
   nothing", "hyper links in fyi email like view report are not coming thru"). Opened in Came from: the pasted picture is drawn from its
   attachment, the picture on the sender's site is said plainly - never a blank - and "View report" is a link that leaves for the browser.
   Invented sender and addresses (fixture_changes.picture_mail). */
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("a picture-only mail shows its picture or says why it cannot, and View report is a link", { timeout: 300000 }, async (t) => {
  const h = await startHarness();
  t.after(() => h.close());
  const page = await h.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 900, deviceScaleFactor: 1 });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await page.waitForSelector("[data-tq-rail] .tq-pile-row", { timeout: 30000 });
  const made = await (await fetch(`${h.fixtureApi}/api/fixture/task/picture-mail`, { method: "POST",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: "{}" })).json();
  const CUR = `[data-tq-canvas-item]:has([data-tq-task-page="${made.taskId}"])`, FROM = `${CUR} [data-tq-from]`;
  await page.evaluate((id) => { location.hash = ""; location.hash = `task=${id}`; }, made.taskId);
  await page.waitForSelector(`${CUR} [data-tq-task-body][data-tq-sections]`, { timeout: 20000 });
  await sleep(1200);
  if (await page.$(`${CUR} [data-tq-section-tab=from]`)) { await page.click(`${CUR} [data-tq-section-tab=from] [data-tq-tab-arrow]`); await sleep(800); }
  const letter = async (mid) => {
    if (!await page.$(`${FROM} [data-tq-letter="${mid}"]`)) await page.click(`${FROM} [data-tq-conversation-row][data-tq-mid="${mid}"]`);
    await page.waitForSelector(`${FROM} [data-tq-letter="${mid}"]`, { visible: true, timeout: 10000 });
    await sleep(900);
    return page.evaluate((sel) => {
      const el = document.querySelector(sel), img = el.querySelector("img");
      return { text: el.innerText, img: img ? { src: img.getAttribute("src"), w: img.naturalWidth, done: img.complete } : null,
        bare: el.querySelector("[data-tq-bare]")?.innerText || "",
        links: [...el.querySelectorAll("[data-tq-letter-body] a")].map((a) => ({ text: a.innerText, href: a.getAttribute("href"), target: a.target, rel: a.rel })) };
    }, `${FROM} [data-tq-letter="${mid}"]`);
  };
  const [pasted, remote, report] = made.mids;

  const a = await letter(pasted);
  assert.ok(a.img && /^\/api\/attachments\/\d+/.test(a.img.src), `the pasted picture is drawn from its attachment: ${JSON.stringify(a)}`);
  assert.ok(a.img.done && a.img.w > 0, "...and it loaded");
  assert.doesNotMatch(a.text, /\(empty\)|\[image/, "no blank and no stand-in in the words");

  const b = await letter(remote);
  assert.equal(b.img, null, "nothing from the sender's site is loaded");
  assert.match(b.bare, /picture on the sender's site, and Taskuary does not load outside pictures - open the original/);

  const c = await letter(report);
  assert.deepEqual(c.links, [{ text: "View report", href: "https://reports.vendor.example/r/9?u=alex", target: "_blank", rel: "noopener noreferrer" }]);
  assert.deepEqual(errors, []);
});
