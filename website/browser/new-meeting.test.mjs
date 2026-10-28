import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { boot, sleep } from "./walkdriver.mjs";

/* NEW → MEETING (the owner, 2026-10-28: "probably new meeting screen is better"). On the demo world, whose calendar is a scripted week
   (demo.agenda) and whose directory knows Gail Moreno: New's Meeting tab, a person picked by name and a length, Find times shows free times
   that clear that week, and a pick makes a task whose Close out holds the invite with Send - drafted, nothing sent. Then the phone. */
const shot = async (page, name) => {
  if (!process.env.TASKUARY_SHOTS) return;
  await mkdir(process.env.TASKUARY_SHOTS, { recursive: true });
  await page.screenshot({ path: path.join(process.env.TASKUARY_SHOTS, `${name}.png`) });
};
const openMeeting = async (page) => {
  await page.evaluate(() => { location.hash = "#new-task"; });
  await page.waitForSelector("[data-tq-new] [role=tab]", { timeout: 20000 });
  await page.$$eval("[data-tq-new] [role=tab]", (tabs) => tabs.find((t) => t.textContent.includes("Meeting"))?.click());
  await page.waitForSelector("[data-tq-meeting]", { timeout: 10000 });
};
const authed = (page, url, init = {}) => page.evaluate(async (url, init) => {
  const r = await fetch(url, { ...init, headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token"), "Content-Type": "application/json" } });
  return r.json();
}, url, init);

test("New → Meeting finds free times and a pick drafts the invite into a task's Close out, sending nothing", { timeout: 240000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 950 });
  await openMeeting(page);
  assert.equal(await page.$eval("[data-tq-find-times]", (b) => b.disabled), true, "nothing to find before who and what");
  await page.click("[data-tq-meeting] .MuiAutocomplete-root input");
  await page.keyboard.type("gail");
  await page.waitForFunction(() => [...document.querySelectorAll(".MuiAutocomplete-popper [role=option]")].some((o) => /Gail Moreno/.test(o.textContent)), { timeout: 15000 });
  await page.$$eval(".MuiAutocomplete-popper [role=option]", (os) => os.find((o) => /Gail Moreno/.test(o.textContent)).click());
  await sleep(300);
  await page.type("[data-tq-meeting-subject]", "the audit list");
  await page.click("[data-tq-length='45']");
  assert.match(await page.$eval("[data-tq-meeting]", (e) => e.innerText), /gmoreno@northwind\.example/);
  await page.click("[data-tq-find-times]");
  await page.waitForSelector("[data-tq-meeting-slots] [data-tq-slot]", { timeout: 20000 });
  const slots = await page.$$eval("[data-tq-slot]", (bs) => bs.map((b) => ({ at: b.dataset.tqSlot, label: b.textContent })));
  assert.ok(slots.length >= 3 && slots.length <= 5, JSON.stringify(slots));
  // the same times the server reads off the scripted week: inside working hours, never over a busy block
  const got = await authed(page, "/api/meetings/slots?to=gmoreno%40northwind.example&minutes=45");
  assert.deepEqual(slots.map((s) => s.at), got.slots.map((s) => s.start));
  for (const s of got.slots) assert.ok(s.start.slice(11) >= "09:00" && s.end.slice(11) <= "17:00", JSON.stringify(s));
  assert.match(await page.$eval("[data-tq-meeting-slots]", (e) => e.innerText), /45 minutes - pick a time/);
  await shot(page, "1-find-times");

  const made = page.waitForResponse((r) => r.url().endsWith("/api/meetings") && r.request().method() === "POST", { timeout: 20000 });
  await page.click(`[data-tq-slot="${slots[0].at}"]`);
  const out = await (await made).json();
  assert.ok(out.ok, JSON.stringify(out));
  assert.match(out.title, /^Meeting with Gail Moreno about the audit list$/);
  // ...the task comes up, its Close out holding the invite with Send
  await page.waitForFunction(() => /Invite gmoreno@northwind\.example to the audit list/.test(document.querySelector("[data-tq-closeout]")?.innerText || ""), { timeout: 20000 });
  const co = await page.$eval("[data-tq-closeout]", (e) => e.innerText);
  assert.match(co, /tells the calendar/);
  assert.ok(await page.$$eval("[data-tq-closeout] button", (bs) => bs.some((b) => b.textContent.trim() === "Send" && !b.disabled)), "Send is under the invite, live with no note");
  await shot(page, "2-task-close-out");
  const d = await authed(page, `/api/tasks/${out.taskId}`);
  const rv = d.reviews.find((r) => r.ReviewId === out.reviewId);
  assert.equal(rv.Status, "pending");
  assert.notEqual(rv.DeliveryState, "sent", "drafted, nothing sent");
  assert.deepEqual(errors, []);
});

test("New → Meeting on a phone: one column, nothing wider than the screen", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 390, height: 844 });
  await openMeeting(page);
  await page.click("[data-tq-meeting] .MuiAutocomplete-root input");
  await page.keyboard.type("erin@northwind.example"); await page.keyboard.press("Enter"); await sleep(300);
  await page.type("[data-tq-meeting-subject]", "the Q3 budget");
  await page.click("[data-tq-find-times]");
  await page.waitForSelector("[data-tq-meeting-slots] [data-tq-slot]", { timeout: 20000 });
  await sleep(300);
  const wide = await page.evaluate(() => {
    const w = document.documentElement.clientWidth;
    return [...document.querySelectorAll("[data-tq-meeting] *")].filter((e) => e.getBoundingClientRect().right > w + 1).map((e) => e.tagName + "." + e.className).slice(0, 5);
  });
  assert.deepEqual(wide, []);
  const cols = await page.$$eval("[data-tq-slot]", (bs) => new Set(bs.map((b) => Math.round(b.getBoundingClientRect().left))).size);
  assert.equal(cols, 1, "the times stack");
  await page.$eval("[data-tq-meeting-slots]", (e) => e.scrollIntoView({ block: "center" }));
  await shot(page, "3-phone");
  assert.deepEqual(errors, []);
});
