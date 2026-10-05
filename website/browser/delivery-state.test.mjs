import test from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { launch } from "../browser.mjs";

const website = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

test("uncertain delivery checks the original attempt and live claims freeze every mutation", { timeout: 60000 }, async () => {
  const port = await new Promise((resolve, reject) => {
    const server = net.createServer(); server.once("error", reject);
    server.listen(0, "127.0.0.1", () => { const port = server.address().port; server.close(() => resolve(port)); });
  });
  const origin = `http://127.0.0.1:${port}`;
  const vite = spawn(process.execPath, ["node_modules/vite/bin/vite.js", "--mode", "demo", "--host", "127.0.0.1", "--port", String(port), "--strictPort"],
    { cwd: website, windowsHide: true, stdio: ["ignore", "pipe", "pipe"] });
  let log = ""; vite.stdout.on("data", c => { log += c; }); vite.stderr.on("data", c => { log += c; });
  let browser;
  try {
    let ready = false;
    for (let n = 0; n < 100; n++) {
      if (vite.exitCode !== null) throw new Error(`Demo Vite exited: ${log}`);
      try { if ((await fetch(origin)).ok) { ready = true; break; } } catch { /* starting */ }
      await delay(100);
    }
    assert.ok(ready, `Demo Vite did not start: ${log}`);
    browser = await launch();
    const page = await browser.newPage(), errors = [], apiRequests = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setRequestInterception(true);
    page.on("request", request => {
      const url = new URL(request.url());
      if (url.origin === origin && url.pathname.startsWith("/api/")) apiRequests.push(url.pathname);
      if (["http:", "https:"].includes(url.protocol) && url.origin !== origin) request.abort(); else request.continue();
    });
    await page.goto(origin, { waitUntil: "networkidle0" });
    await page.evaluate(async () => {
      const { default: React } = await import("/node_modules/.vite/deps/react.js");
      const { default: ReactDOM } = await import("/node_modules/.vite/deps/react-dom_client.js");
      const { default: ReviewDecision } = await import("/src/ReviewDecision.jsx");
      const { useRowVerbs } = await import("/src/actionRow.js");
      const { default: api } = await import("/src/api.js");
      document.getElementById("root").style.display = "none";
      const host = document.createElement("div"); host.id = "delivery-fixture"; document.body.appendChild(host);
      window.deliveryCalls = [];
      api.post = async (url, body) => {
        window.deliveryCalls.push({ url, body });
        return { data: { ok: false, delivery: "unknown", send_error: "The provider has not confirmed the original attempt." } };
      };
      const attempted = { body: "Original owner-approved edited reply.", envelope: { kind: "reply", to: ["erin@example.com"], cc: ["gail@example.com"],
        attachments: [{ name: "original-report.txt", path: "fictional/report.txt", size: 20 }] } };
      window.deliveryReview = { ReviewId: 999, TaskId: 999, Kind: "draft_reply", Status: "pending", Channel: "email", CanSend: false, Stale: 1,
        DraftText: "A newer unrelated draft.", DeliveryState: "unknown", DeliveryEnvelope: JSON.stringify(attempted),
        Deliver: JSON.stringify({ kind: "reply", to: ["new@example.com"], cc: ["new-copy@example.com"], attachments: [] }) };
      const Probe = () => React.createElement("pre", { id: "delivery-verbs" }, JSON.stringify(useRowVerbs().list));
      const root = ReactDOM.createRoot(host);
      window.renderDelivery = (changes, toRow = false) => {
        window.deliveryReview = { ...window.deliveryReview, ...changes };
        root.render(React.createElement(React.Fragment, null,
          React.createElement(ReviewDecision, { review: window.deliveryReview, toRow }), React.createElement(Probe)));
      };
      window.renderDelivery({});
    });
    await page.waitForFunction(() => document.querySelector("#delivery-fixture")?.innerText.includes("Check delivery"));
    const snapshot = () => page.$eval("#delivery-fixture", host => ({
      text: host.innerText, body: host.querySelector("textarea:not([aria-hidden='true'])").value,
      readonly: host.querySelector("textarea:not([aria-hidden='true'])").readOnly,
      buttons: [...host.querySelectorAll("button")].map(button => ({ label: button.textContent.trim(), disabled: button.disabled })),
      fileDisabled: host.querySelector("input[type=file]").disabled,
    }));
    let view = await snapshot();
    assert.equal(view.body, "Original owner-approved edited reply."); assert.equal(view.readonly, true);
    assert.match(view.text, /erin@example.com/); assert.match(view.text, /gail@example.com/);
    assert.match(view.text, /original-report.txt/); assert.doesNotMatch(view.text, /new-copy@example.com/);
    assert.equal(view.fileDisabled, true);
    assert.ok(view.buttons.find(button => button.label === "Check delivery" && !button.disabled));
    assert.ok(view.buttons.filter(button => button.label !== "Check delivery").every(button => button.disabled));
    await page.$$eval("#delivery-fixture button", buttons => buttons.find(button => button.textContent.trim() === "Check delivery").click());
    await page.waitForFunction(() => window.deliveryCalls.length === 1);
    assert.deepEqual(await page.evaluate(() => window.deliveryCalls), [{ url: "/api/reviews/999/decide", body: { verb: "approve", final_text: null, note: null, cc: null } }]);
    await page.waitForFunction(() => document.querySelector("#delivery-fixture")?.innerText.includes("Delivery has not been confirmed."));
    assert.doesNotMatch((await snapshot()).text, /Approved, but it did not send/);

    await page.evaluate(() => window.renderDelivery({ DeliveryState: "sending", DeliveryClaim: "fixture-live-claim" }));
    await page.waitForFunction(() => document.querySelector("#delivery-fixture")?.textContent.includes("Sending…"));
    view = await snapshot();
    assert.ok(view.buttons.filter(button => button.label).every(button => button.disabled)); assert.equal(view.readonly, true); assert.equal(view.fileDisabled, true);
    await page.evaluate(() => window.renderDelivery({ DeliveryState: "unknown", DeliveryClaim: "fixture-live-claim" }, true));
    await page.waitForFunction(() => JSON.parse(document.querySelector("#delivery-verbs").innerText).some(verb => verb.id === "999:approve" && verb.label === "Checking delivery…"));
    const verbs = await page.$eval("#delivery-verbs", node => JSON.parse(node.innerText));
    assert.ok(verbs.filter(verb => verb.id.startsWith("999:") || verb.id === "attach").every(verb => verb.disabled));
    assert.equal((await page.evaluate(() => window.deliveryCalls)).length, 1);
    assert.deepEqual(apiRequests, []); assert.deepEqual(errors, []);
  } finally {
    await browser?.close();
    if (vite.exitCode === null) { vite.kill(); await Promise.race([new Promise(resolve => vite.once("exit", resolve)), delay(3000)]); }
  }
});
