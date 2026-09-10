import assert from "node:assert/strict";
import { launch } from "./browser.mjs";

const url = process.argv[2] || "http://127.0.0.1:8767/";
const browser = await launch({ args: ["--no-sandbox", "--enable-unsafe-swiftshader"] });

try {
  const page = await browser.newPage();
  const errors = [];
  const failed = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("requestfailed", (request) => failed.push(`${request.url()}: ${request.failure()?.errorText}`));
  await page.setViewport({ width: 1536, height: 1000, deviceScaleFactor: 1 });
  await page.goto(url, { waitUntil: "networkidle0" });

  const iframe = await page.waitForSelector(".workspace-hero");
  const workspace = await iframe.contentFrame();
  await workspace.waitForFunction(() => window.workspaceMockup?.state.frames > 2);
  assert.equal(await page.$('script[src="/floor.js"]'), null, "the old canvas animation is not loaded");
  assert.ok(await workspace.$("#world canvas"), "the new 3D workspace canvas is rendered");
  assert.equal(await workspace.$eval(".hero-heading h1", (node) => node.textContent), "Your inbox, staffed by AI agents.");
  const hero = await iframe.boundingBox();
  assert.ok(hero.width >= 1500 && hero.height >= 760, `workspace fills the desktop hero: ${JSON.stringify(hero)}`);
  if (process.argv[3]) {
    await workspace.waitForFunction(() => window.workspaceMockup?.state.motion.phase === "ready");
    await page.screenshot({ path: process.argv[3] });
  }

  await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
  await page.reload({ waitUntil: "networkidle0" });
  const mobileFrame = await (await page.waitForSelector(".workspace-hero")).contentFrame();
  await mobileFrame.waitForFunction(() => window.workspaceMockup?.state.frames > 2);
  const pageWidth = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, inner: innerWidth,
    wide: [...document.querySelectorAll("body *")].filter((node) => node.getBoundingClientRect().right > innerWidth + 1)
      .slice(0, 5).map((node) => `${node.tagName}.${node.className}:${Math.round(node.getBoundingClientRect().right)}`) }));
  const frameWidth = await mobileFrame.evaluate(() => ({ scroll: document.documentElement.scrollWidth, inner: innerWidth }));
  const frameHeight = await mobileFrame.evaluate(() => ({ scroll: document.documentElement.scrollHeight, inner: innerHeight }));
  assert.ok(pageWidth.scroll <= pageWidth.inner, `landing page fits mobile: ${JSON.stringify(pageWidth)}`);
  assert.ok(frameWidth.scroll <= frameWidth.inner, `workspace fits mobile: ${JSON.stringify(frameWidth)}`);
  assert.ok(frameHeight.scroll <= frameHeight.inner + 1, `workspace has no nested mobile scroll: ${JSON.stringify(frameHeight)}`);
  assert.deepEqual(errors, []);
  assert.deepEqual(failed, []);
  console.log("PASS: taskuary.com serves the new interactive workspace hero on desktop and mobile.");
} finally {
  await browser.close();
}
