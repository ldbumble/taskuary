// THE AGENT'S BROWSER, WALKED ON THE REAL CLI (not a test: nothing here runs in CI). node real-browser.mjs <name> <site url> [user] [password]
// He asks for something behind a sign-in on a site with no connector: the agent says so and opens the browser BESIDE the chat, he signs in on the
// page shown him, the agent goes on by itself; then a second task asks the same site again and no sign-in is asked of him. Each frame is read by
// real-conv's sampler, with what this walk adds: the pane beside the chat, the chat's width and whether its box still fits its page.
import path from "node:path";
import { api, connect, open, shot, save, sleep, type, buttons, out, info } from "./real-lib.mjs";
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

// `typed`: what he types on the page shown him, one box after another (Tab between, Enter last) - [] where no page is expected: one shown
// all the same is a finding, and nothing is typed on it
async function walk(tag, tid, page, ask, typed = []) {
  const signs = typed.length > 0;
  await open(page, tid);
  await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 120000 });
  await sleep(2500);
  const rec = await record(page, path.join(out, "video", `${name}-${tag}`)), lay = [], stop = { now: false }, watching = watchLayout(page, lay, stop);
  await page.evaluate(sampler, NAMES);
  // ...AND THE LAYOUT EVERY FRAME (the walk of 2026-11-12: one 200 ms read caught the chat 1145 px wide and its box 289 px past the window as the
  // pane closed, gone by the next): each rAF, the chat's width, the box's overflow, the rail and the pane's layout - kept on every change
  await page.evaluate(() => { window.__lay = []; let last = "", t0 = performance.now();
    const read = () => { const pg = document.querySelector("[data-tq-task-page]"), vp = pg?.querySelector(".tq-aui-viewport"), box = pg?.querySelector(".tq-aui-input")?.getBoundingClientRect();
      const r = [Math.round(vp?.getBoundingClientRect().width || 0), box ? Math.round(Math.max(0, box.right - innerWidth, box.bottom - innerHeight)) : -1,
        !!document.querySelector("[data-tq-rail] .tq-pile-row"), document.querySelector("[data-tq-browser-layout]")?.getAttribute("data-tq-browser-layout") || "", document.documentElement.scrollWidth - innerWidth];
      const s = JSON.stringify(r); if (s !== last) { last = s; window.__lay.push([Math.round(performance.now() - t0), ...r]); } requestAnimationFrame(read); };
    requestAnimationFrame(read); });
  const snap = async (n) => { await shot(page, `${name}-${tag}-${n}`); const c = await api(`/api/tasks/${tid}/conversation`); await save(`${name}-${tag}-${n}-list.json`, c);
    console.log(`[${tag} ${n}]`, c.items.map((x) => `${x.kind}${x.state ? ":" + x.state : ""}${x.cards?.length ? "+" + x.cards.length + "c" : ""}`).join(" "), "| pending", c.pending.length, "| working", c.working, "| layout", JSON.stringify(await layout(page))); };
  await rest(page, tid); await snap("0rest");
  await type(page, ask); await sleep(1500); await snap("1asked");
  // ...the page is shown him (the pane beside the chat), or the agent came to rest without one
  // ...at rest for half a minute, not for a moment: a turn its agent takes back (asked for a password) is followed by the one that opens the page
  const shown = () => { let calm = 0; return until(async () => (await layout(page)).pane || ((await api(`/api/tasks/${tid}/conversation`)).working ? (calm = 0) : ++calm >= 15 && "rest"), 400000, 2000); };
  let pane = await shown();
  // ...an agent that came to rest asking him for the password is a FINDING; the walk goes on as he would - one line - so the rest is still seen
  if (pane === "rest" && signs) { console.log(`[${tag}] FINDING: at rest with no page shown - he says to use the browser`); await snap("2norpane"); await type(page, "Use the browser for it."); await sleep(1500); pane = await shown(); }
  console.log(`[${tag}] pane`, JSON.stringify(pane)); await sleep(4000); await snap("2pane");
  if (signs && pane && pane !== "rest") {
    await rest(page, tid, 240000); await snap("3asked-to-sign-in");
    console.log(`[${tag}] buttons`, (await buttons(page)).slice(0, 400));
    // his hands on the page: a click on it, then the keys (Tab to the first box)
    const l = await layout(page), [x, y, w, h] = l.pane || [0, 0, 0, 0];
    if (w) { await page.mouse.click(x + w / 2, y + h * 0.75); await sleep(600);
      for (const t of typed) { await page.keyboard.press("Tab"); await sleep(300); await page.keyboard.type(t, { delay: 40 }); await sleep(300); }
      await sleep(300); await snap("4typed");
      await page.keyboard.press("Enter");
      // ...the hand-back: the pane goes and the agent is at work, with no press of his
      const back = await until(async () => { const c = await api(`/api/tasks/${tid}/conversation`), l = await layout(page); return (c.working || !l.pane) && { working: c.working, pane: !!l.pane, asking: c.asking?.request_id || "" }; }, 60000, 250);
      console.log(`[${tag}] handed back`, JSON.stringify(back)); await sleep(1500); await snap("5sent"); }
    await until(async () => (await api(`/api/tasks/${tid}/conversation`)).working, 30000, 300);
  } else if (pane && pane !== "rest") console.log(`[${tag}] FINDING: a page was shown him where none was expected`);
  await rest(page, tid, 300000); await sleep(3000); await snap("6end");
  console.log(`[${tag}] SAVED`, JSON.stringify(await api("/api/signins")).slice(0, 300), "| asking", JSON.stringify((await api(`/api/tasks/${tid}/conversation`)).asking)?.slice(0, 200));
  stop.now = true; await watching;
  const fr = await page.evaluate(() => window.__frames), bad = check(fr);
  // ...the layout's own rules: the chat never narrower than half its width at rest without the pane beside it, the box inside the window
  lay.forEach((l) => { if (l.over > 2) bad.push(`layout: the box overflows the window by ${l.over} px`); if (l.wide > 2) bad.push(`layout: the page scrolls sideways by ${l.wide} px`); });
  // ...every frame: the box inside the window, no sideways scroll, and the chat never wider than its widest at rest with the rail shown
  // ...its column: the width it holds most often with the rail shown and no pane (one bad frame cannot set it)
  const fl = await page.evaluate(() => window.__lay), ws = fl.filter((x) => x[3] && x[4] !== "split" && x[1]).map((x) => x[1]);
  const rest0 = ws.length ? +Object.entries(ws.reduce((m, w) => ({ ...m, [w]: (m[w] || 0) + 1 }), {})).sort((a, b) => b[1] - a[1])[0][0] : 0;
  fl.forEach(([t, w, over, rail, lay, wide]) => { if (over > 2) bad.push(`frame ${t} ms: the box stands ${over} px past the window (chat ${w} px, rail ${rail}, pane ${lay || "-"})`);
    if (wide > 2) bad.push(`frame ${t} ms: the page scrolls sideways by ${wide} px`);
    if (rail && rest0 && w > rest0 + 2) bad.push(`frame ${t} ms: the chat is ${w} px with the task list shown - wider than its column (${rest0})`); });
  await save(`${name}-${tag}-every-frame.json`, fl);
  await save(`${name}-${tag}-frames.json`, fr); await save(`${name}-${tag}-layout.json`, lay); await save(`${name}-${tag}-findings.txt`, [...new Set(bad)].join("\n") || "no rule broken");
  await rec.stop({ sheet: 12 });
  console.log(`[${tag}] FRAMES`, fr.length, "LAYOUTS", lay.length, "RULES BROKEN", new Set(bad).size); console.log([...new Set(bad)].slice(0, 20).join("\n"));
  console.log(`[${tag}] SAID\n` + (await said(tid)).map((s) => "  > " + s.replace(/\n/g, "\n    ")).join("\n"));
  console.log(`[${tag}] BUTTONS`, (await buttons(page)).slice(0, 300));
}

const { browser, page } = await connect();
await page.reload({ waitUntil: "domcontentloaded" }); await sleep(3000);
// which walks to run (WALKS, default all), and the site's mood for each (the scratch site's /_mode): a - he signs in on the page shown him;
// b - the saved sign-in goes in unseen, no page; c - the site asks a code after the password, and the page is shown for that alone;
// d - the saved password no longer works, and the page is shown with the reason
const tasks = {
  a: ["plain", "Hi Alex,\n\nWhat is the date of the next payroll run and the amount due? It is on the Payworth portal - I do not have a login.\n\nThanks,\nGail", undefined,
    `Sign in to Payworth for me at ${site} and get the next payroll date and the amount due.`, [user, pw]],
  b: ["plain", "Alex - for the audit file I need the reference number shown on our Payworth account page. Can you send it over?\n\nErin", ["Erin Blake", "erin.blake@northwind.example", "Audit file: account reference"],
    `Look it up on Payworth at ${site} - the reference number on the account page.`, []],
  c: ["mfa", "Alex, who does Payworth show as signed in on our account page?\n\nPaula", ["Paula Vance", "paula.vance@northwind.example", "Payworth account name"],
    `Load the Payworth account page at ${site} afresh and tell me the name it shows as signed in.`, [process.env.SITE_CODE || ""]],
  // ...d asks what b asks, of another sender: run it without b (WALKS=acd), or triage folds it into b's task and its signed-in browser
  d: ["changed", "Alex - which reference number does Payworth show on our account page? I need it for the bank form.\n\nMarcus", ["Marcus Reed", "marcus.reed@northwind.example", "Bank form: Payworth reference"],
    `Load Payworth at ${site} afresh and look it up - the reference number on the account page.`, [user, process.env.SITE_PW2 || ""]] };
// e - THE SYSTEM HAS A CONNECTOR: a card for it among his connections (an "Any database" card for the training vendor, its connection string a
// database file in the scratch home), so the agent uses that and opens no browser - no page is shown him, nothing is asked. Its topic is
// made straight in the store (POST /api/tasks, as New does), never through triage, which folds it into the walks' Payworth task
tasks.e = ["plain", "Alex - how many Trainly seats are we using right now, out of how many? I need it for the renewal.\n\nRay", ["Ray Colton", "ray.colton@northwind.example", "Trainly renewal: seats in use"],
  "Find how many Trainly seats are in use, out of how many.", []];
const connector = async () => {
  const db = path.join(info.home, "trainly.db");
  const { execFileSync } = await import("node:child_process");
  execFileSync(process.env.PYTHON || "python", ["-c", "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('DROP TABLE IF EXISTS seats'); c.execute('CREATE TABLE seats (plan TEXT, seats_bought INTEGER, seats_in_use INTEGER, renews TEXT)'); c.execute(\"INSERT INTO seats VALUES ('Team',60,47,'2027-01-31')\"); c.commit()", db]);
  const had = ((await api("/api/connectors"))?.data || []).find((c) => c.Name === "Trainly");
  console.log("connector", JSON.stringify(await api("/api/connectors", { ...(had ? { ConnectorId: had.ConnectorId } : {}), Type: "database", Name: "Trainly",
    ConfigJson: JSON.stringify({ conn_str: `sqlite:///${db.replace(/\\/g, "/")}` }), Active: true, Roles: "tool", Scope: "read" })));
};
// BACKEND=coding: each walk is a coding task on the real CLI over ACP (fixture/coding, real; CODING_PTY=1 runs it in its terminal), his ask typed into it - no mail
const coding = process.env.BACKEND === "coding";
for (const k of process.env.WALKS || "abcd") {
  const [m, body, who, ask, typed] = tasks[k];
  console.log("site mode", await fetch(`${site}/_mode?${m}`).then((r) => r.text()));
  if (k === "e") await connector();
  // ...a first sign-in is first: a saved one from an earlier walk on this home is let go of
  if (k === "a") console.log("forget", JSON.stringify(await api(`/api/signins/${new URL(site).hostname}`, undefined, "DELETE")).slice(0, 120));
  const t = k === "e" && !coding ? await api("/api/tasks", { Title: who[2], Kind: "general", Summary: body }).then((x) => ({ task_id: x.taskId }))
    : coding ? await api("/api/fixture/coding", { git: info.git, real: true, pty: process.env.CODING_PTY === "1", title: (who || ["", "", "Payworth: next payroll run"])[2] }).then((x) => ({ task_id: x.taskId }))
    : await mail(`conv-${name}-${k}`, body, who);
  console.log("push", JSON.stringify(t).slice(0, 160));
  await walk(k, t.task_id, page, coding || k === "e" ? `${body.split("\n\n")[0]} ${ask}` : ask, typed);
}
await browser.disconnect();
