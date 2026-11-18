import assert from "node:assert/strict";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { startHarness } from "./harness.mjs";
import { record } from "./recorder.mjs";

/* A REMOVED CONNECTION IS NEVER DRAWN AS IT WAS (the stress round, 2026-11-18): a Mastodon card whose Test had failed was removed from its own
   page - and the list it went back to drew it "connection failing", red, for half a second before it read "not set up". The list was the one
   read before the Remove; the press left the card first and read the list after. Every frame from the confirm is read: the removed card on the
   list is only ever the wiped one. Invented people only. */
const out = path.join(process.env.TEMP || os.tmpdir(), "claude", "remove-stale");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

test("a connection removed from its page goes back to a list that already says it is wiped", { timeout: 300000 }, async (t) => {
  const h = await startHarness({ fresh: true });
  t.after(() => h.close());
  const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token }, body: body && JSON.stringify(body) }).then((r) => r.json());
  await api("/api/setup/dismiss", { dismissed: true });
  const c = (await api("/api/connectors")).data.find((x) => x.Type === "mastodon");
  await api("/api/connectors", { ConnectorId: c.ConnectorId, ConfigPatch: { base_url: "https://social.example" } });
  const tested = await api(`/api/connectors/${c.ConnectorId}/test`, {});
  assert.equal(tested.ok, false);                                     // no token: the card is failing, as the owner left it
  const page = await h.newPage();
  await page.setViewport({ width: 1500, height: 900 });
  const errors = []; page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(h.ui, { waitUntil: "domcontentloaded" });
  await sleep(1500);
  await page.evaluate((id) => { location.hash = `connector=${id}`; }, String(c.ConnectorId));
  const button = async (re, scope = "") => {
    for (const b of await page.$$(`${scope} button`)) if (re.test(await b.evaluate((e) => e.innerText.trim()))) return b;
    return null;
  };
  for (let i = 0; i < 60 && !(await button(/^Remove connection$/)); i++) await sleep(250);
  const rec = await record(page, path.join(out, "video"));
  await (await button(/^Remove connection$/)).click();
  await page.waitForSelector('[role="dialog"]', { visible: true });
  // every committed state from the confirm: what the list says of the Mastodon card, while it is drawn
  await page.evaluate(() => {
    window.__seen = [];
    const read = () => {
      const card = [...document.querySelectorAll("[data-tq-browse-card], [role=button], div")].find((d) => /^Mastodon\n/.test(d.innerText || "") && d.innerText.length < 200);
      const s = card ? card.innerText.replace(/\s+/g, " ").trim() : "";
      if (window.__seen.at(-1) !== s) window.__seen.push(s);
    };
    new MutationObserver(read).observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true });
  });
  await (await button(/^Remove$/, '[role="dialog"]')).click();
  for (let i = 0; i < 40 && !(await button(/^Undo$/)); i++) await sleep(250);
  await sleep(1500);
  await rec.stop();
  const seen = (await page.evaluate(() => window.__seen)).filter(Boolean);
  assert.ok(seen.length, "the list was drawn after the Remove");
  assert.deepEqual(seen.filter((s) => /failing/.test(s)), [], `the removed card was drawn as it was: ${JSON.stringify(seen)}`);
  assert.match(seen.at(-1), /not set up/);
  assert.deepEqual(errors, []);
});
