// Manual theme smoke on a disposable --demo instance. Never point screenshots at an owner's mailbox.
// TASKUARY_TEST_TOKEN=<demo token> node theme_check.mjs http://127.0.0.1:17887 ./theme-shots
import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { launch } from "./browser.mjs";
import { clickNav } from "./browser/harness.mjs";

const url = process.argv[2], folder = process.argv[3] || "theme-shots";
if (!url || ["7787", "7790"].includes(new URL(url).port)) throw Error("Pass an isolated demo/test URL, never the live Taskuary ports.");
await mkdir(folder, { recursive: true });
const browser = await launch({ protocolTimeout: 15000 }), errors = [];
const settle = () => new Promise((r) => setTimeout(r, 700));
const mode = (page) => page.evaluate(() => document.documentElement.dataset.theme);
const waitMode = (page, want) => page.waitForFunction((v) => document.documentElement.dataset.theme === v, {}, want);
const checkSurfaces = async (page) => {
  const light = await page.evaluate(() => [...document.querySelectorAll("body *")].filter((el) => {
    const r = el.getBoundingClientRect(), s = getComputedStyle(el), rgb = s.backgroundColor.match(/^rgb\((\d+), (\d+), (\d+)\)$/);
    return r.width > 150 && r.height > 32 && r.bottom > 0 && r.top < innerHeight && s.visibility !== "hidden" && rgb && Math.min(...rgb.slice(1).map(Number)) > 210;
  }).map((el) => el.className));
  assert.deepEqual(light, [], "application surfaces follow the night palette");
};
try {
  const page = await browser.newPage();
  page.setDefaultTimeout(15000);
  console.log("browser opened");
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewport({ width: 1440, height: 1000 });
  await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "light" }]);
  if (process.env.TASKUARY_TEST_TOKEN) await page.evaluateOnNewDocument((token) => localStorage.setItem("taskuary_token", token), process.env.TASKUARY_TEST_TOKEN);
  await page.goto(url, { waitUntil: "networkidle0" });
  await page.waitForSelector('[aria-label="Switch to dark theme"]');
  assert.equal(await mode(page), "light");
  console.log("initial light OK");

  // Keyboard activation, and draft/state retention: no reload/remount when MUI changes.
  const draft = await page.$("textarea");
  if (draft) await draft.type("An unfinished demo draft");
  console.log("draft typed");
  await page.focus('[aria-label="Switch to dark theme"]');
  await page.keyboard.press("Space");
  console.log("toggle key pressed");
  await waitMode(page, "dark");
  if (draft) assert.equal(await draft.evaluate((el) => el.value), "An unfinished demo draft");
  console.log("draft retained");
  await page.reload({ waitUntil: "domcontentloaded" });
  console.log("reloaded");
  await page.waitForSelector('[aria-label="Switch to light theme"]');
  assert.equal(await mode(page), "dark");

  // A change in another tab updates the rendered palette as well as its toggle's label.
  const other = await browser.newPage();
  console.log("second tab opened");
  await other.goto(new URL("/", url).href, { waitUntil: "domcontentloaded" });
  console.log("second tab loaded");
  await other.waitForSelector('[aria-label="Switch to light theme"]');
  console.log("second tab theme", await mode(other));
  await other.bringToFront();
  await other.click('[aria-label="Switch to light theme"]');
  console.log("second tab switched");
  await page.bringToFront();
  await page.waitForSelector('[aria-label="Switch to dark theme"]');
  await page.click('[aria-label="Switch to dark theme"]');
  await other.bringToFront();
  await other.waitForSelector('[aria-label="Switch to light theme"]');
  await other.close();
  await page.bringToFront();
  console.log("cross-tab OK");

  for (const view of ["Assistant", "Board", "Reports", "Hub", "Connections", "Settings"]) {
    await clickNav(page, view); await settle();
    assert.equal(await mode(page), "dark");
    assert.equal(await page.evaluate(() => getComputedStyle(document.body).backgroundColor), "rgb(42, 41, 37)");
    await page.mouse.move(0, 0);
    await page.screenshot({ path: path.join(folder, `${view.toLowerCase()}-dark.png`) });
    console.log(`dark ${view}: OK`);
  }
  await clickNav(page, "Assistant");
  // The demo's first task is invented; its mail, actions and markdown exercise custom styles.
  await page.evaluate(() => { location.hash = "task=1"; });
  await settle(); await settle();
  await checkSurfaces(page);
  await page.screenshot({ path: path.join(folder, "task-dark.png") });
  await page.click('[aria-label="Switch to light theme"]'); await settle();
  await page.screenshot({ path: path.join(folder, "task-light.png") });
  await page.click('[aria-label="Switch to dark theme"]');

  await page.click('[aria-label="Report a problem"]');
  await page.waitForSelector('[role="dialog"]');
  assert.equal(await page.$eval('[role="dialog"]', (el) => getComputedStyle(el).backgroundColor), "rgb(51, 49, 45)");
  await page.screenshot({ path: path.join(folder, "dialog-dark.png") });
  await page.keyboard.press("Escape");

  await page.setViewport({ width: 390, height: 844 }); await settle();
  const button = await page.$('[aria-label="Switch to light theme"]');
  const bounds = await button.boundingBox();
  assert.ok(bounds && bounds.x >= 0 && bounds.x + bounds.width <= 390, "phone toggle stays visible");
  await checkSurfaces(page);
  await page.screenshot({ path: path.join(folder, "phone-dark.png") });
  await page.setViewport({ width: 1440, height: 1000 });
  await page.click('[data-tq-view="game"]'); await settle(); await settle();
  await page.screenshot({ path: path.join(folder, "game-dark.png") });

  assert.deepEqual(errors, [], "no runtime errors in either theme");
  console.log("theme OK: keyboard, draft retention, persistence, cross-tab, six views, task, dialog, phone and game");
} finally { await browser.close(); }
