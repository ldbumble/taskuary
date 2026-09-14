// Does the live browser view actually WORK - a real agent-browser session, through the server's
// relay, painted on the canvas in the page?
//
// Everything about this pane has been proven a piece at a time: browserview reads agent-browser's
// state files, the relay speaks its screencast, the split lays out in the Assistant tab. What was
// never checked end to end is the thing the owner actually asked for - frames from a real Chrome
// arriving on the canvas he is looking at (2026-09-14: "does the browser live in the app work yet").
//
//   node website/browser_live_check.mjs <url> <sid>
//
// The caller starts the server (on a scratch TASKUARY_HOME) and an agent-browser session named
// tq-<sid>. This script stubs ONLY the task and assistant payloads - so the page believes it has a
// session with that sid - and lets the browser state endpoint and the screencast websocket hit the
// real server. Exits 1 with what it saw if the canvas never paints.
import { launch } from "./browser.mjs";

const url = process.argv[2] || "http://127.0.0.1:7899/";
const SID = process.argv[3] || "e2e-live";
const TID = 999002;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const TASK = { TaskId: TID, Ref: "TQ-9991", Title: "Watch a real page", Kind: "general", Status: "open",
  Source: "assistant", SourceRef: "assistant:setup", Tags: "needs:browser", Summary: "watch it" };
const ASSISTANT = {
  messages: [{ id: "c1", role: "user", content: [{ type: "text", text: "watch it" }], createdAt: new Date().toISOString() }],
  providers: [{ id: "cli:codex", label: "OpenAI Codex CLI (your CLI)", type: "cli", model: "" }],
  defaultPick: "cli:codex", starting: false,
  session: { sid: SID, alive: true, busy: false, provider: "OpenAI Codex CLI (your CLI)", model: "",
    pick: "cli:codex", mode: "assistant", task_id: TID, trace: [], trace_revision: 0 },
};
const json = (body) => ({ status: 200, contentType: "application/json", body: JSON.stringify(body) });

const browser = await launch();
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900 });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.setRequestInterception(true);
page.on("request", (req) => {
  const u = req.url();
  if (u.includes(`/api/tasks/${TID}/assistant`)) return req.respond(json(ASSISTANT));
  if (u.includes(`/api/tasks/${TID}`)) return req.respond(json({ task: TASK, comments: [], runs: [], routes: [] }));
  return req.continue();          // the browser state endpoint and the screencast socket are REAL
});

await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
await page.evaluate((tid) => { localStorage.setItem("taskuary_walk_tid", String(tid)); }, TID);
await page.reload({ waitUntil: "domcontentloaded", timeout: 30000 });
await page.waitForSelector(".tq-walk canvas", { timeout: 30000 });
await wait(6000);                 // the state poll, the socket, the first frame

// Has the canvas been PAINTED? An unpainted one is the pane's own #101010 fill (or transparent);
// a real frame is a photograph of a web page - many colours, and a light background.
const seen = await page.evaluate(() => {
  const c = document.querySelector(".tq-walk canvas");
  const r = c.getBoundingClientRect();
  const ctx = c.getContext("2d");
  const { data } = ctx.getImageData(0, 0, c.width, c.height);
  const colours = new Set();
  let light = 0, pixels = 0;
  for (let i = 0; i < data.length; i += 4 * 97) {          // a sparse sample is plenty
    pixels += 1;
    colours.add(`${data[i] >> 3},${data[i + 1] >> 3},${data[i + 2] >> 3}`);
    if (data[i] > 200 && data[i + 1] > 200 && data[i + 2] > 200) light += 1;
  }
  const text = document.querySelector(".tq-walk")?.innerText || "";
  return { canvas: { w: Math.round(r.width), h: Math.round(r.height) }, pixels, colours: colours.size,
    lightShare: +(light / pixels).toFixed(3), live: /\bLIVE\b/.test(text),
    url: (text.match(/[\w.-]+\.(?:com|org|net|test|dev)[^\s]*/) || [null])[0],
    takeOver: /Take over/.test(text) };
});

const shot = process.argv[4] || null;
if (shot) { const el = await page.$(".tq-walk"); if (el) await el.screenshot({ path: shot }); }
console.log(JSON.stringify({ ...seen, shot, pageErrors: errors }, null, 2));
await browser.close();

const bad = [];
if (!seen.canvas.w) bad.push("the browser canvas has no width");
if (seen.colours < 8) bad.push(`the canvas is blank - only ${seen.colours} distinct colours, so no frame was painted`);
if (!seen.live) bad.push("the toolbar never said LIVE, so frames are not arriving");
if (!seen.takeOver) bad.push("no Take over control");
if (errors.length) bad.push(`page errors: ${errors.join(" | ")}`);
if (bad.length) { console.error("FAIL\n- " + bad.join("\n- ")); process.exit(1); }
console.log("OK - a real page, relayed from a real browser, painted in the app");
