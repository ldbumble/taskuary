import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* A SIGN-IN ASK IS THE QUESTION AND A LINK, NOT A CARD (the owner, 2026-11-03: "remove that stupid box again as we did with the questions
   the agent ask. just have the question and link to fill it out securely"). No "asked you something" heading, no explainer, no Sign in here
   or Signed in press: the question in the conversation, "fill it in securely" opening the one-time fill page. Signing in on the page needs no
   press (signin.watch sees it); "done" typed in the box below still says so - here through the worker's answer road, as the composer sends
   it, to a terminal stand-in, which is typed the site and "continue" as a fill tells it. Invented site and task only. */
test("a sign-in ask is the question and a fill-it-in link; done typed tells the agent as a fill does", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const call = (path, method = "POST", body = {}) => page.evaluate(async (path, method, body) => (await fetch(path, { method, ...(method === "POST" ? { body: JSON.stringify(body) } : {}),
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json(), path, method, body);
  const made = await call("/api/fixture/signin/terminal-ask");
  assert.ok(made.taskId, JSON.stringify(made));

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  const ask = '[data-tq-asking="signin:northwind.example"]';
  await page.waitForSelector(ask, { visible: true, timeout: 30000 });
  const seen = await page.$eval(ask, (el) => ({ text: el.innerText, tag: el.tagName, buttons: el.querySelectorAll("button").length,
    link: el.querySelector("[data-tq-signin-link]")?.textContent || "" }));
  assert.equal(seen.tag, "P", "a line of the conversation, not a card");
  assert.equal(seen.buttons, 0, "no Sign in here, no Signed in");
  assert.equal(seen.link, "fill it in securely");
  assert.match(seen.text, /^Sign in to northwind\.example to continue - fill it in securely, or sign in on the page\.$/);
  assert.doesNotMatch(await page.evaluate(() => document.body.innerText), /Sign in here|Or sign in yourself|then press Signed in/);

  // (the link's page itself is browser/signin-fill-page's - this demo world refuses to mint one)

  // "done", as the box below sends it while the question is open
  const box = await page.waitForSelector('textarea[placeholder="Message the agent - never your password"]', { visible: true, timeout: 15000 });
  await box.click(); await box.type("done"); await page.keyboard.press("Enter");
  await page.waitForFunction((ask) => !document.querySelector(ask), { timeout: 15000 }, ask);
  let typed = "";
  for (let i = 0; i < 40 && !typed.includes("\r"); i++) { typed = (await call(`/api/fixture/signin/typed/${made.taskId}`, "GET")).typed; await new Promise((r) => setTimeout(r, 250)); }
  assert.equal(typed.replace(/\r$/, ""), "Signed in to northwind.example - continue.", "the pane hears the site and continue");
  assert.deepEqual(errors, []);
});
