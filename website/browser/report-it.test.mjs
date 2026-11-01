import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, sleep, type } from "./walkdriver.mjs";

/* THE OWNER'S SIDE OF "REPORT IT" (the owner, 2026-11-01: "can the advisor/assistant create bug report for you to send or a new feature
   request? ... they will file issues"). On the demo world, with the model's answers recorded (demo_answers.json): a wish asked of the
   Assistant brings up Request a feature, a bug brings up Report this bug, and the Advisor's counted "Report this?" opens the same popup -
   each drafted by the server through the scrub, shown whole, and Send opening GitHub's new-issue page (intercepted here: nothing opens). */

const press = (page, label, scope = "body") => page.evaluate((label, scope) => {
  const b = [...document.querySelectorAll(`${scope} button`)].filter((x) => x.textContent.trim() === label && x.offsetParent).pop();
  if (!b) return false; b.click(); return true;
}, label, scope);

async function popup(page, drafts, n) {
  await page.waitForSelector("[aria-labelledby='bug-report-title']", { timeout: 15000 });
  for (let i = 0; i < 80 && drafts.length < n; i++) await sleep(100);
  assert.equal(drafts.length, n, "the popup asked the server for its scrubbed draft");
  await page.waitForFunction(() => document.querySelector("[aria-labelledby='bug-report-title'] input")?.value, { timeout: 15000 });
  return page.evaluate(() => { const d = document.querySelector("[aria-labelledby='bug-report-title']");
    return { head: d.querySelector("#bug-report-title").innerText, title: d.querySelector("input").value,
             field: [...d.querySelectorAll("label")].map((l) => l.innerText).join(" | "), text: d.querySelector("textarea")?.value || "" }; });
}
const close = async (page) => { await press(page, "Close", "[aria-labelledby='bug-report-title']") || await page.keyboard.press("Escape");
  await page.waitForFunction(() => !document.querySelector("[aria-labelledby='bug-report-title']"), { timeout: 10000 }); };

test("a wish and a bug asked of the Assistant, and the Advisor's Report this?, open the scrubbed draft; Send opens the new-issue page",
  { timeout: 300000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  const drafts = [];
  page.on("response", (r) => { if (new URL(r.url()).pathname === "/api/bug-report/draft") drafts.push(JSON.parse(r.request().postData() || "{}")); });
  await page.evaluate(() => { window.__opened = []; window.open = (u) => { window.__opened.push(String(u)); return null; }; });

  // A WISH: Request a feature under the answer, a feature request in the popup, Send opens the page labelled enhancement
  await type(page, "I wish I could sort the rail by date");
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent.trim() === "Request a feature" && b.offsetParent), { timeout: 30000 });
  assert.ok(await press(page, "Request a feature"));
  const wish = await popup(page, drafts, 1);
  assert.deepEqual([drafts[0].kind, drafts[0].happened, drafts[0].error], ["feature", "a way to sort the rail by date", ""]);
  assert.equal(wish.head, "Request a feature"); assert.match(wish.title, /^\[feature\] /); assert.match(wish.field, /What would help/);
  assert.match(wish.text, /What would help: a way to sort the rail by date/);
  assert.ok(await press(page, "Send", "[aria-labelledby='bug-report-title']"));
  await page.waitForFunction(() => window.__opened.length === 1, { timeout: 10000 });
  const url = new URL(await page.evaluate(() => window.__opened[0]));
  assert.equal(url.origin + url.pathname, "https://github.com/ldbumble/taskuary/issues/new");
  assert.equal(url.searchParams.get("labels"), "enhancement"); assert.match(url.searchParams.get("title"), /^\[feature\] /);
  assert.match(url.searchParams.get("body"), /^### The request\n/);
  await page.waitForFunction(() => !document.querySelector("[aria-labelledby='bug-report-title']"), { timeout: 10000 });

  // A BUG: Report this bug under the answer, drafted as one - nothing opened until Send
  await type(page, "that's a bug - the export button did nothing");
  await page.waitForFunction(() => [...document.querySelectorAll("button")].some((b) => b.textContent.trim() === "Report this bug" && b.offsetParent), { timeout: 30000 });
  assert.ok(await press(page, "Report this bug"));
  const bug = await popup(page, drafts, 2);
  assert.deepEqual([drafts[1].kind, drafts[1].trying], ["bug", "export the board"]);
  assert.equal(bug.head, "Report this bug"); assert.match(bug.title, /^\[bug\] /);
  await close(page);

  // THE ADVISOR: three runs ending on one error, counted by its detector - its Report this? opens the same popup, drafted from what it counted
  const made = await page.evaluate(async () => (await fetch("/api/fixture/advisor/report-idea", { method: "POST", body: "{}",
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } })).json());
  assert.ok(made.ideas?.length, JSON.stringify(made));
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-rail] .tq-pile-row")].some((e) => /failed the same way/.test(e.textContent)), { timeout: 40000 });
  assert.ok(await clickRow(page, await findRow(page, /failed the same way/)));
  // ...its move on Came from's strip, beside the idea's own moves
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-item-sections] button")].some((b) => b.textContent.trim() === "Report this?" && b.offsetParent),
    { timeout: 20000 });
  assert.ok(await press(page, "Report this?", "[data-tq-item-sections]"));
  const counted = await popup(page, drafts, 3);
  assert.deepEqual([drafts[2].kind, drafts[2].screen, drafts[2].route], ["bug", "Advisor", "agent run"]);
  assert.match(drafts[2].error, /KeyError/); assert.match(counted.title, /^\[bug\] /);
  await close(page);
  assert.equal(await page.evaluate(() => window.__opened.length), 1, "only the one Send opened a page");
  assert.deepEqual(errors, []);
});
