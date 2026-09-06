import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { waitForDemoReplays, settleDemoWatcher } from "./processing-fixtures.mjs";

const fixtureRequest = async (harness, path, method = "GET", body) => {
  const response = await fetch(`${harness.fixtureApi}${path}`, {
    method,
    headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  assert.ok(response.ok, `${method} ${path}: ${response.status} ${response.ok ? "" : await response.text()}`);
  return response.json();
};

const currentTitle = (page) => page.$eval(".tq-pile-row.current .card b", (node) => node.textContent.trim());
const currentDraft = (page) => page.$eval(".tq-msg .tq-card textarea", (node) => node.value);
const waitDraft = (page, text) => page.waitForFunction((wanted) =>
  [...document.querySelectorAll(".tq-msg .tq-card textarea")].some((node) => node.value === wanted),
{ timeout: 15000 }, text);

const holdNextTaskResponse = async (page, taskId) => {
  const client = await page.createCDPSession();
  let resolveHeld;
  let rejectHeld;
  const held = new Promise((resolve, reject) => { resolveHeld = resolve; rejectHeld = reject; });
  let requestId;
  let networkId;
  const completed = new Set();
  const completionWaiters = new Map();
  client.on("Network.loadingFinished", ({ requestId: id }) => {
    completed.add(id);
    completionWaiters.get(id)?.();
  });
  await client.send("Network.enable");
  client.on("Fetch.requestPaused", async (event) => {
    try {
      if (!requestId) {
        requestId = event.requestId;
        networkId = event.networkId;
        assert.ok(networkId, "held response must have a network identity for delivery verification");
        const body = await client.send("Fetch.getResponseBody", { requestId });
        resolveHeld({ requestId, text: body.base64Encoded ? Buffer.from(body.body, "base64").toString() : body.body });
      } else {
        await client.send("Fetch.continueRequest", { requestId: event.requestId });
      }
    } catch (error) { rejectHeld(error); }
  });
  await client.send("Fetch.enable", {
    patterns: [{ urlPattern: `*/api/tasks/${taskId}`, requestStage: "Response" }],
  });
  return {
    held,
    release: async () => {
      if (requestId) {
        const delivered = new Promise((resolve, reject) => {
          if (completed.has(networkId)) { resolve(); return; }
          const timer = setTimeout(() => reject(new Error("released old response did not finish delivery")), 15000);
          completionWaiters.set(networkId, () => { clearTimeout(timer); resolve(); });
        });
        await client.send("Fetch.continueRequest", { requestId });
        await delivered;
      }
      await client.send("Fetch.disable");
      await client.detach();
    },
  };
};

test("PW-106 refreshes same-ID source and drafts while preserving Current and owner edits", { timeout: 150000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const sessions = await waitForDemoReplays(harness);
  assert.ok(sessions.some((row) => row.Title?.includes("census sync")));
  await settleDemoWatcher(harness, sessions);
  const initialPile = await fixtureRequest(harness, "/api/funnel/pile?force=1");
  const target = initialPile.items.find((item) => item.kind === "review" && item.rid && item.mid && item.tid);
  assert.ok(target, "fixture needs an actual grouped pending review");

  const page = await harness.newPage();
  const errors = [];
  const writes = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin === harness.ui && request.method() !== "GET"
      && (url.pathname.startsWith("/api/concierge") || url.pathname === "/api/funnel/settle")) {
      writes.push({ method: request.method(), path: url.pathname });
    }
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector(".tq-pile-row .card", { timeout: 15000 });
  const cards = await page.$$(".tq-pile-row .card");
  let picked = false;
  for (const card of cards) {
    if (await card.$eval("b", (node, title) => node.textContent.trim() === title, target.title)) {
      await card.click();
      picked = true;
      break;
    }
  }
  assert.ok(picked, "target is opened through the rendered Unread row");
  await page.waitForSelector(".tq-pile-row.current", { timeout: 15000 });
  await page.waitForSelector(".tq-msg .tq-card textarea", { timeout: 15000 });
  const heldTitle = await currentTitle(page);
  assert.equal(heldTitle, target.title);
  const afterOpen = writes.length;
  assert.ok(afterOpen > 0, "the intentional row open must create its assistant turn");
  const history = (await fixtureRequest(harness, "/api/concierge")).messages;
  assert.ok(history.some((turn) => turn.card?.key === target.key));

  const memberMarker = "Synthetic older member joins the same task context.";
  await fixtureRequest(harness, "/api/fixture/processing/member", "POST", {
    message_id: target.mid, body: memberMarker,
  });
  await page.waitForFunction((text) => [...document.querySelectorAll(".tq-card-full")]
    .some((node) => node.innerText.includes(text)), { timeout: 15000 }, memberMarker);
  const grouped = await fixtureRequest(harness, `/api/tasks/${target.tid}`);
  assert.ok(grouped.messages.filter((message) => message.Status !== "context").length >= 2,
    "the delayed response scenario must render combined task bodies, not a one-message fallback");
  assert.equal(await currentTitle(page), heldTitle);

  const draft = "Synthetic refreshed draft on the exact same review.";
  await fixtureRequest(harness, "/api/fixture/processing/draft", "POST", { review_id: target.rid, body: draft });
  await waitDraft(page, draft);
  assert.equal(await currentTitle(page), heldTitle);
  await fixtureRequest(harness, "/api/fixture/processing/draft", "POST", { review_id: target.rid, body: "" });
  await waitDraft(page, "");
  assert.equal(await currentDraft(page), "", "clearing a backend draft must clear the rendered old text");

  await page.waitForSelector(".tq-msg .tq-card-full", { visible: true, timeout: 10000 });
  const original = await fixtureRequest(harness, `/api/messages/${target.mid}`);
  const marker = "Synthetic same-ID source freshness marker.";
  await fixtureRequest(harness, "/api/fixture/processing/source", "POST", {
    message_id: target.mid, body: `${original.BodyText}\n\n${marker}`,
  });
  await page.waitForFunction((text) => [...document.querySelectorAll(".tq-card-full")]
    .some((node) => node.innerText.includes(text)), { timeout: 15000 }, marker);
  assert.equal(await currentTitle(page), heldTitle);

  // Hold an actual old task response after its body exists, let a newer response
  // render, then deliver the old one. Both requests still pass the harness guard.
  const delayed = await holdNextTaskResponse(page, target.tid);
  let released = false;
  try {
    const oldMarker = "Synthetic delayed obsolete source.";
    const newMarker = "Synthetic newest source wins the response race.";
    await fixtureRequest(harness, "/api/fixture/processing/source", "POST", {
      message_id: target.mid, body: oldMarker,
    });
    const held = await Promise.race([
      delayed.held,
      new Promise((_, reject) => setTimeout(() => reject(new Error("old task response was not held")), 15000)),
    ]);
    assert.ok(held.text.includes(oldMarker), "the delayed response must contain the obsolete real source");
    await fixtureRequest(harness, "/api/fixture/processing/source", "POST", {
      message_id: target.mid, body: newMarker,
    });
    await page.waitForFunction((text) => [...document.querySelectorAll(".tq-card-full")]
      .some((node) => node.innerText.includes(text)), { timeout: 15000 }, newMarker);
    await delayed.release();
    released = true;
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const sourceText = await page.$$eval(".tq-card-full", (nodes) => nodes.map((node) => node.innerText).join("\n"));
    assert.ok(sourceText.includes(newMarker));
    assert.ok(!sourceText.includes(oldMarker), "an obsolete response must not replace newer visible source");
    await fixtureRequest(harness, "/api/fixture/processing/source", "POST", {
      message_id: target.mid, body: "",
    });
    await page.waitForFunction((kept, removed) => [...document.querySelectorAll(".tq-card-full")]
      .some((node) => node.innerText.includes(kept) && !node.innerText.includes(removed)),
    { timeout: 15000 }, memberMarker, newMarker);
  } finally {
    if (!released) await delayed.release();
  }

  const editor = await page.$(".tq-msg .tq-card textarea");
  await editor.type("Owner unsaved synthetic wording", { delay: 10 });
  const refreshedReview = page.waitForResponse(async (response) => {
    if (new URL(response.url()).pathname !== "/api/reviews" || response.request().method() !== "GET") return false;
    const data = await response.json();
    return data.data?.some((review) => review.ReviewId === target.rid
      && review.DraftText === "Another saved draft from elsewhere");
  }, { timeout: 15000 });
  await fixtureRequest(harness, "/api/fixture/processing/draft", "POST", {
    review_id: target.rid, body: "Another saved draft from elsewhere",
  });
  // Wait for the changed presentation to reach this real page before asserting edit preservation.
  await (await refreshedReview).buffer();
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.equal(await currentDraft(page), "Owner unsaved synthetic wording");
  assert.equal(await currentTitle(page), heldTitle);
  assert.equal(writes.length, afterOpen, "freshness updates must not create turns or settle Current");
  assert.deepEqual((await fixtureRequest(harness, "/api/concierge")).messages, history);
  assert.deepEqual(errors, []);
  assert.deepEqual(page.fixtureEscapes, []);
});
