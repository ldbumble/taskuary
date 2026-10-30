import assert from "node:assert/strict";
import test from "node:test";

import { clickNav, startHarness } from "./harness.mjs";
import { popOpen, scriptChat, shot, sleep, stepRows, until } from "./sees-page.mjs";

/* GET AI TO SET IT UP, IN THE CHAT (the owner, 2026-10-30: "don't you think this sort of ai troubleshooting should go on in the assistant
   ... it will know if you change something in the screen it will trigger a change in the chat and say i see you changed this").
   The card's button opens the chat window with the card as its subject - no walk drawn on the card, no Board task. The scripted answer
   fills what is not a secret, is refused the secret, and presses Test - which tries the values on screen, unsaved. Its answer is heard
   next; the owner's own paste of the secret is heard as an edit - the secret's value never leaves the page - and the chat's x asks
   before it ends the help, after which the page's edits are heard by nobody. Typing on the card before any of it sends nothing. */

const SENTINEL = "SENTINEL-SECRET-0042-never-the-model";
const until2 = (page, re) => until(page, (src) => new RegExp(src).test([...document.querySelectorAll(".tq-chat-pop .tq-aui-step, .tq-chat-pop .tq-msg")].map((x) => x.innerText).join(" ")), re.source);
const typeInto = async (page, label, text) => {
  const h = await page.evaluateHandle((label) => [...document.querySelectorAll("[data-tq-browse-one] input")]
    .find((x) => x.closest(".MuiFormControl-root")?.querySelector("label")?.innerText.trim().startsWith(label)), label);
  const el = h.asElement(); assert.ok(el, `the ${label} box`);
  await el.click(); await page.keyboard.down("Control"); await page.keyboard.press("A"); await page.keyboard.up("Control"); await el.type(text);
  return el;
};

test("Connections: the card's door opens the chat; it fills, tests what is on screen, hears the owner's paste, and x ends it", { timeout: 420000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  await page.setViewport({ width: 1600, height: 900, deviceScaleFactor: 1 });
  const errors = [], tests = [], saves = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const turns = scriptChat(page, harness, (body, n) => {
    if (n === 1) return { say: "LinkedIn needs an app of yours. I put in the Client ID and tried it - the secret is yours to paste.",
      view_ops: [{ op: "set", field: "Client ID", value: "test-client-id-0042" }, { op: "set", field: "Client Secret", value: "made-up" }, { op: "press", button: "Test" }] };
    if (body.react && /^test failed/.test(body.react)) return { say: "Test says it is not signed in yet - paste the Client Secret into its box." };
    if (body.react && /changed Client Secret/.test(body.react)) return { say: "I see you pasted the secret - press Save, then Sign in with LinkedIn." };
    return { say: "Ok." };
  }, (req, url) => {
    if (/^\/api\/connectors\/\d+\/test$/.test(url.pathname)) {
      tests.push(JSON.parse(req.postData() || "{}"));
      req.respond({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: false, ms: 4, detail: "LinkedIn is not signed in yet", draft: true }) });
      return true;
    }
    if (url.pathname === "/api/connectors" && req.method() === "POST") saves.push(req.postData());
    return false;
  });
  await page.goto(harness.ui, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForSelector("[data-tq-nav='connections']", { timeout: 120000 });
  await clickNav(page, "Connections");
  await page.waitForSelector("[data-tq-browse-search]", { timeout: 30000 });
  await page.type("[data-tq-browse-search]", "linkedin");
  await until(page, () => [...document.querySelectorAll("[data-tq-browse-card] [data-tq-card]")].some((c) => /LinkedIn/.test(c.innerText)));
  await page.evaluate(() => [...document.querySelectorAll("[data-tq-browse-card] [data-tq-card]")].find((c) => /LinkedIn/.test(c.innerText)).click());
  await page.waitForSelector('[data-tq-browse-one] [data-tq-ai-setup="start"]', { timeout: 30000 });
  await sleep(1200);

  // 1. NOBODY ASKED: the owner types on the card by hand, and the Assistant hears none of it
  await typeInto(page, "Client ID", "typed-by-hand");
  await page.mouse.click(5, 300);
  await sleep(3000);
  assert.equal(turns.length, 0, "setting a card up by hand never triggers it");
  await shot(page, "card", "1-by-hand-quiet");

  // 2. THE DOOR: the chat window opens on the card - nothing of a walk on the card - and the card goes with the ask, the secret as its state
  assert.equal(await page.$("[data-tq-ai-walk]"), null);
  await page.click('[data-tq-browse-one] [data-tq-ai-setup="start"]');

  await until(page, () => { const p = document.querySelector(".tq-chat-pop"); return !!p && !p.hidden; });
  await until2(page, /Pressed Test/);
  const first = turns[0];
  assert.match(first.text, /^Help me set up LinkedIn/);
  assert.equal(first.view?.area, "connections");
  const fields = Object.fromEntries((first.view.fields || []).map((f) => [f.label, f]));
  assert.equal(fields["Client ID"]?.value, "typed-by-hand", "what is on screen, unsaved");
  assert.ok(Object.keys(fields).some((k) => /^Client Secret/.test(k) && fields[k].secret && !("value" in fields[k])), "the secret as its state only");
  assert.equal(await page.$("[data-tq-ai-walk]"), null, "no walk drawn on the card");
  const rows = await stepRows(page);
  assert.match(rows[0], /^Set Client ID to test-client-id-0042/);
  assert.match(rows[1], /Client Secret.* is yours to paste/);
  assert.match(rows[2], /^Pressed Test - failed: LinkedIn is not signed in yet/);
  // ...Test tried the values on screen, never saved
  assert.equal(tests.length, 1);
  assert.equal(JSON.parse(tests[0].ConfigJson || "{}").client_id, "test-client-id-0042", "the unsaved Client ID was what it tested");
  assert.deepEqual(saves, [], "nothing saved - Save is the owner's");
  await shot(page, "card", "2-door-opened-filled-tested");

  // 3. THE TEST'S ANSWER IS HEARD NEXT, unasked - a reaction draws no line of the owner's
  await until(page, () => /paste the Client Secret into its box/.test(document.querySelector(".tq-chat-pop")?.innerText || ""));
  const heard = turns.find((x) => /^test failed/.test(x.react || ""));
  assert.ok(heard, "the Test's result went back as the next turn");
  assert.ok(!(await page.evaluate(() => [...document.querySelectorAll(".tq-chat-pop .tq-msg")].some((m) => /test failed/.test(m.innerText)))), "no owner line for it");

  // 4. THE OWNER PASTES THE SECRET THEMSELVES: heard as an edit - its value never leaves the page
  await typeInto(page, "Client Secret", SENTINEL);
  await page.mouse.click(5, 300);
  await until(page, () => /I see you pasted the secret/.test(document.querySelector(".tq-chat-pop")?.innerText || ""), undefined, 15000);
  const pasted = turns.find((x) => /changed Client Secret/.test(x.react || ""));
  assert.ok(pasted, "the owner's own edit was heard while helping");
  assert.ok(!JSON.stringify(turns).includes(SENTINEL), "the secret never went with a turn");
  await shot(page, "card", "3-owner-pasted-secret-heard");

  // 5. THE WINDOW SHUT, STILL HELPING: an edit is still heard, and its answer waits behind the pill's count - the window never opens by itself
  await page.focus(".tq-chat-pop ~ .tq-compose-box textarea, .tq-compose-box textarea");
  await page.keyboard.press("Escape");
  await until(page, () => document.querySelector(".tq-chat-pop")?.hidden !== false);
  const shut = turns.length;
  await typeInto(page, "Client ID", "test-client-id-0043");
  await page.mouse.click(5, 300);
  for (let i = 0; i < 40 && turns.length === shut; i++) await sleep(250);
  assert.ok(/changed Client ID/.test(turns[turns.length - 1]?.react || ""), "heard with the window shut");
  await until(page, () => !!document.querySelector("[data-tq-unseen]"));
  assert.equal(await popOpen(page), false, "a quiet mark on the pill - the window stays shut");
  await shot(page, "card", "4-window-shut-mark-on-pill");

  // 6. THE x ASKS FIRST, then ends the help - and the page's edits are heard by nobody after it
  await page.click(".tq-compose-box textarea");
  await until(page, () => { const p = document.querySelector(".tq-chat-pop"); return !!p && !p.hidden; });
  const before = turns.length;
  await page.click("[data-tq-box-close]");
  await page.waitForSelector("[data-tq-chat-end]", { timeout: 5000 });
  await page.mouse.move(5, 300);
  assert.ok(await popOpen(page), "the window stays while it asks");
  await shot(page, "card", "5-close-asks-to-end");
  await page.click("[data-tq-chat-end-yes]");
  await until(page, () => document.querySelector(".tq-chat-pop")?.hidden !== false);
  await typeInto(page, "Client ID", "after-the-end");
  await page.mouse.click(5, 300);
  await sleep(3000);
  assert.equal(turns.length, before, "a session ended hears no more");
  await shot(page, "card", "6-ended-quiet");
  assert.deepEqual(saves, []);
  assert.deepEqual(errors, []);
});
