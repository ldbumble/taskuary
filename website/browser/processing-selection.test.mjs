import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";
import { waitForDemoReplays, settleDemoWatcher } from "./processing-fixtures.mjs";

async function request(h, path, method = "GET", body) {
  const response = await fetch(`${h.fixtureApi}${path}`, {
    method, headers: { "X-Taskuary-Token": h.token, "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  assert.ok(response.ok, `${method} ${path}: ${response.status}`);
  return response.json();
}

const title = (page, state) => page.$eval(`.tq-pile-row.${state} .card b`, n => n.textContent.trim());
const clickNext = page => page.evaluate(() => {
  const button = [...document.querySelectorAll("button")].find(n => n.textContent.trim() === "Next");
  if (!button || button.disabled) throw new Error("Next must be enabled for this owner gesture");
  button.click();
});

test("PW-115 abandons a Walk validation when New chat replaces its conversation", { timeout: 150000 }, async t => {
  const h = await startHarness();
  t.after(() => h.close());
  await settleDemoWatcher(h, await waitForDemoReplays(h));
  const page = await h.newPage();
  const writes = [];
  page.on("request", r => {
    if (r.method() === "POST" && new URL(r.url()).pathname.startsWith("/api/concierge")) writes.push(r.url());
  });
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForFunction(() => [...document.querySelectorAll("button")]
    .some(n => n.textContent.trim() === "Walk me through my tasks"), { timeout: 15000 });
  // Drain the initial pile/state loads before isolating the owner's Walk capture.
  await page.waitForNetworkIdle({ idleTime: 150, timeout: 15000 });
  const cdp = await page.createCDPSession();
  let heldId, heldNetwork, resolveHeld, resolveDelivered;
  const held = new Promise(resolve => { resolveHeld = resolve; });
  const delivered = new Promise(resolve => { resolveDelivered = resolve; });
  await cdp.send("Network.enable");
  cdp.on("Network.loadingFinished", e => { if (e.requestId === heldNetwork) resolveDelivered(); });
  cdp.on("Fetch.requestPaused", e => {
    if (!heldId) {
      heldId = e.requestId; heldNetwork = e.networkId;
      resolveHeld();
    } else cdp.send("Fetch.continueRequest", { requestId: e.requestId }).catch(() => {});
  });
  await cdp.send("Fetch.enable", { patterns: [{ urlPattern: "*/api/funnel/pile*", requestStage: "Response" }] });
  try {
    await page.evaluate(() => [...document.querySelectorAll("button")]
      .find(n => n.textContent.trim() === "Walk me through my tasks").click());
    await Promise.race([held, new Promise((_, reject) => setTimeout(() => reject(new Error("Walk did not validate pile")), 15000))]);
    assert.ok(heldNetwork);
    const resetResponse = page.waitForResponse(r => new URL(r.url()).pathname === "/api/assistant/dock/new"
      && r.status() === 200, { timeout: 15000 });
    await page.click('button[aria-label^="New chat"]');
    await (await resetResponse).buffer();
    await page.waitForFunction(() => {
      const button = document.querySelector('button[aria-label^="New chat"]');
      return button && !button.disabled;
    }, { timeout: 15000 });
    const fresh = (await request(h, "/api/concierge")).messages;
    assert.deepEqual(fresh, []);
    await cdp.send("Fetch.continueRequest", { requestId: heldId });
    await Promise.race([delivered, new Promise((_, reject) => setTimeout(() => reject(new Error("old Walk pile never delivered")), 15000))]);
    await cdp.send("Fetch.disable");
    await page.waitForNetworkIdle({ idleTime: 500, timeout: 15000 });
    assert.deepEqual(writes, [], "old Walk must not enter the replacement chat after its held read completes");
    assert.equal(await page.$('.tq-pile-row.current'), null);
    assert.deepEqual((await request(h, "/api/concierge")).messages, []);
    assert.deepEqual(page.fixtureEscapes, []);
  } finally {
    await cdp.send("Fetch.disable").catch(() => {});
    await cdp.detach().catch(() => {});
  }
});

test("PW-118 rejects a changed captured Next without advancing Current or retrying", { timeout: 150000 }, async t => {
  const h = await startHarness();
  t.after(() => h.close());
  await settleDemoWatcher(h, await waitForDemoReplays(h));
  const pile = await request(h, "/api/funnel/pile?force=1");
  const target = pile.items.find(i => i.kind === "review" && i.rid);
  assert.ok(target);
  const page = await h.newPage();
  const writes = [], errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("request", r => {
    const url = new URL(r.url());
    if (url.origin === h.ui && r.method() === "POST"
      && (url.pathname.startsWith("/api/concierge") || url.pathname === "/api/funnel/settle")) {
      writes.push({ path: url.pathname, body: JSON.parse(r.postData() || "{}") });
    }
  });
  await page.goto(h.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector(".tq-pile-row .card", { timeout: 15000 });
  await page.evaluate(wanted => {
    const row = [...document.querySelectorAll(".tq-pile-row .card")]
      .find(n => n.querySelector("b")?.textContent.trim() === wanted);
    if (!row) throw new Error("synthetic review row missing");
    row.click();
  }, target.title);
  await page.waitForSelector(".tq-pile-row.current .card", { timeout: 15000 });
  await page.waitForFunction(() => !document.querySelector(".tq-typing"), { timeout: 15000 });
  await page.waitForSelector(".tq-pile-row.next .card", { timeout: 15000 });
  const heldCurrent = await title(page, "current");
  const shownNext = await title(page, "next");
  const before = (await request(h, "/api/concierge")).messages;
  const beforeWrites = writes.length;

  const cdp = await page.createCDPSession();
  let releaseId, resolvePaused;
  const paused = new Promise(resolve => { resolvePaused = resolve; });
  cdp.on("Fetch.requestPaused", event => {
    if (!releaseId) { releaseId = event.requestId; resolvePaused(JSON.parse(event.request.postData)); }
    else cdp.send("Fetch.continueRequest", { requestId: event.requestId }).catch(() => {});
  });
  await cdp.send("Fetch.enable", {
    patterns: [{ urlPattern: "*/api/concierge/stream", requestStage: "Request" }],
  });
  try {
    await clickNext(page);
    const bound = await Promise.race([paused, new Promise((_, reject) =>
      setTimeout(() => reject(new Error("Next did not issue its guarded stream request")), 15000))]);
    assert.match(bound.selection_revision, /^[a-f0-9]{64}$/);
    assert.ok(bound.expected_next_key && bound.expected_next_members.length);
    const advertised = pile.items.find(i => i.key === bound.expected_next_members[0]);
    assert.equal(advertised?.title, shownNext, "request must name the displayed Next");
    assert.ok(advertised.tid, "selected synthetic agent must have durable task context");
    await request(h, "/api/fixture/processing/context", "POST", {
      task_id: advertised.tid, body: "Synthetic selected task context changed after the Next gesture",
    });
    const stale = page.waitForResponse(r => new URL(r.url()).pathname === "/api/concierge/stream"
      && r.status() === 409, { timeout: 15000 });
    await cdp.send("Fetch.continueRequest", { requestId: releaseId });
    await stale;
    await cdp.send("Fetch.disable");
    await page.waitForFunction(() => !document.querySelector(".tq-typing"), { timeout: 15000 });
    await page.waitForFunction(() => [...document.querySelectorAll("button")]
      .some(n => n.textContent.trim() === "Next" && !n.disabled), { timeout: 15000 });
    assert.equal(await title(page, "current"), heldCurrent);
    assert.deepEqual((await request(h, "/api/concierge")).messages, before);
    assert.equal(writes.length, beforeWrites + 1, "stale stream must not retry plain or auto-advance");

    const retryTitle = await title(page, "next");
    const done = page.waitForResponse(r => new URL(r.url()).pathname === "/api/concierge/stream"
      && r.status() === 200, { timeout: 15000 });
    await clickNext(page);
    const response = await done;
    const result = JSON.parse((await response.text()).trim().split("\n").at(-1));
    assert.equal(result.type, "done", JSON.stringify(result));
    const first = result.item.kind === "fyis" ? result.item.items[0] : result.item;
    assert.equal(first.title, retryTitle, "fresh explicit retry must consume the displayed Next");
    await page.waitForFunction(() => !document.querySelector(".tq-typing"), { timeout: 15000 });
    assert.equal(writes.length, beforeWrites + 2);
    assert.ok((await request(h, "/api/concierge")).messages.length > before.length);
    const currentAfterRetry = await title(page, "current");
    const activeCard = () => page.$eval('.tq-msg .tq-card', node => ({
      title: node.querySelector('.tq-card-title')?.textContent.trim(),
      buttons: [...node.querySelectorAll('button')].map(button => button.textContent.trim()),
    }));
    const originalControls = await activeCard();
    assert.ok(originalControls.buttons.length, 'selected agent must have live controls');
    const passive = pile.items.find(i => i.kind === "agent" && i.tid && i.title !== currentAfterRetry);
    assert.ok(passive, "passive notice must name a different synthetic agent");
    const noticeRead = page.waitForResponse(async r => {
      if (new URL(r.url()).pathname !== "/api/concierge" || r.status() !== 200) return false;
      try {
        return (await r.json()).messages.some(m => m.card?.background_event && m.card.key === passive.key);
      } catch { return false; }
    }, { timeout: 15000 });
    await request(h, "/api/fixture/processing/background", "POST", { task_id: passive.tid });
    await noticeRead;
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    assert.equal(await title(page, "current"), currentAfterRetry);
    assert.deepEqual(await activeCard(), originalControls, 'passive notice must not steal interactive controls');
    await page.reload({ waitUntil: "domcontentloaded", timeout: 20000 });
    await page.waitForSelector(".tq-pile-row.current .card", { timeout: 15000 });
    assert.equal(await title(page, "current"), currentAfterRetry,
      "restoring tagged passive history must retain the explicit owner subject");
    assert.deepEqual(await activeCard(), originalControls, 'restored controls must still target Current');
    assert.equal(writes.length, beforeWrites + 2, "passive notice and reload must not navigate");
    assert.deepEqual(errors, []);
    assert.deepEqual(page.fixtureEscapes, []);
  } finally {
    await cdp.send("Fetch.disable").catch(() => {});
    await cdp.detach().catch(() => {});
  }
});
