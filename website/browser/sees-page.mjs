// What the assistant-sees-* tests share (the owner, 2026-10-30: the Assistant reads the page it was asked about and acts on it as the owner
// would). The demo has no model: each turn is scripted at the stream - its reply may carry `view_ops`, what a model's VIEW lines become once
// the server has held them to the owner's lines (taskuary/pageview.py). What is held here is the page: the view it sent, and what it did with
// the ops through its own buttons. Set TASKUARY_FLOW_SHOTS to a folder to keep each flow's key frames, named by flow and step.
import path from "node:path";

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const until = (page, f, arg, timeout = 30000) => page.waitForFunction(f, { timeout, polling: 150 }, arg).catch(async (e) => {
  throw new Error(`${e.message} waiting for ${String(f).slice(0, 200)}\n${(await page.evaluate(() => document.body.innerText)).slice(-1500)}`);
});

// every /api/concierge/stream turn is answered by `reply(body, n)` - {say, view_ops} - and its body kept, so a test reads what the page sent
export function scriptChat(page, harness, reply, also = () => false) {
  const turns = [];
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (req) => {
    const url = new URL(req.url());
    // ...a typed line or a reaction only: a row opened or Next is the walk's own turn, answered by the fixture
    const body = url.origin === harness.ui && url.pathname === "/api/concierge/stream" && req.method() === "POST" ? JSON.parse(req.postData() || "{}") : null;
    if (body && (body.mode || "say") === "say") {
      turns.push(body);
      const out = reply(body, turns.length) || { say: "Ok." };
      const done = { type: "done", options: [], chips: [], decision: null, ...out };
      return req.respond({ status: 200, contentType: "application/x-ndjson", body: `${JSON.stringify(done)}\n` });
    }
    if (also(req, url)) return undefined;
    return page.fixtureRequestGuard(req);
  });
  return turns;
}

export const api = (harness, p, init = {}) => fetch(`${harness.fixtureApi}${p}`, { ...init, headers: { "X-Taskuary-Token": harness.token, "Content-Type": "application/json", ...(init.headers || {}) } })
  .then((r) => r.json());

export async function ask(page, text) {
  const box = await page.waitForSelector(".tq-compose textarea:not([disabled])", { timeout: 30000 });
  await box.click();
  await box.type(text);
  await page.keyboard.press("Enter");
}
// the step rows on the newest answer in the chat window (AgentSteps, the troubleshooter's shape)
export const stepRows = (page) => page.evaluate(() => {
  const msgs = [...document.querySelectorAll(".tq-chat-pop .tq-msg")].filter((m) => m.querySelector(".tq-aui-steps"));
  const last = msgs[msgs.length - 1];
  return last ? [...last.querySelectorAll(".tq-aui-step")].map((x) => x.innerText.replace(/\s+/g, " ").trim()) : [];
});
export const popOpen = (page) => page.evaluate(() => { const p = document.querySelector(".tq-chat-pop"); return !!p && !p.hidden; });
export const clickText = (page, sel, re) => page.evaluate((sel, src) => {
  const b = [...document.querySelectorAll(sel)].find((x) => new RegExp(src).test(x.innerText.trim()) && x.offsetParent && !x.disabled);
  if (!b) return false; b.click(); return true;
}, sel, re.source);

export async function shot(page, flow, step) {
  const dir = process.env.TASKUARY_FLOW_SHOTS;
  if (!dir) return;
  await sleep(350);
  await page.screenshot({ path: path.join(dir, `${flow}-${step}.png`) });
}
