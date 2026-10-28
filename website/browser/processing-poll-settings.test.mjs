import assert from "node:assert/strict";
import test from "node:test";

import { clickNav, startHarness } from "./harness.mjs";

const CHAT_CARDS = [
  ["teams", "Microsoft Teams"], ["slack", "Slack"], ["telegram", "Telegram"],
  ["whatsapp", "WhatsApp"], ["imessage", "Apple Messages"], ["discord", "Discord"],
];

// one short label and one line of hint, folded under Advanced after the token (the setup sweep, 2026-10-28): the label was cut off
// and a five-line hint led Credentials. Settings' Background sync help (below) keeps the full story
const fieldLabel = "Check for new messages every (seconds)";
const fieldHelp = "Blank = 30; 0 = no fast check (background sync and Sync now still read it).";

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

// A chip or a card opening smooth-scrolls the browse frame into view, and page.click() aims at coordinates taken before
// the scroll ends - the click landed beside the button about one run in four and the test waited out its timeout
// (CI, 2026-10-01). A DOM click is not aimed.
const press = (page, selector) => page.$eval(selector, (node) => node.click());

async function fixtureState(page) {
  return page.evaluate(async () => {
    const headers = { "X-Taskuary-Token": localStorage.getItem("taskuary_token") };
    const [connectors, settings] = await Promise.all([
      fetch("/api/connectors", { headers }).then((response) => response.json()),
      fetch("/api/settings", { headers }).then((response) => response.json()),
    ]);
    // The models page records "you have looked at the defaults" the moment it mounts (AiDefaults ->
    // /api/setup/seen, the checklist's one stored step, 5b5d4c33). That is a bookkeeping mark about the
    // visit itself, not fixture state the help or a connector field could have changed - so it is not
    // part of what "read-only" compares.
    return { connectors: connectors.data, settings: settings.data.filter((s) => s.Name !== "setup_seen_models") };
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
    // the models page's "you have looked at the defaults" mark (AiDefaults -> /api/setup/seen) is the
    // visit recording itself, not a save, sync, test or edit - see fixtureState above; so is the page noting the owner
    // sat down or left (/api/concierge/arrive, welcome.arrive)
    if (url.origin === harness.ui && !["GET", "HEAD", "OPTIONS"].includes(request.method())
      && !["/api/setup/seen", "/api/concierge/arrive"].includes(url.pathname)) {
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
  // the canvas (0.3.7.0): a section is its chip, and Back returns to that section's cards
  await press(page, '[data-tq-browse-chip="Messaging"]');
  await page.waitForFunction(() => document.body.innerText.includes("Apple Messages"), { timeout: 10000 });

  const rendered = [];
  for (const [, name] of CHAT_CARDS) {
    await clickVisibleExact(page, name, "p");
    await page.waitForSelector('input[placeholder="30"]', { timeout: 5000 });
    const field = await page.$eval('input[placeholder="30"]', (input) => {
      const control = input.closest(".MuiFormControl-root");
      return {
        value: input.value,
        label: control?.querySelector("label")?.textContent?.trim() || "",
        helper: control?.querySelector(".MuiFormHelperText-root")?.textContent?.trim() || "",
        advanced: !!input.closest("[data-tq-advanced-fold]"),
      };
    });
    rendered.push(`${field.label} ${field.helper}`);
    assert.equal(field.value, "", `${name}: the synthetic blank value stays blank`);
    assert.equal(field.label, fieldLabel, `${name}: the visible field states default and zero`);
    assert.equal(field.helper, fieldHelp, `${name}: one line says blank, zero and what still reads it`);
    assert.equal(field.advanced, true, `${name}: the clock is under Advanced, after the token`);

    await press(page, "[data-tq-browse-back]");
    // the list is back when the open card is gone - "Apple Messages" alone is also the title of that card while it is open
    await page.waitForFunction(() => !document.querySelector("[data-tq-browse-one]")
      && document.body.innerText.includes("Apple Messages"), { timeout: 5000 });
  }

  const renderedCopy = rendered.join("\n");
  assert.doesNotMatch(renderedCopy, /Check assistant chat every N seconds/i);
  assert.doesNotMatch(renderedCopy, /blank = the global sync interval/i);
  assert.doesNotMatch(renderedCopy, /Only (WhatsApp|this connector) polls faster/i);
  assert.doesNotMatch(renderedCopy, /never holds a chat back/i);

  await clickNav(page, "Settings");
  await page.waitForSelector('input[placeholder^="Search settings"]', { timeout: 10000 });
  await press(page, '[data-tq-browse-chip="config"]');
  await page.waitForFunction(() => document.body.innerText.includes("How mail is sorted"), { timeout: 5000 });
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
