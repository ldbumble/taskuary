import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* SIGNED IN IS A PRESS ON A TERMINAL CLI'S ASK TOO (owner-approved, 2026-10-25). The chat's own agent's sign-in ask had a Signed in
   press; a terminal CLI's (Claude Code in its pane) had only Sign in here, a box, and a line saying to type it - and the bare words
   reached its prompt with no site and no "continue". Here a real backend holds the ask of a terminal stand-in; the press goes through
   the worker's answer road to signin.signed_in, and the pane is typed what a fill tells it. Invented site and task only. */
test("a terminal CLI's sign-in ask has a Signed in press, told to the pane as a fill is", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 30000 });
  const call = (path, method = "POST") => page.evaluate(async (path, method) => (await fetch(path, { method, ...(method === "POST" ? { body: "{}" } : {}),
    headers: { "Content-Type": "application/json", "X-Taskuary-Token": localStorage.getItem("taskuary_token") } })).json(), path, method);
  const made = await call("/api/fixture/signin/terminal-ask");
  assert.ok(made.taskId, JSON.stringify(made));

  await page.evaluate((id) => { window.location.hash = `task=${id}`; }, made.taskId);
  const ask = '[data-tq-asking="signin:northwind.example"]';
  await page.waitForSelector(ask, { visible: true, timeout: 30000 });
  const card = await page.$eval(ask, (el) => ({ text: el.innerText, presses: [...el.querySelectorAll("button:not([type=submit])")].map((b) => b.textContent.trim()) }));
  assert.deepEqual(card.presses, ["Sign in here", "Signed in"], "the same two presses the chat agent's ask has");
  assert.match(card.text, /Or sign in yourself in the browser, then press Signed in\./);
  assert.doesNotMatch(card.text, /answer Signed in/);

  await page.evaluate((ask) => [...document.querySelectorAll(`${ask} button`)].find((b) => b.textContent.trim() === "Signed in").click(), ask);
  await page.waitForFunction((ask) => !document.querySelector(ask), { timeout: 15000 }, ask);
  let typed = "";
  for (let i = 0; i < 40 && !typed.includes("\r"); i++) { typed = (await call(`/api/fixture/signin/typed/${made.taskId}`, "GET")).typed; await new Promise((r) => setTimeout(r, 250)); }
  assert.equal(typed.replace(/\r$/, ""), "Signed in to northwind.example - continue.", "the pane hears the site and continue, never a chooser's number");
  assert.deepEqual(errors, []);
});
