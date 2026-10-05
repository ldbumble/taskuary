import assert from "node:assert/strict";
import test from "node:test";
import { startHarness } from "./harness.mjs";

test("first-run read waits for completion, displays five results and preserves source errors", { timeout: 120000 }, async (t) => {
  const harness = await startHarness(); t.after(() => harness.close());
  const page = await harness.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let reads = 0, running = true, failed = false;
  const items = Array.from({ length: 6 }, (_, n) => ({ MessageId: 900 + n, Subject: `Invented result ${n + 1}`, Channel: "email" }));
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname; let data;
    if (path === "/api/ingest/poll") { reads += 1; data = { report: "running" }; }
    if (path === "/api/ingest/status") data = { status: { state: running ? "running" : "idle" }, failed: failed ? ["gmail"] : [], triageError: failed ? "The AI key was rejected." : "" };
    if (path === "/api/setup") data = { steps: [{ key: "sync", done: !running }], pending: false, first_items: running ? [] : items };
    if (data) return request.respond({ status: 200, contentType: "application/json", body: JSON.stringify(data) });
    page.fixtureRequestGuard(request);
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded" });
  await page.evaluate(async () => {
    const [{ FirstSync }, React, client] = await Promise.all([
      import("/src/SetupWizard.jsx"), import("/node_modules/.vite/deps/react.js"), import("/node_modules/.vite/deps/react-dom_client.js"),
    ]);
    const createRoot = client.createRoot || client.default.createRoot;
    const createElement = React.createElement || React.default.createElement;
    const fixture = document.createElement("div"); fixture.id = "first-run-fixture";
    document.body.append(fixture);
    createRoot(fixture).render(createElement(FirstSync, { enabled: true, ready: false }));
  });
  const click = async () => page.$eval("#first-run-fixture button", (button) => button.click());
  await page.waitForSelector("#first-run-fixture button"); await click();
  await page.waitForFunction(() => document.querySelector("#first-run-fixture")?.textContent.includes("Reading your connected sources"));
  assert.equal(reads, 1);
  assert.equal(await page.$eval("#first-run-fixture button", (button) => button.disabled), true);
  assert.doesNotMatch(await page.$eval("#first-run-fixture", (el) => el.innerText), /Your first items are ready/);
  running = false;
  await page.waitForFunction(() => document.querySelector("#first-run-fixture")?.textContent.includes("Your first items are ready"));
  const text = await page.$eval("#first-run-fixture", (el) => el.innerText);
  assert.match(text, /Invented result 5/i); assert.doesNotMatch(text, /Invented result 6/i);
  assert.match(text, /normal import scope|ready/);
  failed = true; await click();
  await page.waitForFunction(() => document.querySelector("#first-run-fixture [role=alert]")?.textContent.includes("AI key was rejected"));
  assert.match(await page.$eval("#first-run-fixture [role=alert]", (el) => el.innerText), /gmail/);
  assert.equal(reads, 2);
  assert.deepEqual(errors, []);
});
