import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { settleDemoWatcher, waitForDemoReplays } from "./processing-fixtures.mjs";

const request = async (harness, path, method = "GET", body) => {
  const response = await fetch(`${harness.fixtureApi}${path}`, {
    method,
    headers: { "X-Taskuary-Token": harness.token, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(`${method} ${path} failed ${response.status}: ${JSON.stringify(data)}`);
  return data;
};

const clickState = async (page, label) => {
  const handles = await page.$$('[role="group"][aria-label="Feed views"] *');
  for (const handle of handles) {
    if (await handle.evaluate((node, wanted) => node.children.length === 0
      && node.textContent.trim().toLowerCase() === wanted
      && node.getBoundingClientRect().width > 0, label)) {
      await handle.click(); return;
    }
  }
  assert.fail(`visible ${label} feed view was not found`);
};

const clickItem = async (page, itemId) => {
  const rows = await page.$$('[data-processing-item]');
  for (const row of rows) {
    if (await row.evaluate((node, wanted) => node.dataset.processingItem === wanted, itemId)) {
      const target = await row.$("[data-tq-open]");
      assert.ok(target, `${itemId} has no open target`);
      await target.click(); return;
    }
  }
  assert.fail(`canonical item ${itemId} was not rendered`);
};

const chooseOption = async (page, ariaLabel, label) => {
  await page.click(`[aria-label="${ariaLabel}"]`);
  await page.waitForSelector('[role="option"]', { visible: true, timeout: 5000 });
  const options = await page.$$('[role="option"]');
  for (const option of options) {
    if (await option.evaluate((node, wanted) => node.textContent.trim() === wanted, label)) {
      await option.click(); return;
    }
  }
  assert.fail(`${ariaLabel} option ${label} was not found`);
};

const chooseSource = (page, label) => chooseOption(page, "Timeline source", label);

const rowIds = (page) => page.$$eval("[data-processing-item]", (rows) => rows.map((row) => row.dataset.processingItem));

const stageContent = (page) => page.$eval("[data-tq-timeline-stage]", (stage) => [
  stage.innerText,
  ...[...stage.querySelectorAll("input, textarea")].map((node) => node.value),
].join("\n"));

const waitForStageMarker = (page, marker) => page.waitForFunction((wanted) => {
  const stage = document.querySelector("[data-tq-timeline-stage]");
  return stage && [stage.innerText, ...[...stage.querySelectorAll("input, textarea")].map((node) => node.value)]
    .join("\n").includes(wanted);
}, { timeout: 10000 }, marker);

async function drainCanonicalAll(page, minimum) {
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const ids = await rowIds(page);
    if (ids.length >= minimum && !await page.$("[data-processing-all-loading]")) return ids;
    await page.$eval('[data-processing-all-rail="true"]', (rail) => { rail.scrollTop = rail.scrollHeight; });
    await page.waitForFunction((before) => {
      const n = document.querySelectorAll("[data-processing-item]").length;
      return n > before || !document.querySelector("[data-processing-all-loading]");
    }, { timeout: 5000 }, ids.length).catch(() => {});
  }
  return rowIds(page);
}

test("canonical All renders every root once with truthful details and frozen pages", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const replays = await waitForDemoReplays(harness);
  await settleDemoWatcher(harness, replays);

  const page = await harness.newPage();
  const errors = [];
  const traffic = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("request", (entry) => {
    const url = new URL(entry.url());
    if (url.origin === harness.ui) traffic.push({ method: entry.method(), path: url.pathname, search: url.search });
  });
  const automaticWrites = () => traffic.filter(({ method, path }) => method !== "GET"
    && (path.startsWith("/api/concierge") || path === "/api/funnel/settle"
      || /^\/api\/(messages|reviews)\//.test(path)));

  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector(".tq-pile-row.next .tq-pile-next", { timeout: 10000 });
  await page.evaluate(() => [...document.querySelectorAll("button")]
    .find((button) => button.innerText === "Walk me through my tasks")?.click());
  await page.waitForSelector(".tq-pile-row.current .tq-pile-next.cur", { timeout: 15000 });
  await page.waitForFunction(() => !document.querySelector(".tq-typing"), { timeout: 15000 });
  const current = await page.$eval(".tq-pile-row.current .card b", (node) => node.textContent.trim());
  const seed = await request(harness, "/api/fixture/processing/canonical-all", "POST", { count: 507 });
  assert.ok(seed.total >= 507, "fixture must retain demo roots and add at least 507 canonical roots");
  // Reload so the real source and calendar discovery requests observe the new fixture, while
  // proving that a canonical reconciliation cannot replace the already established Current.
  await page.reload({ waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector(".tq-pile-row.current .tq-pile-next.cur", { timeout: 10000 });
  assert.equal(await page.$eval(".tq-pile-row.current .card b", (node) => node.textContent.trim()), current,
    "canonical fixture reconciliation must preserve the durable Current across reload");

  await clickState(page, "all");
  await page.waitForSelector("[data-processing-item] [data-tq-open]", { timeout: 15000 });
  assert.equal(await page.$(".tq-pile-row"), null, "All remains a detail-only canonical rail");
  assert.equal(await page.$(".tq-compose"), null, "All must not mount assistant chat");
  const writesAtAll = automaticWrites().length;

  const firstIds = await rowIds(page);
  assert.equal(new Set(firstIds).size, firstIds.length, "the first page must contain one row per canonical root");
  for (const root of Object.values(seed.standalone)) assert.ok(firstIds.includes(root.item_id), `${root.item_id} standalone root is missing`);
  assert.equal(firstIds.filter((id) => id === seed.grouped.item_id).length, 1, "a grouped task must render as one root row");
  assert.equal(await page.$eval(`[data-processing-item="${seed.grouped.item_id}"]`, (node) => Number(node.dataset.processingMembers)),
    seed.grouped.member_count, "the grouped root must expose its complete canonical member count");

  await clickItem(page, seed.grouped.item_id);
  await waitForStageMarker(page, seed.grouped.sibling_draft_marker);
  const latestStage = await stageContent(page);
  assert.equal(latestStage.includes(seed.grouped.selected_draft_marker), false,
    "the older member draft must not leak into the default latest-member detail");
  assert.equal(automaticWrites().length, writesAtAll, "opening exact message detail must not write state");

  await chooseSource(page, seed.grouped.source_nonrepresentative);
  await page.waitForFunction((itemId, mid) => {
    const row = [...document.querySelectorAll("[data-processing-item]")].find((node) => node.dataset.processingItem === itemId);
    return row?.dataset.processingTarget === `message:${mid}`;
  }, { timeout: 10000 }, seed.grouped.item_id, seed.grouped.message_ids[0]);
  assert.equal((await rowIds(page)).filter((id) => id === seed.grouped.item_id).length, 1,
    "source filtering must retain the root once and target its matching member");
  await clickItem(page, seed.grouped.item_id);
  await waitForStageMarker(page, seed.grouped.full_body_marker);
  const olderStage = await stageContent(page);
  assert.ok(olderStage.includes(seed.grouped.selected_draft_marker), "the filtered member's exact draft must be visible");
  assert.equal(olderStage.includes(seed.grouped.sibling_draft_marker), false, "the latest sibling draft must not leak into older detail");

  const ownerDraft = "owner is still typing this canonical draft";
  const draftBoxes = await page.$$("textarea");
  let draftBox = null;
  for (const box of draftBoxes) {
    if ((await box.evaluate((node) => node.value)).includes(seed.grouped.selected_draft_marker)) { draftBox = box; break; }
  }
  assert.ok(draftBox, "the selected member's exact pending draft must be editable");
  await draftBox.focus();
  await page.keyboard.down("Control"); await page.keyboard.press("A"); await page.keyboard.up("Control");
  await page.keyboard.type(ownerDraft);
  const refreshedDetail = page.waitForResponse((response) => new URL(response.url()).pathname
    === `/api/processing/items/${seed.grouped.item_id}/detail`, { timeout: 10000 });
  await request(harness, "/api/fixture/processing/draft", "POST", {
    review_id: seed.grouped.selected_review_id, body: "backend changed while owner typed",
  });
  const refreshedResponse = await refreshedDetail;
  await refreshedResponse.buffer();
  await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  await page.waitForFunction((wanted) => [...document.querySelectorAll("textarea")]
    .some((node) => node.value === wanted), { timeout: 10000 }, ownerDraft);

  await chooseSource(page, "all sources");
  await page.waitForFunction((itemId, mid) => {
    const row = [...document.querySelectorAll("[data-processing-item]")].find((node) => node.dataset.processingItem === itemId);
    return row?.dataset.processingTarget === `message:${mid}`;
  }, { timeout: 10000 }, seed.grouped.item_id, seed.grouped.message_ids.at(-1));

  for (const kind of ["task", "idea", "review"]) {
    const root = seed.standalone[kind];
    await clickItem(page, root.item_id);
    await page.waitForSelector(`[data-processing-generic-detail][data-processing-detail-kind="${kind}"]`, { timeout: 10000 });
    assert.ok((await page.$eval("[data-processing-generic-detail]", (node) => node.innerText)).includes(root.body_marker),
      `${kind} full persisted body was not rendered`);
  }
  const writesAfterIntentionalDraft = automaticWrites().length;
  assert.ok(writesAfterIntentionalDraft >= writesAtAll, "the explicit draft edit may save when its field loses focus");

  await chooseOption(page, "Timeline category", "email");
  await page.waitForFunction((itemId) => [...document.querySelectorAll("[data-processing-item]")]
    .some((node) => node.dataset.processingItem === itemId), { timeout: 10000 }, seed.grouped.item_id);
  assert.equal((await rowIds(page)).includes(seed.standalone.idea.item_id), false,
    "the server category filter must not leak an assistant idea into email");
  await chooseOption(page, "Timeline category", "all kinds");
  await page.waitForFunction((itemId) => [...document.querySelectorAll("[data-processing-item]")]
    .some((node) => node.dataset.processingItem === itemId), { timeout: 10000 }, seed.standalone.idea.item_id);

  const arrival = await request(harness, "/api/fixture/processing/canonical-arrival", "POST", { emit: false });
  // The API count includes the single calendar-prep root. FeedView deliberately nests that row
  // beneath its calendar event instead of rendering it a second time in the rail.
  const expectedRailCount = seed.total - 1;
  const frozenIds = await drainCanonicalAll(page, expectedRailCount);
  assert.equal(frozenIds.length, expectedRailCount,
    `the frozen rail must render every API root except the nested calendar prep (${expectedRailCount})`);
  assert.equal(new Set(frozenIds).size, frozenIds.length, "frozen pages must concatenate without duplicates");
  assert.equal(frozenIds.includes(arrival.item_id), false, "a concurrent arrival must not enter the old frozen lease");
  assert.ok(traffic.some(({ path, search }) => path === "/api/processing/all" && new URLSearchParams(search).has("cursor")),
    "the rendered rail must request an opaque continuation page");

  await request(harness, "/api/fixture/processing/canonical-emit", "POST");
  await page.waitForFunction((itemId) => [...document.querySelectorAll("[data-processing-item]")]
    .some((node) => node.dataset.processingItem === itemId), { timeout: 10000 }, arrival.item_id);
  assert.equal((await rowIds(page)).filter((id) => id === arrival.item_id).length, 1,
    "a fresh lease must show the new arrival once");

  const body = await page.$eval("body", (node) => node.innerText);
  assert.ok(body.includes(seed.calendar.upcoming), "the unfiltered All calendar banner must retain an upcoming event");
  assert.ok(body.includes(seed.calendar.started), "the unfiltered All calendar banner must retain a started event");
  assert.equal(body.split(seed.calendar.prep).length - 1, 1, "calendar prep must render once under its event");
  assert.ok([seed.ignored_item_id, seed.muted_item_id].every((id) => firstIds.includes(id)),
    "ignored and standing-rule-muted roots must remain visible in All");

  await clickState(page, "unread");
  await page.waitForSelector(".tq-pile-row.current .tq-pile-next.cur", { timeout: 10000 });
  assert.equal(await page.$eval(".tq-pile-row.current .card b", (node) => node.textContent.trim()), current,
    "canonical All must not change Current");
  assert.equal(automaticWrites().length, writesAfterIntentionalDraft,
    "All/filter/pagination/tab return must not add automatic state writes");
  assert.deepEqual(errors, []);
  assert.deepEqual(page.fixtureEscapes, []);
});
