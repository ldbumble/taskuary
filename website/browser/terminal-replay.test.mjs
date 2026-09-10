import assert from "node:assert/strict";
import test from "node:test";

import { bodyText, startHarness } from "./harness.mjs";

async function waitUntil(predicate, timeout = 5000) {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (predicate()) return;
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
  throw new Error("timed out waiting for terminal websocket frames");
}

test("P0-BROWSER terminal replay becomes visible and accepts fixture input", { timeout: 120000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const session = await page.createCDPSession();
  await session.send("Network.enable");
  const sentFrames = [];
  const receivedFrames = [];
  session.on("Network.webSocketFrameSent", ({ response }) => sentFrames.push(response.payloadData));
  session.on("Network.webSocketFrameReceived", ({ response }) => receivedFrames.push(response.payloadData));

  const replayStarted = performance.now();
  await page.goto(`${harness.ui}/#task=4`, { waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector(".xterm-helper-textarea", { timeout: 15000 });
  await page.waitForFunction(() => !document.body.innerText.includes("restoring the session"), { timeout: 10000 });
  const rendered = await bodyText(page);
  assert.equal(rendered.includes("closed"), false, "fixture terminal websocket closed during replay");
  assert.ok(receivedFrames.some((frame) => {
    try { return JSON.parse(frame).type === "ready"; } catch { return false; }
  }), "terminal replay did not reach its ready barrier");
  assert.ok(receivedFrames.some((frame) => {
    try { const message = JSON.parse(frame); return message.type === "out" && message.replay === true; } catch { return false; }
  }), "terminal websocket did not identify its initial output as replay");
  assert.match(await page.$eval(".xterm-rows", (node) => node.textContent), /month-end difference|gl_export/,
    "replayed terminal content was not visibly rendered");
  const replayVisibleMs = Math.round(performance.now() - replayStarted);
  assert.ok(replayVisibleMs <= 10000, `terminal replay took ${replayVisibleMs}ms to become visible`);

  const inputStarted = performance.now();
  await page.click(".xterm-helper-textarea");
  await page.keyboard.type("phase-zero-terminal-input");
  const typed = () => sentFrames.flatMap((frame) => {
    try {
      const message = JSON.parse(frame);
      return message.type === "in" ? [message.data] : [];
    } catch {
      return [];
    }
  }).join("");
  await waitUntil(() => typed().includes("phase-zero-terminal-input"));
  const inputEmissionMs = Math.round(performance.now() - inputStarted);
  assert.ok(typed().includes("phase-zero-terminal-input"), "typed terminal input was not emitted over the fixture websocket");
  assert.ok(inputEmissionMs <= 1500, `terminal input emission took ${inputEmissionMs}ms`);

  const readyBeforeReload = receivedFrames.filter((frame) => {
    try { return JSON.parse(frame).type === "ready"; } catch { return false; }
  }).length;
  const reconnectStarted = performance.now();
  await page.reload({ waitUntil: "domcontentloaded", timeout: 20000 });
  await page.waitForSelector(".xterm-helper-textarea", { timeout: 15000 });
  await page.waitForFunction(() => !document.body.innerText.includes("restoring the session"), { timeout: 10000 });
  await waitUntil(() => receivedFrames.filter((frame) => {
    try { return JSON.parse(frame).type === "ready"; } catch { return false; }
  }).length > readyBeforeReload);
  const readyAfterReload = receivedFrames.filter((frame) => {
    try { return JSON.parse(frame).type === "ready"; } catch { return false; }
  }).length;
  const reconnectMs = Math.round(performance.now() - reconnectStarted);
  assert.ok(readyAfterReload > readyBeforeReload, "terminal reconnect did not reach a new ready barrier");
  assert.ok(reconnectMs <= 10000, `terminal reconnect took ${reconnectMs}ms`);
  assert.match(await page.$eval(".xterm-rows", (node) => node.textContent), /month-end difference|gl_export/,
    "terminal reconnect did not visibly restore replay content");
  assert.deepEqual(page.fixtureEscapes, [], `browser attempted non-fixture requests: ${page.fixtureEscapes.join(", ")}`);
  t.diagnostic(JSON.stringify({ fixture: "actual Taskuary --demo Replay; no PTY/worker; fixture intentionally ignores input",
    sentFrames: sentFrames.length, receivedFrames: receivedFrames.length, reconnectReady: readyAfterReload,
    timings: { replayVisibleMs, inputEmissionMs, reconnectMs } }));
});
