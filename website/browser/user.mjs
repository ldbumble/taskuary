// THE HANDS OF AN AGENT PLAYING THE OWNER (not a test: nothing here runs in CI). It drives the app a scratch instance (real-run.mjs) keeps
// open, as a person would - it sees the page, presses what is there by its words, types where a person types - and every command ends by
// saying what is on the screen now, with a screenshot, so whoever plays the person judges the app by what it SHOWS, never by its insides.
//   node user.mjs look                  what is on the screen: where you are, the rail, the open task's chat, the buttons you can press
//   node user.mjs click "<words>" [n]   press the button or link whose words are these (the n-th of them when several, 1 = first)
//   node user.mjs type "<words>"        type into the box on the screen (the task's chat box, else New's, else Ask Taskuary) and press Enter
//   node user.mjs attach <file> "<words>"  the same with a file on the paperclip
//   node user.mjs row "<words>"         open the rail row whose words contain these
//   node user.mjs go new|rail|reports|connections|settings|back
//   node user.mjs wait <seconds>        let time pass, then look
//   node user.mjs sent                  what actually left the computer (the instance's outbox) - for checking what the app SAID it sent
import path from "node:path";
import { readFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { connect, shot, sleep, out, info } from "./real-lib.mjs";

const [cmd = "look", ...args] = process.argv.slice(2);
const { browser, page } = await connect();
const vis = `(e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== "hidden"; }`;

async function look(note = "") {
  await sleep(600);
  const s = await page.evaluate((visSrc) => {
    const vis = eval(visSrc), txt = (e) => (e?.innerText || "").replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim();
    const tp = document.querySelector("[data-tq-task-page]");
    const head = txt(tp?.querySelector("[data-tq-task-head], header, h1, h2")) || txt(document.querySelector("main h1, main h2"));
    // ...the whole row on one line: its first two lines were its age and a hand badge, and the walks read rows "showing only the waving hand"
    const rail = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row[data-tq-key]")].filter(vis).map((e) => "- " + txt(e).split("\n").filter(Boolean).join(" | ")).slice(0, 25);
    const chat = txt(tp?.querySelector(".tq-aui-viewport"));
    const main = tp ? "" : txt(document.querySelector("main") || document.body).slice(0, 2500);
    // ...a greyed one says so (a card the chat moved past keeps its buttons inside a disabled fieldset: button.disabled reads false there)
    const off = (b) => b.matches(":disabled") || !!b.closest("[inert], [aria-disabled=true]");
    const btns = [...document.querySelectorAll("button, a[href], [role=button]")].filter(vis)
      .map((b) => { const w = (b.innerText || b.getAttribute("aria-label") || b.title || "").trim().replace(/\s+/g, " "); return w && off(b) ? `${w} (greyed)` : w; })
      .filter((w) => w && w.length < 70);
    const boxes = [...document.querySelectorAll("textarea, input[type=text], input:not([type]), [contenteditable=true]")].filter(vis)
      .map((b) => b.getAttribute("placeholder") || b.getAttribute("aria-label") || "a box");
    const working = !!tp?.querySelector("[data-tq-working], [data-tq-stop-run]");
    const alerts = [...document.querySelectorAll("[role=alert], .MuiAlert-message, [data-tq-toast]")].filter(vis).map(txt).filter(Boolean);
    return { url: location.hash, head, rail, chat: chat.slice(-3500), main, btns: [...new Set(btns)], boxes: [...new Set(boxes)], working, alerts };
  }, vis);
  const f = await shot(page, `user-${Date.now()}`);
  const parts = [note && `>> ${note}`, `WHERE: ${s.url || "home"}${s.head ? ` - ${s.head.split("\n")[0]}` : ""}${s.working ? "  [the agent is at work]" : ""}`,
    s.alerts.length && `ALERTS: ${s.alerts.join(" / ")}`,
    s.rail.length && `RAIL:\n${s.rail.join("\n")}`,
    s.chat && `CHAT (newest last):\n${s.chat}`, s.main && `PAGE:\n${s.main}`,
    `BUTTONS: ${s.btns.join(" | ")}`, s.boxes.length && `BOXES: ${s.boxes.join(" | ")}`, `SCREENSHOT: ${f}`];
  console.log(parts.filter(Boolean).join("\n\n"));
}

async function click(words, n = 1) {
  const got = await page.evaluate((w, n, visSrc) => {
    const vis = eval(visSrc), norm = (s) => (s || "").trim().replace(/\s+/g, " ").toLowerCase(), want = norm(w);
    const all = [...document.querySelectorAll("button, a[href], [role=button], [role=menuitem], [role=tab], label")].filter(vis);
    const name = (b) => norm(b.innerText || b.getAttribute("aria-label") || b.title);
    const hits = [...all.filter((b) => name(b) === want), ...all.filter((b) => name(b) !== want && name(b).includes(want))];
    const b = hits[n - 1];
    if (!b) return { ok: false };
    // ...greyed by its own flag or by the card around it (MovedPast's disabled fieldset): the walks of 2026-11-18 "pressed" such a Send and an
    // Approve, nothing reached the server, and the diary read it as a live stale card
    if (b.matches(":disabled") || b.closest("[inert], [aria-disabled=true]")) return { ok: false, off: name(b), why: b.title || "" };
    // ...and pressed with the mouse: an element's click() reaches a button under an open menu's backdrop, which no person can - the walks
    // "opened" Change a second time over the first that way
    b.scrollIntoView({ block: "center" }); const q = b.getBoundingClientRect(); return { ok: true, name: name(b), x: q.x + q.width / 2, y: q.y + q.height / 2 };
  }, words, n, vis);
  if (got.ok) await page.mouse.click(got.x, got.y);
  if (!got.ok) return look(got.off ? `"${got.off}" is greyed out${got.why ? ` (its hover says: ${got.why})` : ""} - nothing pressed` : `no button or link says "${words}" - nothing pressed`);
  await sleep(1500); return look(`pressed "${got.name}"`);
}

async function type(words, file) {
  const where = await page.evaluate((visSrc) => {
    const vis = eval(visSrc);
    // ...an open dialog's own box first, as a person's keys go (the walk, 2026-11-18: with Search open, the Ask box behind it got the words)
    const box = [...document.querySelectorAll("[role=dialog] input:not([type=file]), [role=dialog] textarea"), document.querySelector("[data-tq-task-page] .tq-aui-input"),
      ...document.querySelectorAll("textarea, [contenteditable=true], input[type=text]")].find((b) => b && vis(b) && !b.disabled);
    if (!box) return "";
    box.focus(); return box.getAttribute("placeholder") || box.getAttribute("aria-label") || "the box";
  }, vis);
  if (!where) return look("there is no box to type in on this screen");
  if (file) {
    const input = await page.$("[data-tq-task-page] input[type=file]") || await page.$("input[type=file]");
    if (!input) return look("there is no paperclip on this screen");
    await input.uploadFile(path.resolve(file)); await sleep(1200);
    await page.evaluate((visSrc) => { const vis = eval(visSrc); [document.querySelector("[data-tq-task-page] .tq-aui-input"), ...document.querySelectorAll("textarea, [contenteditable=true]")].find((b) => b && vis(b) && !b.disabled)?.focus(); }, vis);
  }
  await page.keyboard.type(words); await page.keyboard.press("Enter");
  await sleep(3000); return look(`typed into "${where}"${file ? ` with ${path.basename(file)}` : ""}`);
}

async function row(words) {
  // ...pressed with the mouse, as a person does (the walks of 2026-11-18: an element's click() on the row opened nothing, and the diaries read
  // the rail as broken - a real click on the same row opens it)
  const at = await page.evaluate((w, visSrc) => {
    const vis = eval(visSrc), want = w.toLowerCase();
    const r = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row[data-tq-key]")].filter(vis).find((e) => e.innerText.toLowerCase().includes(want));
    if (!r) return null; r.scrollIntoView({ block: "center" }); const q = r.getBoundingClientRect(); return { x: q.x + q.width / 2, y: q.y + q.height / 2 };
  }, words, vis);
  if (at) await page.mouse.click(at.x, at.y);
  const ok = !!at;
  await sleep(2000); return look(ok ? `opened the row "${words}"` : `no rail row says "${words}"`);
}

const GO = { new: "New", reports: "Reports", connections: "Connections", settings: "Settings", back: "Back" };
if (cmd === "look") await look();
else if (cmd === "click") await click(args[0], Number(args[1] || 1));
else if (cmd === "type") await type(args.join(" "));
else if (cmd === "attach") await type(args.slice(1).join(" "), args[0]);
else if (cmd === "row") await row(args.join(" "));
else if (cmd === "go") { if (args[0] === "rail") { await page.evaluate(() => { location.hash = ""; }); await look("went to the rail"); } else await click(GO[args[0]] || args[0]); }
else if (cmd === "wait") { await sleep(1000 * Number(args[0] || 10)); await look(`waited ${args[0] || 10}s`); }
else if (cmd === "sent") { const f = path.join(info.home, "outbox.jsonl"); console.log(existsSync(f) ? (await readFile(f, "utf8")).trim().split("\n").slice(-10).map((l) => { const j = JSON.parse(l); return `- ${j.args?.[0]} to ${JSON.stringify(j.args?.[1])}: ${String(j.args?.[2] || "").slice(0, 80)}`; }).join("\n") || "nothing sent" : "nothing sent"); }
else console.log("commands: look | click <words> [n] | type <words> | attach <file> <words> | row <words> | go new|rail|reports|connections|settings|back | wait <s> | sent");
browser.disconnect();
