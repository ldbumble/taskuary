import assert from "node:assert/strict";
import test from "node:test";

import { clickNav, startHarness } from "./harness.mjs";

const CHAT_CARDS = [
  ["teams", "Microsoft Teams", /every chat this connector brings in/i],
  ["slack", "Slack", /every chat this connector brings in/i],
  ["telegram", "Telegram", /every chat this connector brings in/i],
  ["whatsapp", "WhatsApp", /inbound messages from every chat/i],
  ["imessage", "Apple Messages", /every chat Messages\.app brings in/i],
  ["discord", "Discord", /every chat this connector brings in/i],
];

const fieldLabel = "Check for new messages every N seconds (blank = 30, 0 = no fast polling)";

async function clickVisibleExact(page, text, selector = "div,p,span") {
  const clicked = await page.evaluate(({ wanted, query }) => {
    const candidates = [...document.querySelectorAll(query)].filter((node) => {
      const box = node.getBoundingClientRect();
      return node.textContent.trim() === wanted && box.width > 0 && box.height > 0;
    });
    const node = candidates.find((candidate) => getComputedStyle(candidate).cursor === "pointer") || candidates[0];
    node?.click();
    return Boolean(node);
  }, { wanted: text, query: selector });
  assert.equal(clicked, true, `visible control not found: ${text}`);
}

async function fixtureState(page) {
  return page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token") };
    const [connectors, settings] = await Promise.all([
      fetch("/api/connectors", { headers }).then((response) => response.json()),
      fetch("/api/settings", { headers }).then((response) => response.json()),
    ]);
    return { connectors: connectors.data, settings: settings.data };
  });
}

test("PW-003/PW-004/PW-005 render the six chat clocks and global off help read-only", { timeout: 120000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());

  const page = await harness.newPage();
  const pageErrors = [];
  const writes = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (url.origin === harness.ui && !["GET", "HEAD", "OPTIONS"].includes(request.method())) {
      writes.push(`${request.method()} ${url.pathname}`);
    }
  });

  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 20000 });
  const demo = await page.evaluate(async () => (await fetch("/api/demo", {
    headers: { "X-Taskuary-Token": localStorage.getItem("taskuary_token") },
  })).json());
  assert.equal(demo.demo, true);

  const before = await fixtureState(page);
  const seeded = before.connectors
    .filter((connector) => CHAT_CARDS.some(([type]) => type === connector.Type))
    .map((connector) => [connector.Type, connector.Name]);
  assert.deepEqual(seeded, CHAT_CARDS.map(([type, name]) => [type, name]),
    "the isolated store supplies the six invented connector cards under test");

  await clickNav(page, "Connections");
  await page.waitForSelector('input[placeholder^="Search connectors"]', { timeout: 10000 });
  await clickVisibleExact(page, "Messaging");
  await page.waitForFunction(() => document.body.innerText.includes("Apple Messages"), { timeout: 10000 });

  const rendered = [];
  for (const [, name, coverage] of CHAT_CARDS) {
    await clickVisibleExact(page, name, "p");
    await page.waitForSelector('input[placeholder="30"]', { timeout: 5000 });
    const field = await page.$eval('input[placeholder="30"]', (input) => {
      const control = input.closest(".MuiFormControl-root");
      return {
        value: input.value,
        label: control?.querySelector("label")?.textContent?.trim() || "",
        helper: control?.querySelector(".MuiFormHelperText-root")?.textContent?.trim() || "",
      };
    });
    rendered.push(`${field.label} ${field.helper}`);
    assert.equal(field.value, "", `${name}: the synthetic blank value stays blank`);
    assert.equal(field.label, fieldLabel, `${name}: the visible field states default and zero`);
    assert.match(field.helper, coverage, `${name}: connector intake coverage is visible`);
    assert.match(field.helper, /recurring fast clock is separate from the full background-sync clock/i, name);
    assert.match(field.helper, /Blank uses 30 seconds/i, name);
    assert.match(field.helper, /0 disables this fast poll/i, name);
    assert.match(field.helper, /recurring background sync can still poll the connector/i, name);
    assert.match(field.helper, /manual Sync now, action-time freshness checks, and startup catch-up can still fetch it/i, name);
    assert.match(field.helper, /Background sync 0 in Settings disables both recurring clocks/i, name);
    assert.match(field.helper, /explicit and startup fetches remain available/i, name);
    if (name === "WhatsApp") {
      assert.match(field.helper, /replies in the notification chat are polled too/i);
      assert.match(field.helper, /sending notifications is event-driven/i);
    }

    await clickVisibleExact(page, "Connections", "span");
    await page.waitForSelector('input[placeholder^="Search connectors"]', { timeout: 5000 });
    await clickVisibleExact(page, "Messaging");
  }

  const renderedCopy = rendered.join("\n");
  assert.doesNotMatch(renderedCopy, /Check assistant chat every N seconds/i);
  assert.doesNotMatch(renderedCopy, /blank = the global sync interval/i);
  assert.doesNotMatch(renderedCopy, /Only (WhatsApp|this connector) polls faster/i);
  assert.doesNotMatch(renderedCopy, /never holds a chat back/i);

  await clickNav(page, "Settings");
  await page.waitForSelector('input[placeholder^="Search settings"]', { timeout: 10000 });
  await clickVisibleExact(page, "Configuration");
  await page.waitForFunction(() => document.body.innerText.includes("Triage & routing"), { timeout: 5000 });
  await clickVisibleExact(page, "Sync & startup");
  await page.waitForFunction(() => document.body.innerText.includes("Background sync (minutes)"), { timeout: 5000 });

  const backgroundValue = await page.evaluate(() => {
    const label = [...document.querySelectorAll("p")]
      .find((node) => node.textContent.trim() === "Background sync (minutes)");
    return label?.parentElement?.parentElement?.querySelector('input[type="number"]')?.value ?? null;
  });
  assert.equal(backgroundValue, "10", "the isolated store renders the global ten-minute default");
  await clickVisibleExact(page, "Background sync (minutes)", "p");
  await page.waitForSelector('[role="dialog"]', { timeout: 5000 });
  const help = await page.$eval('[role="dialog"]', (node) => node.innerText);
  assert.match(help, /10 is the default/i);
  assert.match(help, /0 turns recurring background polling off/i);
  assert.match(help, /Sync now, startup catch-up, and an action that must refresh chat context can still fetch/i);
  assert.match(help, /Teams, Slack, Telegram, WhatsApp, iMessage, Discord/);
  assert.match(help, /separate recurring fast clock - every 30 seconds unless their card says otherwise/i);
  assert.match(help, /0 here disables both recurring clocks/i);
  assert.match(help, /manual Sync now, startup catch-up, and action-time refreshes remain available/i);

  const after = await fixtureState(page);
  assert.deepEqual(after, before, "opening connector fields and help must not change fixture state");
  assert.deepEqual(writes, [], "the rendered read-only check must not save, sync, test, or edit anything");
  assert.deepEqual(pageErrors, []);
  assert.deepEqual(page.fixtureEscapes, []);
});
