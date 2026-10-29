import assert from "node:assert/strict";
import test from "node:test";

import { bodyText, clickNav, startHarness, waitForBody } from "./harness.mjs";
import { settleDemoWatcher, waitForDemoReplays } from "./processing-fixtures.mjs";

const limits = {
  firstVisibleMs: Number(process.env.TASKUARY_BROWSER_VISIBLE_MS || 8000),
  navigationMs: Number(process.env.TASKUARY_BROWSER_NAVIGATION_MS || 3000),
  inputMs: Number(process.env.TASKUARY_BROWSER_INPUT_MS || 1500),
  // not a budget: firstVisibleMs is the budget, measured from before goto. This only bounds a load that never ends.
  loadMs: 60000,
  // nor this: how long a wait for the app to SETTLE may take on a loaded runner. The budgets above are measured and asserted; a wait
  // that is no budget timed out at a budget's few seconds on a busy CI box, a failure about the runner and not the app (2026-10-28)
  settleMs: 30000,
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
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: limits.loadMs });
  await page.waitForSelector(".tq-pile-row.next .card", { timeout: limits.firstVisibleMs });
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
  await page.reload({ waitUntil: "domcontentloaded", timeout: limits.loadMs });
  await page.waitForFunction(() => {
    const walk = [...document.querySelectorAll("button")]
      .find((button) => button.innerText === "Walk me through my tasks");
    // the day's welcome is drawn as a .tq-msg too (904916c2); "no conversation yet" is no OTHER line
    return !!walk && !walk.disabled && !document.querySelector(".tq-msg:not(.tq-welcome-msg)")
      && !document.querySelector(".tq-pile-row.current");
  }, { timeout: limits.settleMs });

  // A fresh fixture has no Current yet. Two same-tick clicks reproduce the duplicate-turn
  // trigger while React is still scheduling its busy render; exactly one request may leave.
  await page.waitForFunction(() => [...document.querySelectorAll("button")]
    .some((button) => button.innerText === "Walk me through my tasks" && !button.disabled), { timeout: limits.settleMs });
  await page.evaluate(() => {
    const button = [...document.querySelectorAll("button")]
      .find((candidate) => candidate.innerText === "Walk me through my tasks");
    button.click();
    button.click();
  });
  await page.waitForSelector(".tq-pile-row.current .card", { timeout: limits.settleMs });
  await page.waitForFunction(() => !document.querySelector(".tq-typing"), { timeout: limits.settleMs });
  await page.waitForSelector(".tq-pile-row.next .card", { timeout: limits.settleMs });
  assert.equal(turnRequests, 1, "a same-tick double click must create exactly one assistant turn");
  // a press is not a typed line (the owner, 2026-10-23): no "Walk me through my tasks." bubble, only the "…" until the item lands
  assert.equal(await page.$$eval(".tq-msg.you", (rows) => rows.filter((row) => row.textContent.includes("Walk me through my tasks")).length), 0);
  assert.equal(await page.$$eval(".tq-pile-row.current", (rows) => rows.length), 1);
  assert.equal(await page.$$eval(".tq-pile-row.next", (rows) => rows.length), 1);
  // CURRENT and NEXT are rings on the row now, not pills inside it: the row already says what it
  // is with its border, and a word repeating that was one more thing on a line meant to carry one
  // (the owner, 2026-09-16: "maybe just subject should be there to clean it up").
  assert.equal(await page.$(".tq-pile-next"), null, "the NEXT/current pills are gone from the row");
  const expectedNext = await page.$eval(".tq-pile-row.next .card b", (node) => node.textContent.trim());
  // Next sits in the card's own foot since the one-card walk (904916c2), not in the verb line under it
  // ...and on a task, under the task view the canvas shows (0.3.7.0: [data-tq-next])
  // ...pressed once it is there and live: a busy box drew the task view after Current did, and a press aimed before then found no
  // Next (or a greyed one) and was lost - the wait below for the advance then ran out (CI, 2026-10-28)
  const nextLive = () => [...document.querySelectorAll(".tq-msg button, [data-tq-next]")]
    .filter((button) => button.innerText.trim() === "Next" && !button.disabled && button.getBoundingClientRect().width > 0).pop();
  await page.waitForFunction(`!!(${nextLive})()`, { timeout: limits.settleMs });
  assert.ok(await page.evaluate(`(() => { const b = (${nextLive})(); b?.click(); return !!b; })()`), "Next is on the card");
  await page.waitForFunction((title) => document.querySelector(".tq-pile-row.current .card b")?.textContent.trim() === title,
    { timeout: limits.settleMs }, expectedNext);
  await page.waitForFunction(() => !document.querySelector(".tq-typing"), { timeout: limits.settleMs });
  assert.equal(turnRequests, 2, "explicit Next must advance with exactly one additional assistant turn");
  const advancedCurrent = await page.$eval(".tq-pile-row.current .card b", (node) => node.textContent.trim());
  assert.equal(advancedCurrent, expectedNext, "the visible Next row must become Current");
  assert.ok(firstVisibleMs <= limits.firstVisibleMs, `Assistant took ${firstVisibleMs}ms to become visible`);
  assert.equal((await bodyText(page)).includes("restoring the session"), false, "Assistant loading must not start a terminal replay");

  // The budget is the PAGE's time on each keystroke - from the key event reaching the window to every listener, React's
  // render and its commit having run (the commit's microtask runs before the bubbling window listener). Timing
  // input.type() from here counted ~70 CDP round trips as well, and a busy box failed the budget on that transport
  // alone (1652ms for a page that spent a fraction of it). The round trip is still reported, as typedMs.
  const input = ".tq-compose textarea";   // found as each press is made: a handle held across the walk's re-renders went stale
  await page.evaluate(() => {
    const spent = window.__tqInputMs = [];
    let began = 0;
    for (const kind of ["keydown", "keypress", "input", "keyup"]) {
      window.addEventListener(kind, () => { began = performance.now(); }, true);
      window.addEventListener(kind, () => { spent.push(performance.now() - began); }, false);
    }
  });
  const typedStarted = performance.now();
  await page.focus(input); await page.keyboard.type("phase zero latency probe");
  await page.waitForFunction(() => document.querySelector(".tq-compose textarea")?.value === "phase zero latency probe", { timeout: 30000 });
  const typedMs = Math.round(performance.now() - typedStarted);
  const spent = await page.evaluate(() => window.__tqInputMs);
  const inputMs = Math.round(spent.reduce((a, b) => a + b, 0));
  assert.ok(inputMs <= limits.inputMs, `Assistant input took ${inputMs}ms over ${spent.length} events, the slowest ${JSON.stringify(spent.map(Math.round).sort((a, b) => b - a).slice(0, 8))}`);
  await page.click(input, { clickCount: 3 });
  await page.keyboard.press("Backspace");

  // the canvas redesign (0.3.7.0): Tasks and Reports are no longer tabs - a task opens as its view in the canvas (a
  // link does it), Reports is the sidebar's browse card, and the Board is the top bar's switch
  const surfaces = [
    ["Board", "text", "Agent board", "census sync fails when a site has no manager"],
    ["Reports", "text", "reports read and summarise", "Headcount by site, nightly"],
  ];
  const timings = { firstVisibleMs, inputMs, typedMs };
  for (const [label, waitKind, readyMarker, fixtureText] of surfaces) {
    const before = performance.now();
    await clickNav(page, label);
    if (label === "Reports") {
      await page.waitForSelector('[data-tq-browse-chip="reports"]', { timeout: limits.navigationMs });
      // a DOM click: the chip's frame smooth-scrolls into view, and a coordinate click can land beside it mid-scroll
      await page.$eval('[data-tq-browse-chip="reports"]', (node) => node.click());
    }
    if (waitKind === "selector") await page.waitForSelector(readyMarker, { timeout: limits.navigationMs });
    else await waitForBody(page, readyMarker, limits.navigationMs);
    const elapsed = Math.round(performance.now() - before);
    // The marker is the tab's own chrome, which paints before its data arrives - Tasks' search box
    // is there while /api/tasks is still in flight - so reading body text the instant the marker
    // appears raced the response rather than waiting for it. Navigation keeps its own budget; the
    // fixture row only has to turn up.
    await waitForBody(page, fixtureText, limits.settleMs);
    assert.ok(elapsed <= limits.navigationMs, `${label} took ${elapsed}ms to become visible`);
    timings[`${label.toLowerCase()}VisibleMs`] = elapsed;
  }

  await clickNav(page, "Assistant");
  await page.waitForSelector(".tq-pile-row.current .card", { timeout: limits.settleMs });
  assert.equal(await page.$eval(".tq-pile-row.current .card b", (node) => node.textContent.trim()), advancedCurrent,
    "tab navigation must retain Current");

  await page.reload({ waitUntil: "domcontentloaded", timeout: limits.loadMs });
  await page.waitForSelector(".tq-pile-row.current .card", { timeout: limits.settleMs });
  assert.equal(await page.$eval(".tq-pile-row.current .card b", (node) => node.textContent.trim()), advancedCurrent,
    "durable replay must restore Current");
  // the Current turn is a chat line, or - on a task - the task view the canvas shows (0.3.7.0), which fills in its title
  // once the task loads
  const currentTurns = (title) => [...document.querySelectorAll(".tq-chat-inner > .tq-msg, .tq-chat-inner > .tq-canvas-live")]
    .filter((row) => row.textContent.includes(title)).length;
  await page.waitForFunction(currentTurns, { timeout: limits.settleMs }, advancedCurrent);
  assert.equal(await page.evaluate(currentTurns, advancedCurrent), 1, "durable replay must not duplicate the Current assistant turn");
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
