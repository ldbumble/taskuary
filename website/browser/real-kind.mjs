// THE KIND SWITCH, WATCHED FRAME BY FRAME (not a test: nothing here runs in CI). node real-kind.mjs <name> <task id> [menu word regex ...]
// The owner's rule: a layout switch never blanks what was drawn. Each frame writes down whether the task page holds a chat, how many items
// it draws and how many words; a frame with none, after frames that had some, is the finding. With no words given it only lists the menu.
import path from "node:path";
import { connect, open, shot, save, sleep, buttons, out } from "./real-lib.mjs";
import { record } from "./recorder.mjs";
const [name, tid, ...words] = process.argv.slice(2);
const { browser, page } = await connect();
await open(page, Number(tid)); await sleep(3500);
const rec = await record(page, path.join(out, "video", name));
await page.evaluate(() => { window.__k = []; let last = "";
  const tick = () => { const p = document.querySelector("[data-tq-task-page]"), vp = p?.querySelector(".tq-aui-viewport");
    const f = { page: !!p, chat: !!vp, items: vp ? vp.querySelectorAll("[data-tq-item]").length : 0, words: (vp?.innerText || "").trim().length, working: !!vp?.querySelector("[data-tq-working]"),
      term: !!p?.querySelector(".xterm, [data-tq-chat-screen]"), w: Math.round(vp?.getBoundingClientRect().width || 0) };
    const sig = JSON.stringify(f); if (sig !== last) { last = sig; window.__k.push({ t: Math.round(performance.now()), ...f }); }
    requestAnimationFrame(() => setTimeout(tick, 0)); };
  tick(); });
const menu = () => page.evaluate(() => [...document.querySelectorAll("[role=menuitem], [role=menu] li, [role=option]")].filter((e) => e.getBoundingClientRect().width > 0).map((e) => e.innerText.trim().replace(/\s+/g, " ").slice(0, 70)));
const click = (src) => page.evaluate((src) => { const re = new RegExp(src, "i");
  const e = [...document.querySelectorAll("[role=menuitem], [role=menu] li, [role=option], [data-tq-task-page] button")].filter((e) => e.getBoundingClientRect().width > 0 && re.test(e.innerText.trim() || e.getAttribute("aria-label") || "")).pop();
  e?.click(); return e ? "clicked " + (e.innerText.trim() || e.getAttribute("aria-label")).slice(0, 60) : "nothing matches " + src; }, src);
console.log("BUTTONS", await buttons(page));
await page.keyboard.press("Escape"); await sleep(400);          // ...a menu a run before this left open
console.log(await click("^(Change\\s*)?▾$")); await sleep(700); console.log("MENU", JSON.stringify(await menu()));
for (const w of words) { console.log(await click(w)); await sleep(900); await shot(page, `${name}-${words.indexOf(w)}`); console.log("MENU", JSON.stringify(await menu())); }
if (words.length) { for (const ms of [400, 1500, 4000, 12000]) { await sleep(ms === 400 ? 400 : ms - (ms === 1500 ? 400 : ms === 4000 ? 1500 : 4000)); await shot(page, `${name}-after-${ms}`); } }
const fr = await page.evaluate(() => window.__k); await save(`${name}-kind-frames.json`, fr);
let had = false; const bad = [];
fr.forEach((f, i) => { if (f.items > 0) had = true; else if (had && !f.term) bad.push(`${f.t} ms: ${f.chat ? "the chat is drawn with nothing in it" : f.page ? "no chat on the task page" : "no task page"} (for ${(fr[i + 1]?.t ?? f.t) - f.t} ms)`); });
console.log("FRAMES", fr.length, "BLANK", bad.length); console.log(bad.join("\n")); console.log(fr.slice(-14).map((f) => JSON.stringify(f)).join("\n"));
await rec.stop({ sheet: 12 }); await browser.disconnect();
