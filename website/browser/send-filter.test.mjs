import assert from "node:assert/strict";
import test from "node:test";

import { startHarness } from "./harness.mjs";

/* YOUR OWN TOOLS THAT SEND (the owner, 2026-10-25): Settings > Agent permissions lists every MCP tool agents are not handed because it
   sends, with a Keep switch, and folds the kept ones under it, each with Leave out. A tool nobody judged says "Not checked yet: left out"
   (fail closed), and Test it starts a fresh scan. The demo world starts nobody's servers, so /api/sendfilter is answered here from a
   small invented list that the corrections change, the way the server's would. Invented servers only. */
const tool = (name, sends, why, by = "model") => ({ name, sends, why, by, blocked: sends !== false, unchecked: sends === null });
const world = () => ({
  claude: [{ server: "mail", error: "", blocked: false, tools: [tool("send_mail", true, "it emails the recipients"),
    tool("list_inbox", false, "its server marks it read-only", "annotation"), tool("save_draft", null, "not judged yet - no brain was connected")] },
  { server: "claude.ai Team Chat", error: "it needs signing in on claude.ai before its tools can be read", blocked: true, unchecked: false, by: "", tools: [] }],
  codex: [], scanned_at: Date.now() / 1000 - 3600, scanning: false, claudeai: { at: Date.now() / 1000 - 3600, error: "" },
});

test("the send filter lists what agents leave out, keeps one, leaves it out again and checks again", { timeout: 180000 }, async (t) => {
  const harness = await startHarness();
  t.after(() => harness.close());
  const page = await harness.newPage();
  const errors = [], posts = [];
  page.on("pageerror", (e) => errors.push(e.message));
  let state = world(), scans = 0;
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => {
    const p = new URL(r.url()).pathname, json = (body) => r.respond({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
    if (p === "/api/sendfilter" && r.method() === "GET") { const out = state; if (state.scanning) state = { ...state, scanning: false }; return json(out); }
    if (p === "/api/sendfilter/correct" && r.method() === "POST") {
      const b = JSON.parse(r.postData()); posts.push(b);
      state = { ...state, claude: state.claude.map((s) => s.server !== b.server ? s : b.tool === "*" ? { ...s, blocked: b.verdict !== "keep", by: "owner" }
        : { ...s, tools: s.tools.map((x) => x.name !== b.tool ? x : { ...x, by: "owner", blocked: b.verdict !== "keep", sends: b.verdict !== "keep", unchecked: false }) }) };
      return json(state);
    }
    if (p === "/api/sendfilter/scan" && r.method() === "POST") { scans += 1; state = { ...state, scanning: true }; return json({ started: true }); }
    page.fixtureRequestGuard(r);
  });
  await page.goto(`${harness.ui}#settings=config&group=${encodeURIComponent("Agent permissions")}`, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForSelector("[data-tq-sendfilter]", { timeout: 30000 });
  const text = () => page.$eval("[data-tq-sendfilter]", (el) => el.innerText);
  const row = (k) => `[data-tq-sendfilter-row="${k}"]`;

  // THE LIST: one line per tool left out - the send, the unjudged one, and the server whose tools could not be read - and the read-only
  // one only in the fold, which starts shut
  let s = await text();
  assert.match(s, /Your own tools that send/);
  for (const k of ["mail/send_mail", "mail/save_draft", "claude.ai Team Chat/*"]) assert.ok(await page.$(row(k)), `${k} is listed: ${s}`);
  assert.match(await page.$eval(row("mail/send_mail"), (el) => el.innerText), /mail · send_mail[\s\S]*it emails the recipients/);
  assert.match(await page.$eval(row("mail/save_draft"), (el) => el.innerText), /Not checked yet: left out/);
  assert.match(await page.$eval(row("claude.ai Team Chat/*"), (el) => el.innerText), /all its tools[\s\S]*needs signing in/);
  assert.equal(await page.$(row("mail/list_inbox")), null, "the kept ones are folded");
  assert.match(s, /Kept for agents \(1\)/);
  assert.match(s, /Checked 1h ago/);
  assert.doesNotMatch(s, /· Claude/, "with one CLI set up, no line names it");

  // KEEP: the switch is the owner's word, and the line moves under the fold
  await page.click(`${row("mail/send_mail")} input[type=checkbox]`);
  await page.waitForFunction((sel) => !document.querySelector(sel + ":not([data-kept])"), { timeout: 10000 }, row("mail/send_mail"));
  assert.deepEqual(posts.at(-1), { server: "mail", tool: "send_mail", verdict: "keep" });
  assert.match(await text(), /Kept for agents \(2\)/);

  // ...and LEAVE OUT from the fold puts it back on the list
  await page.evaluate(() => [...document.querySelectorAll("[data-tq-sendfilter] button")].find((b) => /Kept for agents/.test(b.textContent)).click());
  await page.waitForSelector(`${row("mail/send_mail")}[data-kept]`, { timeout: 10000 });
  assert.match(await page.$eval(row("mail/send_mail"), (el) => el.innerText), /You kept it/);
  await page.evaluate((sel) => [...document.querySelector(sel).querySelectorAll("button")].find((b) => b.textContent.trim() === "Leave out").click(),
    row("mail/send_mail"));
  await page.waitForSelector(`${row("mail/send_mail")}:not([data-kept])`, { timeout: 10000 });
  assert.deepEqual(posts.at(-1), { server: "mail", tool: "send_mail", verdict: "block" });
  assert.match(await page.$eval(row("mail/send_mail"), (el) => el.innerText), /You left it out/);

  // TEST IT: a fresh scan, said while it runs, and the list read again once it has finished
  await page.evaluate(() => [...document.querySelectorAll("[data-tq-sendfilter] button")].find((b) => b.textContent.trim() === "Test it").click());
  await page.waitForFunction(() => /Checking…/.test(document.querySelector("[data-tq-sendfilter]")?.innerText || ""), { timeout: 5000 });
  await page.waitForFunction(() => /Checked /.test(document.querySelector("[data-tq-sendfilter]")?.innerText || ""), { timeout: 15000 });
  assert.equal(scans, 1);
  assert.deepEqual(errors, []);
  assert.deepEqual(page.fixtureEscapes, []);
});
