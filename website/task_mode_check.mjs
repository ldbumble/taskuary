// One thing only a browser can answer: does the Chat/Task toggle DO anything on the unread tab?
// The rail there is the PIPE, drawn by AssistantView and handed to FeedView as `top`, so a click
// in task mode had no way to reach FeedView's stage and did nothing at all (the owner,
// 2026-09-04: "did you fix that you can't click the task button instead of chat").
//
//   node website/task_mode_check.mjs <url>      # against a `taskuary --demo --port N` server
//
// RUN IT ON BOTH READ PATHS. A fresh --demo is LEGACY, and this check passed on it for months
// while task mode was broken on the canonical one - where a row can have no message at all and the
// stage has to ask the item about itself instead (2026-09-16). To cover the real configuration,
// activate canonical reads on the demo's home first:
//   python -c "from taskuary.store import SQLiteStore; from datetime import datetime; //     SQLiteStore(r'<home>/taskuary.db').activate_processing_reads(//       fixed_now=datetime.now().strftime('%Y-%m-%d %H:%M:%S'), live_state=[])"
//
// Invisible to pytest and to node --test: the click crosses two components and lands on a stage
// that only exists in a browser. (Whether a rail FILTER reaches the walk is a source-level fact
// instead - funnelPile.test.mjs pins it.)
import { launch } from "./browser.mjs";

const url = process.argv[2] || "http://127.0.0.1:7911/";
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const STAGE_TABS = ["Summary", "Message", "Triage"];      // FeedView's own detail panel
// ...and what a row with NO message opens instead: the item's own pane, which names what it is
const TASK_PANE = ["TASK", "Open TQ-"];

const state = (page) => page.evaluate((tabs) => {
  const btn = (label) => [...document.querySelectorAll(".tq-stage-mode button")].find((b) => b.textContent.trim() === label);
  const text = document.body.innerText;
  return {
    mode: btn("Task")?.classList.contains("on") ? "task" : btn("Chat")?.classList.contains("on") ? "chat" : "(toggle gone)",
    pileRows: document.querySelectorAll(".tq-pile-row").length,
    pileTitles: [...document.querySelectorAll(".tq-pile-row .card b")].map((b) => b.textContent.trim().slice(0, 40)),
    placeholder: text.includes("Pick anything on the left"),
    onStage: tabs.every((t) => text.includes(t)),         // the row opened on the task stage
    onItemPane: ["TASK", "Open TQ-"].every((t) => text.includes(t)),   // ...or its item's own pane
    chatTurns: document.querySelectorAll(".tq-msg").length,
  };
}, STAGE_TABS);

const clickPileRow = (page) => page.evaluate(() => {
  const row = [...document.querySelectorAll(".tq-pile-row")]
    .find((r) => !r.className.includes("settling") && !r.className.includes("current"));
  const t = row?.querySelector(".card b")?.textContent?.trim().slice(0, 40) || "";
  row?.querySelector(".card")?.click();
  return t;
});

const browser = await launch();
const page = await browser.newPage();
await page.setViewport({ width: 1500, height: 950 });
let bad = 0;
const check = (ok, msg, extra) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${msg}`);
  if (!ok) { bad += 1; if (extra) console.error(JSON.stringify(extra, null, 2)); }
};

try {
  await page.goto(url, { waitUntil: "networkidle2" });
  await wait(3000);
  let s = await state(page);
  if (!s.pileRows) { console.error("the pile is empty - nothing to check"); process.exit(2); }
  console.log(`landed on the pipe: ${s.pileRows} rows, stage mode ${s.mode}`);

  // ── 1. task mode opens the row on the stage ──────────────────────────────────────────────────
  await page.evaluate(() => [...document.querySelectorAll(".tq-stage-mode button")]
    .find((b) => b.textContent.trim() === "Task")?.click());
  await wait(600);
  check((await state(page)).mode === "task", "clicking Task switches the stage");
  const before = await state(page);
  const title = await clickPileRow(page);
  await wait(2500);
  s = await state(page);
  // A MESSAGE opens on the stage; a row with only a task behind it - an agent, a proposal, a
  // meeting's prep - opens THE TASK, which means leaving for the Tasks tab. Falling back to the
  // chat is now only right for a row with neither, because "open it" answered with a conversation
  // about it for every agent row on the rail (the owner, 2026-09-16: "task button on the assistant,
  // if i click it then hit a item the chat pops up not the actual task").
  const opened = (s.onStage || s.onItemPane) && !s.placeholder;
  const wentToTask = await page.evaluate(() => !document.querySelector(".tq-stage-mode"));
  const fellBack = s.mode === "chat" && s.chatTurns > before.chatTurns;
  check(opened || wentToTask || fellBack,
    opened ? `a task-mode click opened "${title}" on the stage`
      : wentToTask ? `"${title}" has no message, so it opened its task`
        : fellBack ? `"${title}" has neither a message nor a task, so it answered in the chat`
          : `a task-mode click on "${title}" did nothing visible`, s);

} finally { await browser.close(); }
process.exit(bad ? 1 : 0);
