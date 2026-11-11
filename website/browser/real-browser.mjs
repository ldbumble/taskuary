// THE AGENT'S BROWSER, WALKED ON THE REAL CLI (not a test: nothing here runs in CI). node real-browser.mjs <name> <site url> [user] [password]
// He asks for something behind a sign-in on a site with no connector: the agent says so and opens the browser BESIDE the chat, he signs in on the
// page shown him, the agent goes on by itself; then a second task asks the same site again and no sign-in is asked of him. Each frame is read by
// real-conv's sampler, with what this walk adds: the pane beside the chat, the chat's width and whether its box still fits its page.
import path from "node:path";
import { api, connect, open, shot, save, sleep, type, buttons, out } from "./real-lib.mjs";
import { record } from "./recorder.mjs";
import { NAMES, sampler, check, rest } from "./real-conv.mjs";

const [name, site, user = "", pw = ""] = process.argv.slice(2);
const mail = (conv, body, who = ["Gail Moreno", "gail@northwind.example", "Payworth numbers"]) => api("/api/ingest/push", { channel: "email", subject: who[2], from_name: who[0], from_email: who[1], conversation_id: conv, body });
// ...the layout, sampled beside the frames: where the pane and the chat stand, and the box inside its page
const layout = (page) => page.evaluate(() => { const r = (e) => { if (!e) return null; const b = e.getBoundingClientRect(); return b.width ? [Math.round(b.left), Math.round(b.top), Math.round(b.width), Math.round(b.height)] : null; };
  const pg = document.querySelector("[data-tq-task-page]"), box = pg?.querySelector(".tq-aui-input"), b = box?.getBoundingClientRect();
  return { pane: r(pg?.querySelector("canvas")) || r(document.querySelector("canvas")), view: r(document.querySelector("[data-tq-browser-view]")), chat: r(pg?.querySelector(".tq-aui-viewport")), box: r(box),
    over: b ? Math.round(Math.max(0, b.bottom - innerHeight, b.right - innerWidth)) : null, wide: document.documentElement.scrollWidth - innerWidth,
    closed: document.querySelector("[data-tq-browser-closed]")?.innerText || "", chip: [...document.querySelectorAll("[data-tq-task-page] *")].find((e) => !e.children.length && /^browser · /.test(e.innerText || ""))?.innerText || "" }; });
async function watchLayout(page, log, stop) { let last = ""; while (!stop.now) { const l = await layout(page).catch(() => null), s = JSON.stringify(l); if (l && s !== last) { last = s; log.push({ t: Date.now(), ...l }); } await sleep(200); } }
const until = async (f, ms, every = 500) => { const end = Date.now() + ms; while (Date.now() < end) { const v = await f(); if (v) return v; await sleep(every); } return null; };
const said = async (tid) => { const c = await api(`/api/tasks/${tid}/conversation`); return c.items.filter((x) => x.kind === "turn").map((x) => (x.steps || []).filter((s) => s.kind === "said" || s.said).map((s) => s.text || s.said).join("\n") || x.text || x.answer || "").filter(Boolean); };

async function walk(tag, tid, page, ask, signs) {
  await open(page, tid);
  await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 120000 });
  await sleep(2500);
  const rec = await record(page, path.join(out, "video", `${name}-${tag}`)), lay = [], stop = { now: false }, watching = watchLayout(page, lay, stop);
  await page.evaluate(sampler, NAMES);
  const snap = async (n) => { await shot(page, `${name}-${tag}-${n}`); const c = await api(`/api/tasks/${tid}/conversation`); await save(`${name}-${tag}-${n}-list.json`, c);
    console.log(`[${tag} ${n}]`, c.items.map((x) => `${x.kind}${x.state ? ":" + x.state : ""}${x.cards?.length ? "+" + x.cards.length + "c" : ""}`).join(" "), "| pending", c.pending.length, "| working", c.working, "| layout", JSON.stringify(await layout(page))); };
  await rest(page, tid); await snap("0rest");
  await type(page, ask); await sleep(1500); await snap("1asked");
  // ...the page is shown him (the pane beside the chat), or the agent came to rest without one
  // ...at rest for half a minute, not for a moment: a turn its agent takes back (asked for a password) is followed by the one that opens the page
  let calm = 0; const pane = await until(async () => (await layout(page)).pane || ((await api(`/api/tasks/${tid}/conversation`)).working ? (calm = 0) : ++calm >= 15 && "rest"), 400000, 2000);
  console.log(`[${tag}] pane`, JSON.stringify(pane)); await sleep(4000); await snap("2pane");
  if (signs && pane && pane !== "rest") {
    await rest(page, tid, 240000); await snap("3asked-to-sign-in");
    console.log(`[${tag}] buttons`, (await buttons(page)).slice(0, 400));
    // his hands on the page: a click on it, then the keys (Tab to the first box)
    const l = await layout(page), [x, y, w, h] = l.pane || [0, 0, 0, 0];
    if (w) { await page.mouse.click(x + w / 2, y + h * 0.75); await sleep(600);
      await page.keyboard.press("Tab"); await sleep(300); await page.keyboard.type(user, { delay: 40 }); await sleep(300);
      await page.keyboard.press("Tab"); await sleep(300); await page.keyboard.type(pw, { delay: 40 }); await sleep(600); await snap("4typed");
      await page.keyboard.press("Enter"); await sleep(5000); await snap("5sent"); }
    await until(async () => (await api(`/api/tasks/${tid}/conversation`)).working, 60000, 300);
  }
  await rest(page, tid, 300000); await snap("6end");
  stop.now = true; await watching;
  const fr = await page.evaluate(() => window.__frames), bad = check(fr);
  // ...the layout's own rules: the chat never narrower than half its width at rest without the pane beside it, the box inside the window
  lay.forEach((l) => { if (l.over > 2) bad.push(`layout: the box overflows the window by ${l.over} px`); if (l.wide > 2) bad.push(`layout: the page scrolls sideways by ${l.wide} px`); });
  await save(`${name}-${tag}-frames.json`, fr); await save(`${name}-${tag}-layout.json`, lay); await save(`${name}-${tag}-findings.txt`, [...new Set(bad)].join("\n") || "no rule broken");
  await rec.stop({ sheet: 12 });
  console.log(`[${tag}] FRAMES`, fr.length, "LAYOUTS", lay.length, "RULES BROKEN", new Set(bad).size); console.log([...new Set(bad)].slice(0, 20).join("\n"));
  console.log(`[${tag}] SAID\n` + (await said(tid)).map((s) => "  > " + s.replace(/\n/g, "\n    ")).join("\n"));
  console.log(`[${tag}] BUTTONS`, (await buttons(page)).slice(0, 300));
}

const { browser, page } = await connect();
await page.reload({ waitUntil: "domcontentloaded" }); await sleep(3000);
const a = await mail(`conv-${name}-a`, "Hi Alex,\n\nWhat is the date of the next payroll run and the amount due? It is on the Payworth portal - I do not have a login.\n\nThanks,\nGail");
console.log("push", JSON.stringify(a).slice(0, 160));
await walk("a", a.task_id, page, `Sign in to Payworth for me at ${site} and get the next payroll date and the amount due.`, true);
const b = await mail(`conv-${name}-b`, "Alex - for the audit file I need the reference number shown on our Payworth account page. Can you send it over?\n\nErin", ["Erin Blake", "erin.blake@northwind.example", "Audit file: account reference"]);
console.log("push", JSON.stringify(b).slice(0, 160));
await walk("b", b.task_id, page, `Look it up on Payworth at ${site} - the reference number on the account page.`, false);
await browser.disconnect();
