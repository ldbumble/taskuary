import assert from "node:assert/strict";
import test from "node:test";

import { bodyText, clickNav, startHarness, waitForBody } from "./harness.mjs";
import { settleDemoWatcher, waitForDemoReplays } from "./processing-fixtures.mjs";

const limits = {
  firstVisibleMs: Number(process.env.TASKUARY_BROWSER_VISIBLE_MS || 8000),
  navigationMs: Number(process.env.TASKUARY_BROWSER_NAVIGATION_MS || 3000),
  inputMs: Number(process.env.TASKUARY_BROWSER_INPUT_MS || 1500),
};

test("P0-BROWSER renders isolated fixture flows", { timeout: 120000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  assert.notEqual(harness.backendPort, 7787);
  assert.notEqual(harness.frontendPort, 7787);
  assert.notEqual(harness.backendPort, 7790);
  assert.notEqual(harness.frontendPort, 7790);

  const page = await harness.newPage();
  const pageErrors = [];
  let turnRequests = 0;
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    if (new URL(request.url()).pathname === "/api/concierge/stream") turnRequests += 1;
  });

  const started = performance.now();
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector(".tq-pile-row.next .tq-pile-next", { timeout: limits.firstVisibleMs });
  await page.waitForSelector(".tq-compose textarea:not([disabled])", { timeout: limits.firstVisibleMs });
  const firstVisibleMs = Math.round(performance.now() - started);

  const demo = await page.evaluate(async () => (await fetch("/api/demo", {
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") },
  })).json());
  assert.deepEqual(demo, { demo: true, owner: "Dana Whitfield" });
  assert.equal(await page.$(".tq-typing"), null, "initial history/pipeline loading must not initiate an assistant turn");

  // The demo's recorded agents change from working to waiting during fixture startup.
  // That is useful rendered behavior, but it changes the server's captured Next selection. Measure
  // the cold first paint above, then let the synthetic world finish moving and consume the helper's
  // fresh blank dock before making deterministic owner-navigation assertions below.
  await settleDemoWatcher(harness, await waitForDemoReplays(harness));
  await page.reload({ waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForFunction(() => {
    const walk = [...document.querySelectorAll("button")]
      .find((button) => button.innerText === "Walk me through my tasks");
    return !!walk && !walk.disabled && !document.querySelector(".tq-msg")
      && !document.querySelector(".tq-pile-row.current");
  }, { timeout: limits.firstVisibleMs });

  // A fresh fixture has no Current yet. Two same-tick clicks reproduce the duplicate-turn
  // trigger while React is still scheduling its busy render; exactly one request may leave.
  await page.waitForFunction(() => [...document.querySelectorAll("button")]
    .some((button) => button.innerText === "Walk me through my tasks" && !button.disabled), { timeout: 10000 });
  await page.evaluate(() => {
    const button = [...document.querySelectorAll("button")]
      .find((candidate) => candidate.innerText === "Walk me through my tasks");
    button.click();
    button.click();
  });
  await page.waitForSelector(".tq-pile-row.current .tq-pile-next.cur", { timeout: 15000 });
  await page.waitForFunction(() => !document.querySelector(".tq-typing"), { timeout: 15000 });
  await page.waitForSelector(".tq-pile-row.next .tq-pile-next", { timeout: limits.navigationMs });
  assert.equal(turnRequests, 1, "a same-tick double click must create exactly one assistant turn");
  assert.equal(await page.$$eval(".tq-msg.you", (rows) => rows.filter((row) => row.textContent.includes("Walk me through my tasks.")).length), 1);
  assert.equal(await page.$$eval(".tq-pile-row.current", (rows) => rows.length), 1);
  assert.equal(await page.$$eval(".tq-pile-row.next", (rows) => rows.length), 1);
  assert.equal(await page.$eval(".tq-pile-row.current .tq-pile-next", (node) => node.textContent.trim().toLowerCase()), "current");
  assert.equal(await page.$eval(".tq-pile-row.next .tq-pile-next", (node) => node.textContent.trim().toLowerCase()), "next");
  const expectedNext = await page.$eval(".tq-pile-row.next .card b", (node) => node.textContent.trim());
  await page.evaluate(() => [...document.querySelectorAll(".tq-compose .tq-quick button")]
    .find((button) => button.innerText === "Next")?.click());
  await page.waitForFunction((title) => document.querySelector(".tq-pile-row.current .card b")?.textContent.trim() === title,
    { timeout: 15000 }, expectedNext);
  await page.waitForFunction(() => !document.querySelector(".tq-typing"), { timeout: 15000 });
  assert.equal(turnRequests, 2, "explicit Next must advance with exactly one additional assistant turn");
  const advancedCurrent = await page.$eval(".tq-pile-row.current .card b", (node) => node.textContent.trim());
  assert.equal(advancedCurrent, expectedNext, "the visible Next row must become Current");
  assert.ok(firstVisibleMs <= limits.firstVisibleMs, `Assistant took ${firstVisibleMs}ms to become visible`);
  assert.equal((await bodyText(page)).includes("restoring the session"), false, "Assistant loading must not start a terminal replay");

  const input = await page.$(".tq-compose textarea");
  const inputStarted = performance.now();
  await input.type("phase zero latency probe");
  await page.waitForFunction(() => document.querySelector(".tq-compose textarea")?.value === "phase zero latency probe", { timeout: limits.inputMs });
  const inputMs = Math.round(performance.now() - inputStarted);
  assert.ok(inputMs <= limits.inputMs, `Assistant input took ${inputMs}ms`);
  await input.click({ clickCount: 3 });
  await page.keyboard.press("Backspace");

  const surfaces = [
    ["Tasks", "selector", '[aria-label="Search all tasks"]', "Reconcile the August GL export"],
    ["Board", "text", "Agent board", "Waiting on you"],
    ["Reports", "text", "Reports & workflows", "Headcount by site, nightly"],
  ];
  const timings = { firstVisibleMs, inputMs };
  for (const [label, waitKind, readyMarker, fixtureText] of surfaces) {
    const before = performance.now();
    await clickNav(page, label);
    if (waitKind === "selector") await page.waitForSelector(readyMarker, { timeout: limits.navigationMs });
    else await waitForBody(page, readyMarker, limits.navigationMs);
    const elapsed = Math.round(performance.now() - before);
    const rendered = await bodyText(page);
    assert.ok(rendered.includes(fixtureText), `${label} did not render fixture content`);
    assert.ok(elapsed <= limits.navigationMs, `${label} took ${elapsed}ms to become visible`);
    timings[`${label.toLowerCase()}VisibleMs`] = elapsed;
  }

  await clickNav(page, "Assistant");
  await page.waitForSelector(".tq-pile-row.current .tq-pile-next.cur", { timeout: limits.navigationMs });
  assert.equal(await page.$eval(".tq-pile-row.current .card b", (node) => node.textContent.trim()), advancedCurrent,
    "tab navigation must retain Current");

  await page.reload({ waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector(".tq-pile-row.current .tq-pile-next.cur", { timeout: limits.firstVisibleMs });
  assert.equal(await page.$eval(".tq-pile-row.current .card b", (node) => node.textContent.trim()), advancedCurrent,
    "durable replay must restore Current");
  assert.equal(await page.$$eval(".tq-chat-inner > .tq-msg", (rows, title) => rows.filter((row) => row.textContent.includes(title)).length,
    advancedCurrent), 1, "durable replay must not duplicate the Current assistant turn");
  assert.equal(turnRequests, 2, "tab navigation and reload must not initiate another assistant turn");

  assert.deepEqual(page.fixtureEscapes, [], `browser attempted non-fixture requests: ${page.fixtureEscapes.join(", ")}`);
  assert.deepEqual(pageErrors, []);
  t.diagnostic(JSON.stringify({
    fixture: "actual Taskuary --demo backend; synthetic DB; no browser mocks",
    ports: { backend: harness.backendPort, frontend: harness.frontendPort },
    blockedExternalAssets: page.fixtureBlockedAssets,
    timings,
  }));
});
