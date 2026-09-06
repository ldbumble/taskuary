import assert from "node:assert/strict";
import test from "node:test";

import { clickNav, startHarness } from "./harness.mjs";
import { waitForDemoReplays, settleDemoWatcher } from "./processing-fixtures.mjs";

const visibleExact = async (page, text) => page.$$eval("body *", (nodes, wanted) => nodes.filter((node) => {
  const box = node.getBoundingClientRect();
  return node.children.length === 0 && node.textContent.trim().toLowerCase() === wanted
    && box.width > 0 && box.height > 0 && getComputedStyle(node).visibility !== "hidden";
}).length, text);

const stateControls = async (page) => page.$$eval('[role="group"][aria-label="Feed views"]', (groups) => [...new Set(groups.flatMap((group) => [...group.querySelectorAll("*")]).flatMap((node) => {
  const label = node.textContent.trim().toLowerCase();
  const box = node.getBoundingClientRect();
  return node.children.length === 0 && ["all", "unread", "needs me"].includes(label)
    && box.width > 0 && box.height > 0 && getComputedStyle(node).cursor === "pointer" ? [label] : [];
}))].sort());

const clickState = async (page, label) => {
  const candidates = await page.$$('[role="group"][aria-label="Feed views"] *');
  let clicked = false;
  for (const candidate of candidates) {
    const matches = await candidate.evaluate((node, wanted) => {
      const box = node.getBoundingClientRect();
      return node.children.length === 0 && node.textContent.trim().toLowerCase() === wanted
        && box.width > 0 && box.height > 0 && getComputedStyle(node).cursor === "pointer";
    }, label);
    if (matches) {
      await candidate.click();
      clicked = true;
      break;
    }
  }
  assert.ok(clicked, `state control ${label} must be visible`);
};

const pileTitles = async (page) => ({
  current: await page.$eval(".tq-pile-row.current .card b", (node) => node.textContent.trim()),
  next: await page.$eval(".tq-pile-row.next .card b", (node) => node.textContent.trim()),
});

const durableTurns = async (page, token) => page.evaluate(async (fixtureToken) => {
  const response = await fetch("/api/concierge", { headers: { "X-Taskuary-Token": fixtureToken } });
  if (!response.ok) throw new Error(`concierge snapshot failed: ${response.status}`);
  const data = await response.json();
  if (!Array.isArray(data.messages)) throw new Error("concierge snapshot omitted its durable messages");
  return data.messages;
}, token);

test("PW-107 exposes only All and Unread without All creating assistant state", { timeout: 150000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const settledReplays = await waitForDemoReplays(harness);
  assert.ok(settledReplays.some((row) => row.Title?.includes("census sync")),
    "the real Northwind replay must be part of the settled fixture state");
  await settleDemoWatcher(harness, settledReplays);

  const page = await harness.newPage();
  const pageErrors = [];
  const requests = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin === harness.ui) requests.push({ method: request.method(), path: url.pathname, search: url.search });
  });
  const assistantWrites = () => requests.filter(({ method, path }) => method !== "GET"
    && (path.startsWith("/api/concierge") || path === "/api/funnel/settle"));

  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector(".tq-pile-row.next .tq-pile-next", { timeout: 10000 });
  assert.deepEqual(await stateControls(page), ["all", "unread"]);
  assert.equal(await visibleExact(page, "needs me"), 0, "Needs me must be absent from controls and statistics");
  await new Promise((resolve) => setTimeout(resolve, 500));
  assert.deepEqual(assistantWrites(), [], "loading Unread must not automatically start Walk");

  await page.evaluate(() => [...document.querySelectorAll("button")]
    .find((button) => button.innerText === "Walk me through my tasks")?.click());
  await page.waitForSelector(".tq-pile-row.current .tq-pile-next.cur", { timeout: 15000 });
  await page.waitForFunction(() => !document.querySelector(".tq-typing"), { timeout: 15000 });
  await page.waitForSelector(".tq-pile-row.next .tq-pile-next", { timeout: 10000 });
  const established = await pileTitles(page);
  assert.equal(assistantWrites().length, 1, "the one intentional Walk should be the only assistant write");
  const afterWalk = assistantWrites().length;
  const turnsAfterWalk = await durableTurns(page, harness.token);
  assert.ok(turnsAfterWalk.some((turn) => turn.role === "assistant" && turn.card?.key),
    "intentional Walk must persist its assistant card turn");

  await clickState(page, "all");
  await page.waitForSelector(".tqRow [data-tq-open]", { timeout: 10000 });
  assert.equal(await page.$(".tq-pile-row"), null, "All must render the chronological detail rail");
  assert.equal(await page.$(".tq-compose"), null, "All must be detail-only, without assistant chat");
  assert.equal(assistantWrites().length, afterWalk);

  const row = await page.$(".tqRow [data-tq-open]");
  await row.hover();
  await page.waitForFunction(() => document.querySelector(".tqRow [data-tq-open='true']"), { timeout: 5000 });
  await page.waitForFunction(() => (document.querySelector("[data-tq-timeline-stage]")?.innerText || "").trim().length > 40,
    { timeout: 10000 });
  assert.equal(assistantWrites().length, afterWalk, "All hover may fetch detail but must not settle or create a turn");
  await row.click();
  await page.mouse.move(1300, 900);
  await new Promise((resolve) => setTimeout(resolve, 600));
  assert.ok(await page.$(".tqRow [data-tq-open='true']"), "clicking an All row must pin its detail");
  assert.equal(assistantWrites().length, afterWalk, "opening an All row must remain read-only assistant state");

  await clickNav(page, "Tasks");
  await page.waitForSelector('[aria-label="Search all tasks"]', { timeout: 5000 });
  await clickNav(page, "Assistant");
  await page.waitForSelector(".tqRow [data-tq-open]", { timeout: 5000 });
  assert.equal(await page.$(".tq-compose"), null, "returning from another tab must retain All");
  assert.equal(assistantWrites().length, afterWalk, "All tab return must not create assistant state");
  assert.deepEqual(await durableTurns(page, harness.token), turnsAfterWalk,
    "All hover, open and tab return must not create durable assistant turns");
  const feedReads = requests.filter(({ method, path }) => method === "GET" && path === "/api/feed");
  assert.ok(feedReads.length > 0, "the rendered views must exercise the real feed endpoint");
  assert.ok(feedReads.every(({ search }) => !new URLSearchParams(search).has("pending_only")),
    "All/Unread views must not revive the removed pending_only filter");

  await clickState(page, "unread");
  await page.waitForSelector(".tq-pile-row.current .tq-pile-next.cur", { timeout: 10000 });
  assert.deepEqual(await pileTitles(page), established, "All to Unread must retain Current and Next");
  await clickNav(page, "Board");
  await page.waitForFunction(() => document.body.innerText.includes("Agent board"), { timeout: 5000 });
  await clickNav(page, "Assistant");
  await page.waitForSelector(".tq-pile-row.current .tq-pile-next.cur", { timeout: 5000 });
  assert.deepEqual(await pileTitles(page), established, "outer tabs must retain Current and Next");

  await page.reload({ waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector(".tq-pile-row.current .tq-pile-next.cur", { timeout: 10000 });
  await page.waitForSelector(".tq-pile-row.next .tq-pile-next", { timeout: 10000 });
  assert.deepEqual(await pileTitles(page), established, "reload must restore the same Current and Next");
  assert.equal(assistantWrites().length, afterWalk, "view changes, outer tabs and reload must not start Walk");
  assert.deepEqual(await durableTurns(page, harness.token), turnsAfterWalk,
    "outer tabs and reload must preserve durable assistant turns exactly");
  assert.ok(requests.some(({ method, path }) => method === "GET" && path === "/api/concierge"),
    "background assistant reads remain available");

  const race = await harness.newPage();
  const raceErrors = [];
  const raceWrites = [];
  race.on("pageerror", (error) => raceErrors.push(error.message));
  race.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin === harness.ui && request.method() !== "GET"
        && (url.pathname.startsWith("/api/concierge") || url.pathname === "/api/funnel/settle")) {
      raceWrites.push({ method: request.method(), path: url.pathname });
    }
  });
  await race.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await race.waitForSelector(".tq-pile-row.current .tq-pile-next.cur", { timeout: 10000 });
  await clickState(race, "all");
  await race.waitForSelector(".tqRow [data-tq-open='false']", { timeout: 10000 });
  const raceTarget = await race.$(".tqRow [data-tq-open='false']");
  const client = await race.createCDPSession();
  await client.send("Network.enable");
  await client.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 1200,
    downloadThroughput: -1,
    uploadThroughput: -1,
    connectionType: "wifi",
  });
  const detailRequest = race.waitForRequest((request) => {
    const url = new URL(request.url());
    return request.method() === "GET" && url.origin === harness.ui
      && (/^\/api\/tasks\/\d+$/.test(url.pathname) || /^\/api\/messages\/\d+\/thread$/.test(url.pathname));
  }, { timeout: 10000 });
  await raceTarget.hover();
  const pendingDetail = await detailRequest;
  const detailResponse = race.waitForResponse((response) => response.url() === pendingDetail.url(), { timeout: 10000 });
  await new Promise((resolve) => setTimeout(resolve, 120)); // let the hover commit its pending selection
  await clickState(race, "unread");
  await race.waitForSelector(".tq-pile-row.current .tq-pile-next.cur", { timeout: 10000 });
  const completedDetail = await detailResponse;
  await completedDetail.buffer();
  await race.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await client.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 0,
    downloadThroughput: -1,
    uploadThroughput: -1,
    connectionType: "none",
  });
  await client.detach();
  await race.waitForSelector(".tq-compose", { visible: true, timeout: 5000 });
  assert.deepEqual(await pileTitles(race), established,
    "a completed All hover response must not replace Unread Current and Next");
  assert.deepEqual(raceWrites, [], "the delayed All detail response must not create or settle assistant state");
  assert.deepEqual(await durableTurns(race, harness.token), turnsAfterWalk,
    "the delayed All detail response must not create a durable assistant turn");
  assert.deepEqual(race.fixtureEscapes, []);
  assert.deepEqual(raceErrors, []);

  const narrow = await harness.newPage();
  const narrowWrites = [];
  const narrowErrors = [];
  narrow.on("pageerror", (error) => narrowErrors.push(error.message));
  narrow.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin === harness.ui && request.method() !== "GET"
        && (url.pathname.startsWith("/api/concierge") || url.pathname === "/api/funnel/settle")) {
      narrowWrites.push({ method: request.method(), path: url.pathname });
    }
  });
  await narrow.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await narrow.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await narrow.waitForSelector(".tq-pile-row.current .tq-pile-next.cur", { timeout: 10000 });
  await narrow.click('[aria-label="The Timeline"]');
  await narrow.waitForFunction(() => {
    const group = document.querySelector('[role="group"][aria-label="Feed views"]');
    const box = group?.getBoundingClientRect();
    return box && box.width > 0 && box.height > 0;
  }, { timeout: 5000 });
  assert.deepEqual(await stateControls(narrow), ["all", "unread"]);
  assert.equal(await visibleExact(narrow, "needs me"), 0, "Needs me must also be absent at narrow width");
  await clickState(narrow, "all");
  await narrow.waitForSelector(".tqRow [data-tq-open]", { timeout: 10000 });
  assert.equal(await narrow.$(".tq-compose"), null);
  const narrowSubject = await narrow.$eval(".tqRow [data-tq-open]", (node) => {
    const lines = [...node.querySelectorAll("p")].map((part) => part.textContent.trim()).filter(Boolean);
    return lines[1] || lines[0] || "";
  });
  assert.ok(narrowSubject, "fixture All row must expose a subject for detail verification");
  await narrow.click(".tqRow [data-tq-open]");
  await narrow.waitForFunction((subject) => {
    return [...document.querySelectorAll(".MuiDrawer-paper")].some((paper) => {
      const box = paper.getBoundingClientRect();
      return box.width > 0 && box.height > 0 && getComputedStyle(paper).visibility !== "hidden"
        && paper.innerText.includes(subject);
    });
  }, { timeout: 10000 }, narrowSubject);
  assert.deepEqual(await durableTurns(narrow, harness.token), turnsAfterWalk,
    "opening narrow All detail must not create a durable assistant turn");
  await narrow.keyboard.press("Escape");
  await narrow.waitForFunction(() => {
    return [...document.querySelectorAll(".MuiDrawer-paper")].every((paper) => {
      const box = paper.getBoundingClientRect();
      return box.width === 0 || box.height === 0 || getComputedStyle(paper).visibility === "hidden";
    });
  }, { timeout: 5000 });
  await clickState(narrow, "unread");
  await narrow.waitForSelector(".tq-pile-row.current .tq-pile-next.cur", { timeout: 10000 });
  await narrow.waitForSelector(".tq-pile-row.next .tq-pile-next", { timeout: 10000 });
  assert.deepEqual(await pileTitles(narrow), established, "narrow All to Unread must retain Current and Next");
  assert.deepEqual(narrowWrites, [], "narrow view selection must not create or settle assistant state");
  assert.deepEqual(await durableTurns(narrow, harness.token), turnsAfterWalk,
    "narrow detail and view changes must preserve durable assistant turns exactly");

  assert.deepEqual(page.fixtureEscapes, []);
  assert.deepEqual(narrow.fixtureEscapes, []);
  assert.deepEqual(pageErrors, []);
  assert.deepEqual(narrowErrors, []);
});
