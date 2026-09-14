// Does the walk's browser really appear BESIDE the conversation in the Assistant tab?
//
// The split is drawn by SessionPane, which GeneralWorkspace renders only when the task has a live
// session - and on the Assistant tab that whole workspace is a `compact` mount inside `.tq-walk`,
// a different layout chain from the Tasks tab (a flex column inside a flex column inside a card).
// Nothing in pytest or node --test can see whether that chain leaves the browser any width: the
// two halves are sized by CSS at runtime (the owner, 2026-09-14: "will it work on the assistant
// tab showing the browser?").
//
//   node website/walk_browser_check.mjs [url]        # default: the running app on 7787
//
// It mutates nothing. The four walk endpoints are answered INSIDE this headless browser - a walk
// task with a live session and an open browser - so the real React code lays out the real CSS
// against a state the server is not asked to produce. Everything else is the live app, read-only.
//
// Exits 1 with the measurements when the browser pane is missing or too narrow to use.
import { launch } from "./browser.mjs";

const url = process.argv[2] || "http://127.0.0.1:7787/";
const TID = 999001, SID = "walkcheck01";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const TASK = { TaskId: TID, Ref: "TQ-9990", Title: "Log into ADP and clock in", Kind: "general",
  Status: "open", Source: "assistant", SourceRef: "assistant:setup", Tags: "needs:browser,setup:external",
  Summary: "I need something to login into ADP every morning at 9am and clock me in." };
const SESSION = { sid: SID, alive: true, busy: false, provider: "OpenAI Codex CLI (your CLI)",
  model: "", pick: "cli:codex", mode: "assistant", task_id: TID, trace: [], trace_revision: 0, started: new Date().toISOString() };
const ASSISTANT = {
  messages: [{ id: "c1", role: "user", content: [{ type: "text", text: TASK.Summary }], createdAt: new Date().toISOString() }],
  providers: [{ id: "cli:codex", label: "OpenAI Codex CLI (your CLI)", type: "cli", model: "" }],
  defaultPick: "cli:codex", starting: false, session: SESSION,
};
const BROWSER = { open: true, url: "https://online.adp.com/signin/v1/", port: 1234 };

const json = (body) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

const page = await (async () => {
  const browser = await launch();
  const p = await browser.newPage();
  p.browser_ = browser;
  await p.setViewport({ width: 1440, height: 900 });
  return p;
})();

const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.setRequestInterception(true);
page.on("request", (req) => {
  const u = req.url();
  if (u.includes(`/api/tasks/${TID}/assistant`)) return req.respond(json(ASSISTANT));
  if (u.includes(`/api/tasks/${TID}`)) return req.respond(json({ task: TASK, comments: [], runs: [], routes: [] }));
  if (u.includes(`/api/terminals/${SID}/browser`)) return req.respond(json(BROWSER));
  return req.continue();
});

await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
// the walk this browser is in - the same key the tab keeps (AssistantView: WALK_KEY)
await page.evaluate((tid) => { localStorage.setItem("taskuary_walk_tid", String(tid)); }, TID);
await page.reload({ waitUntil: "domcontentloaded", timeout: 30000 });
await page.waitForSelector(".tq-walk", { timeout: 30000 });
await wait(3000);                                    // the session GET, then SessionPane's first browser poll

const seen = await page.evaluate(() => {
  const box = (el) => { const r = el.getBoundingClientRect(); return { x: Math.round(r.x), w: Math.round(r.width), h: Math.round(r.height) }; };
  const walk = document.querySelector(".tq-walk");
  const canvas = document.querySelector(".tq-walk canvas");
  const takeover = [...document.querySelectorAll(".tq-walk button")].find((b) => /Take over/.test(b.textContent));
  const chip = [...document.querySelectorAll(".tq-walk button")].find((b) => /^browser ·/.test(b.textContent.trim()));
  const thread = document.querySelector(".tq-walk .tq-aui-thread");
  return {
    walk: walk ? box(walk) : null,
    thread: thread ? box(thread) : null,
    browserCanvas: canvas ? box(canvas) : null,
    hasToolbar: !!takeover,
    chip: chip ? chip.textContent.trim() : null,
    url: [...document.querySelectorAll(".tq-walk p, .tq-walk div")].map((e) => e.textContent)
      .find((t) => t && t.includes("online.adp.com")) || null,
  };
});

console.log(JSON.stringify({ ...seen, pageErrors: errors }, null, 2));
await page.browser_.close();

const bad = [];
if (!seen.walk) bad.push("no .tq-walk on the Assistant tab");
if (!seen.browserCanvas) bad.push("the walk has no browser canvas beside the conversation");
else if (seen.browserCanvas.w < 300) bad.push(`the browser is ${seen.browserCanvas.w}px wide - too narrow to watch`);
else if (seen.browserCanvas.h < 200) bad.push(`the browser is ${seen.browserCanvas.h}px tall - the flex chain gave it no height`);
if (seen.thread && seen.browserCanvas && seen.thread.w < 300) bad.push(`the conversation is squeezed to ${seen.thread.w}px`);
if (!seen.hasToolbar) bad.push("no Take over / Snapshot toolbar on the browser pane");
if (errors.length) bad.push(`page errors: ${errors.join(" | ")}`);
if (bad.length) { console.error("FAIL\n- " + bad.join("\n- ")); process.exit(1); }
console.log("OK - the conversation and its browser share the Assistant tab's walk");
