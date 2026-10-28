import assert from "node:assert/strict";
import test from "node:test";
import { boot, clickRow, findRow, sleep } from "./walkdriver.mjs";

/* FINDING A PERSON BY WHAT YOU REMEMBER (the owner, 2026-10-27: "I search 'dynamo' and a list of Dynamo people should show up... I
   don't remember the email"). On the demo world, whose directory knows Dynamo Freight's three people (invented, demo.DIRECTORY) though
   none of them ever wrote in: "dynamo" in a reply's CC lists all three with their company, arrows + Enter adds the chosen one's
   address, and "gail" finds Gail Moreno by her first name. */
const OPTS = ".MuiAutocomplete-popper [role=option]";
const options = (page) => page.$$eval(OPTS, (xs) => xs.map((x) => ({ to: x.getAttribute("data-tq-person"), text: x.innerText, on: x.classList.contains("Mui-focused") })));

test("typing a company in CC lists its people, and choosing one adds the address", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1600, height: 900 });
  const invoice = await findRow(page, /Invoice 88213/);
  const cc = () => page.evaluate(() => (document.querySelector("[data-tq-closeout]")?.innerText || "").match(/CC\s+([^\n]*)/)?.[1] || "");
  await clickRow(page, invoice);
  const loop = () => page.evaluate(() => [...document.querySelectorAll("[data-tq-closeout] [role=button]")].find((b) => /loop someone in|someone else/.test(b.textContent))?.click());
  await page.waitForFunction(() => [...document.querySelectorAll("[data-tq-closeout] [role=button]")].some((b) => /loop someone in/.test(b.textContent)), { timeout: 20000 });
  await loop(); await sleep(400);
  await page.keyboard.type("dynamo");
  await page.waitForFunction((sel) => [...document.querySelectorAll(sel)].filter((x) => /@dynamo\.example$/.test(x.getAttribute("data-tq-person") || "")).length === 3,
    { timeout: 15000 }, OPTS);
  const got = await options(page);
  assert.deepEqual(got.map((o) => o.to).sort(), ["lortiz@dynamo.example", "nprice@dynamo.example", "vhale@dynamo.example"]);
  for (const o of got) assert.match(o.text, /Dynamo Freight/, `${o.to} shows its company`);
  assert.match(got.find((o) => o.to === "lortiz@dynamo.example").text, /Lena Ortiz/);
  // arrows walk the list, Enter takes the highlighted one
  await page.keyboard.press("ArrowDown"); await sleep(150);
  const chosen = (await options(page)).find((o) => o.on)?.to;
  assert.ok(chosen, "a row is highlighted");
  await page.keyboard.press("Enter"); await sleep(800);
  assert.match(await cc(), new RegExp(chosen.replace(/[.]/g, "\\.")), "the chosen person's address is on the CC");
  assert.doesNotMatch(await page.$eval("[data-tq-closeout]", (e) => e.innerText), /pick a person or type their email address/);

  // a first name finds the colleague the directory named
  await loop(); await sleep(400);
  await page.keyboard.type("gail");
  await page.waitForFunction((sel) => [...document.querySelectorAll(sel)].some((x) => x.getAttribute("data-tq-person") === "gmoreno@northwind.example"), { timeout: 15000 }, OPTS);
  assert.match((await options(page)).find((o) => o.to === "gmoreno@northwind.example").text, /Gail Moreno/);
  assert.deepEqual(errors, []);
});

// MESSAGE THEM (the owner's idea, trust audit F6, 2026-10-28): a person found in Ctrl K offers the channels New can reach them on, and the
// pick opens New's Send something on the canvas already addressed. The demo sends on nothing, so a mailbox and a Teams chat stand in.
test("a People hit offers Message them on its channels, and the pick opens New's compose addressed to them", { timeout: 180000 }, async (t) => {
  const { page, errors } = await boot(t, { width: 1440, height: 900 });
  await page.evaluate(() => {
    const body = JSON.stringify({ data: [{ channel: "email", to: [] }, { channel: "teams", to: [{ to: "19:gail-chat", name: "Gail Moreno" }] }] });
    const open = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (m, url, ...rest) { return open.call(this, m, /\/api\/send-targets/.test(String(url)) ? `data:application/json,${encodeURIComponent(body)}` : url, ...rest); };
  });
  await page.keyboard.down("Control"); await page.keyboard.press("k"); await page.keyboard.up("Control");
  await page.waitForSelector("[data-tq-search-input]", { timeout: 10000 });
  await page.keyboard.type("gail");
  await page.waitForSelector('[data-tq-message-them="gmoreno@northwind.example"] [data-tq-message-open]', { timeout: 15000 });
  await page.click('[data-tq-message-them="gmoreno@northwind.example"] [data-tq-message-open]');
  await page.waitForSelector("[data-tq-message-channel=teams]", { timeout: 10000 });
  assert.deepEqual(await page.$$eval("[data-tq-message-channel]", (b) => b.map((x) => x.dataset.tqMessageChannel)), ["email", "teams"]);
  await page.click("[data-tq-message-channel=email]");
  await page.waitForFunction(() => /gmoreno@northwind\.example/.test(document.querySelector('[data-tq-browse="new"]')?.innerText || ""), { timeout: 15000 });
  assert.ok(!(await page.$("[data-tq-search]")), "the search went");
  assert.match(await page.$eval('[data-tq-browse="new"]', (e) => e.innerText), /Send something/);
  assert.deepEqual(errors, []);
});
