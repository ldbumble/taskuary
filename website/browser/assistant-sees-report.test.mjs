import assert from "node:assert/strict";
import test from "node:test";

import { clickNav, startHarness } from "./harness.mjs";
import { api, scriptChat, shot, sleep, stepRows, until } from "./sees-page.mjs";

/* SET UP WITH AI OPENS THE CHAT, NOT A BOX ON THE PAGE (the owner, 2026-10-30: "the AI box on top of report/dashboard setup goes away;
   those buttons open the corner chat window with that setup as its subject"). Reports' list carries a door where "Describe the report you
   want" stood: it brings up the empty builder and asks in the chat. The scripted answer fills the describe-it the page keeps for the
   Assistant - the same composer the box ran - and the draft lands in the builder through the same onDraft. Its answer is heard next.
   Nothing is saved: Save stays the owner's. */

const ASK = "Every Monday, list the AP bills due in the next 30 days and call out anything over 10k.";

test("Reports: Set up with AI opens the builder and the chat; the Assistant drafts into the builder, and saves nothing", { timeout: 300000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
  const errors = [], composed = [], saved = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const sources = (await api(harness, "/api/sources")).data || [];
  const cfgOf = (s) => { try { return JSON.parse(s.ConfigJson || "{}"); } catch { return {}; } };
  const base = sources.map(cfgOf).find((c) => c.type && !["agent", "dashboard"].includes(c.type) && !c.components && c.access !== "write");
  assert.ok(base, "a report in the demo to draft like");
  const draft = { ...base, title: "AP bills due in 30 days" };
  const turns = scriptChat(page, harness, (body) => {
    if (body.react) return { say: "It is in the builder - check it, then Preview in step 2 before you save." };
    const f = (body.view?.fields || []).find((x) => x.key === "describe");
    return { say: "Drafting it from your words.", view_ops: [{ op: "set", field: f?.key || "describe", value: ASK }] };
  }, (req, url) => {
    if (url.pathname === "/api/reports/compose" && req.method() === "POST") {
      composed.push(JSON.parse(req.postData() || "{}"));
      req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ config: draft, explain: "Drafted from your words.", confidence: "high" }) });
      return true;
    }
    if (url.pathname === "/api/sources" && req.method() === "POST") saved.push(req.postData());
    return false;
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("[data-tq-nav='reports']", { timeout: 60000 });
  await clickNav(page, "Reports");
  await page.waitForSelector('[data-tq-browse-chip="reports"]', { timeout: 30000 });
  await page.$eval('[data-tq-browse-chip="reports"]', (n) => n.click());
  await page.waitForSelector('[data-tq-setup-ai="report"]', { timeout: 30000 });
  assert.ok(!(await page.evaluate(() => /Describe the report you want/.test(document.querySelector("[data-tq-browse='reports']")?.innerText || ""))),
    "no AI box on top of the list any more");
  await shot(page, "report", "1-list-with-door");

  await page.click('[data-tq-setup-ai="report"]');
  await until(page, () => { const p = document.querySelector(".tq-chat-pop"); return !!p && !p.hidden; });
  await until(page, () => /^Asked the builder for/.test([...document.querySelectorAll(".tq-chat-pop .tq-aui-step")].map((x) => x.innerText.trim()).join("\n")));
  const first = turns[0];
  assert.match(first.text, /^Help me set up a new report/);
  assert.equal(first.view?.area, "reports");
  assert.match(first.view?.title || "", /a new report being set up/, "the empty builder is up, and is what the chat is about");
  assert.ok((first.view.fields || []).some((f) => f.key === "describe"), "the composer is a field it may fill");
  for (let i = 0; i < 40 && !composed.length; i++) await sleep(150);
  assert.deepEqual(composed, [{ ask: ASK }], "the same composer the describe box ran");
  // ...the draft is in the builder: its title on the page, nothing saved
  await until(page, (t) => [...document.querySelectorAll("[data-tq-browse='reports'] input")].some((i) => i.value === t), draft.title);
  const rows = await stepRows(page);
  assert.match(rows[0], /^Asked the builder for: Every Monday/);
  await until(page, () => /check it, then Preview in step 2/.test(document.querySelector(".tq-chat-pop")?.innerText || ""));
  assert.ok(turns.some((x) => /^compose passed/.test(x.react || "")), "what the composer answered was heard next");
  await sleep(1000);
  assert.deepEqual(saved, [], "Save stays the owner's");
  await shot(page, "report", "2-drafted-into-builder");
  assert.deepEqual(errors, []);
});
