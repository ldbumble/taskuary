import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* WHAT TASKUARY KNOWS, CORRECTED WHERE YOU READ IT (slice 6 of the memory redesign, 2026-10-25; the owner's ruling 2, 2026-10-23: Keep /
   Wrong / Forget). Settings > Docs > LEARNED.md > Visualize draws the five subjects with who reads each, the people lines under their
   person, and the three marks on a learned line - Forget alone on a line you wrote. Clicked through the failure first: a mark the server
   does not take says so by its line and changes nothing. Then Forget takes the line out and leaves a tombstone What changed shows with no
   marks left on it; and with no AI connected the page says "Connect an AI to learn how you work". Invented Northwind people. */

async function request(h, path, method = "GET", body) {
  const response = await fetch(`${h.fixtureApi}${path}`, {
    method, headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  assert.ok(response.ok, `${method} ${path}: ${response.status}`);
  return response.json();
}

const LEARNED = "- Payroll questions from site managers go to Ray Colton (ray@northwind.example) [s:4 | ev: task1 | seen: 2026-10-20 | k: payroll ray colton]";
const OWN = "- Paula Vance (paula@northwind.example) prefers a call to a long mail";

test("Visualize groups by subject, marks a learned line, says why a mark did not take, and Forget leaves a tombstone", { timeout: 240000 }, async (t) => {
  const harness = await startHarness({ fresh: true });          // a fresh install: writes are its own, and no AI is connected
  t.after(() => harness.close());
  const doc = (await request(harness, "/api/doc/learned")).content || "";
  assert.match(doc, /## Your people/, "the template has the people section");
  await request(harness, "/api/doc/learned", "PUT", { content: doc.replace("## Your people\n", `## Your people\n${LEARNED}\n${OWN}\n`) });

  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // the failure path first: the server refuses the first mark
  let refuse = true;
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    if (new URL(r.url()).pathname === "/api/learned/mark" && refuse) { refuse = false; return r.respond({ status: 500, contentType: "application/json", body: "{}" }); }
    page.fixtureRequestGuard(r);
  });
  await page.goto(`${harness.ui}#settings=docs&doc=learned&view=viz`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForSelector('[data-tq-learned-section="people"] [data-tq-learned-line="payroll ray colton"]', { timeout: 60000 });

  const heads = await page.$$eval("[data-tq-learned-section]", (els) => els.map((e) => [e.getAttribute("data-tq-learned-section"), e.firstChild?.textContent || ""]));
  assert.deepEqual(heads.map(([s]) => s), ["people", "care", "work", "promises", "bring", "watching", "proposed"]);
  assert.match(heads[0][1], /YOUR PEOPLE · read by triage \(priority only\) · drafts · the Advisor · the Assistant · agents/);
  assert.ok(!heads.some(([, h]) => /rides into every prompt/i.test(h)));
  assert.match(await page.$eval("[data-tq-learn-no-ai]", (e) => e.textContent), /Connect an AI to learn how you work/);
  assert.ok(await page.$("[data-tq-learn-no-ai] [data-tq-connect-ai]"), "the no-AI line carries its Connect an AI");

  const marksOf = (needle) => page.$$eval("[data-tq-learned-line]", (els, n) => {
    const card = els.find((e) => e.parentElement?.textContent.includes(n));
    return card ? [...card.querySelectorAll("[data-tq-mark]")].map((b) => b.getAttribute("data-tq-mark")) : null;
  }, needle);
  assert.deepEqual(await marksOf("Ray Colton"), ["keep", "wrong", "forget"]);
  assert.deepEqual(await marksOf("Paula Vance"), ["forget"], "your own line takes Forget alone - it is not something Taskuary learned wrong");

  // the refused mark: said by its line, and nothing changed
  await page.click('[data-tq-learned-line="payroll ray colton"] [data-tq-mark="wrong"]');
  await page.waitForFunction(() => [...document.querySelectorAll('[role="alert"]')].some((e) => /did not go through/.test(e.textContent)), { timeout: 15000 });
  assert.match((await request(harness, "/api/doc/learned")).content, /Ray Colton/, "a refused Wrong changed nothing");

  // Forget: the line leaves, a tombstone stays
  await page.click('[data-tq-learned-line="payroll ray colton"] [data-tq-mark="forget"]');
  await page.waitForFunction(() => !document.querySelector('[data-tq-learned-line="payroll ray colton"]'), { timeout: 15000 });
  assert.doesNotMatch((await request(harness, "/api/doc/learned")).content, /Ray Colton/);
  const changes = (await request(harness, "/api/learned/changes")).data;
  const newest = changes.find((r) => r.key === "payroll ray colton" && r.newest);
  assert.equal(newest?.standing, "forgotten", JSON.stringify(changes.slice(0, 4)));

  // ...and What changed shows it put down, with nothing left to press on it
  await page.goto(`${harness.ui}#settings=docs&doc=learned&view=changes`, { waitUntil: "domcontentloaded", timeout: 90000 });
  await page.waitForSelector("[data-tq-learned-changes]", { timeout: 60000 });
  const row = await page.$$eval("[data-tq-learned-changes] > div", (els) => {
    const r = els.find((e) => /Ray Colton/.test(e.textContent));
    return r ? { text: r.textContent, marks: r.querySelectorAll("[data-tq-mark]").length } : null;
  });
  assert.ok(row && /Removed by you - stays removed/.test(row.text) && row.marks === 0, JSON.stringify(row));
  assert.deepEqual(errors, []);
});
