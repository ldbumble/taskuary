// AN AMBITIOUS JOB, WALKED END TO END ON THE REAL CLI (not a test: nothing here runs in CI). node real-job.mjs <name> <job>
// The owner, 2026-11-16: "try the most ambitious tasks like find me x properties and email it out to 100 people, sign up to 10 websites and get
// data ... make sure it all works and flows ... not drop user, suggest action cards when needed, not ask things again after approved, show what
// the agent is working on at all times". Against the instance real-run.mjs keeps up (REAL_BROWSER=1). He asks; the walk plays the owner: every
// card is pressed as he would press it (its first go-ahead), the agent's one question is answered from the job's script, a site's emailed code
// arrives as mail; and it writes down, every 15 s, the line that says what the agent is doing. Everything is invented and goes nowhere: mail to
// the fixture outbox (outbox.jsonl), sites on loopback (fake_signup.py), data from invented files.
import path from "node:path";
import { spawn, execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { api, connect, open, shot, save, sleep, type, buttons, out, info } from "./real-lib.mjs";
import { record } from "./recorder.mjs";
import { NAMES, sampler, check, rest } from "./real-conv.mjs";

const [name = "job", job = "signups"] = process.argv.slice(2);
const PY = process.env.PYTHON || "python", here = path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1"));
const SITE = 18791, INBOX = path.join(out, `${name}-inbox.jsonl`);

// ── THE WORLDS: invented data each job works from ──
const worlds = {
  parcels() {
    const db = path.join(info.home, "parcels.db");
    execFileSync(PY, ["-c", `
import random, sqlite3, sys
r = random.Random(7); c = sqlite3.connect(sys.argv[1]); c.execute('DROP TABLE IF EXISTS parcels')
c.execute('CREATE TABLE parcels (parcel_id TEXT, address TEXT, use TEXT, sqft INTEGER, owner TEXT, owner_email TEXT, assessed INTEGER, last_sale_year INTEGER, tax_delinquent_years INTEGER, code_violations INTEGER, vacancy_pct INTEGER, liens INTEGER, notice_of_default INTEGER)')
for i in range(400):
    d = r.random(); owner = f"{r.choice(['Northgate','Bluestone','Cedar','Iron','Lakeview','Summit','Pioneer','Granite'])} {r.choice(['Holdings','Partners','Realty','Properties'])} {i + 1} LLC"
    c.execute('INSERT INTO parcels VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)', (f'P-{10000 + i}', f'{100 + i * 7} {r.choice(["Harbor","Mill","Quarry","Elm","Union","Canal"])} St', r.choice(['retail','office','warehouse','mixed use']),
        r.randint(2000, 90000), owner, f"owner{i + 1}@{owner.split()[0].lower()}.example", r.randint(300, 9000) * 1000, r.randint(1985, 2024), int(d > .7) * r.randint(1, 4), int(d > .5) * r.randint(0, 6),
        min(100, int(d * r.randint(0, 120))), int(d > .8) * r.randint(1, 3), int(d > .9)))
c.commit()`, db]);
    return api("/api/connectors", { Type: "database", Name: "County parcels", ConfigJson: JSON.stringify({ conn_str: `sqlite:///${db.replace(/\\/g, "/")}` }), Active: true, Roles: "tool", Scope: "read" });
  },
  contacts() {
    const f = path.join(info.home, "Documents", "event-contacts.csv");
    execFileSync(PY, ["-c", `
import csv, os, random, sys
r = random.Random(3); os.makedirs(os.path.dirname(sys.argv[1]), exist_ok=True)
first = ['Ana','Ben','Cara','Dev','Eli','Fay','Gus','Hana','Ivo','Jo','Kai','Lea','Max','Nia','Oli','Pia','Quin','Ria','Sam','Tia']
last = ['Hart','Lowe','Ng','Park','Ruiz','Shaw','Tran','Vale','Wolfe','Young']
with open(sys.argv[1], 'w', newline='') as o:
    w = csv.writer(o); w.writerow(['first_name','last_name','company','email','city','last_event'])
    for i in range(100):
        fn, ln = r.choice(first), r.choice(last); co = r.choice(['Acme','Brightline','Corvid','Dunmore','Elmstead','Fernway'])
        w.writerow([fn, ln, co, f"{fn.lower()}.{ln.lower()}{i}@{co.lower()}.example", r.choice(['Harbor City','Millbrook','Oak Ridge']), r.choice(['2025 Summit','2026 Expo','never'])])`, f]);
    return f;
  },
  async signups() {
    // ...a fresh world each run: the sites forget their accounts when they start, so the sign-ins kept for them go too (Remove, as he would)
    for (const r of ((await api("/api/signins"))?.data || [])) if (/^127\./.test(r.Site || r.site || "")) await api(`/api/signins/${r.Site || r.site}`, null, "DELETE");
    const p = spawn(PY, [path.join(here, "fake_signup.py"), String(SITE), INBOX], { stdio: "ignore", detached: false });
    process.on("exit", () => { try { p.kill(); } catch {} });
    return `http://127.0.0.1:${SITE}`;
  },
};

// ── THE JOBS: what he asks, and what only he could answer if asked ──
const JOBS = {
  properties: { world: "parcels", title: "Distressed properties outreach",
    ask: "Find the 100 commercial properties in the county parcel data that look most distressed, show them to me in a table with the signs of distress, the owner, " +
      "how to reach them and a score, and email each owner asking whether they would consider selling. Sign it from me, Alex Doyle at Northwind. Work in batches." },
  email100: { world: "contacts", title: "Invite 100 contacts to the open house",
    ask: () => `Email everyone in ${worlds.contacts()} to invite them to our open house on Thursday 4 December, 5-7pm at Northwind, 12 Harbor St. ` +
      "Personalise each one with their first name and company, and mention their last event if they came to one. Then tell me how many went out." },
  signups: { world: "signups", title: "Market data from ten vendors",
    ask: async () => `Sign up for a free account on each of the ten data vendors listed at ${await worlds.signups()}/ using my work email alex@northwind.example, ` +
      "collect each one's table, and put them together into one sheet by city with a column per vendor. Tell me which ones you could not get and why." },
  report: { world: null, title: null, ask: "Which site is closest to a cap of 140 people, and draft a note to its manager about it." },
};
// what the owner says when asked: a fact only he has, or his go-ahead
const ANSWERS = [[/phone|mobile|number/i, "Use 555-0142 - it is the office line."], [/card|pay|\$49|subscri/i, "Skip the paid one - do not pay for anything."],
  [/password/i, "Make up a strong one for each and keep them in the sign-in vault."], [/.*/, "Yes - go ahead and do it the way you think best."]];
const STOP = /^(Reject|Not now|Withdraw|Cancel|Skip|Edit|Change|Dismiss|Stop)/i, GO = /^(Send all|Send|Approve|Allow once|Allow|Trust|Yes|Go ahead|Run|Sign|Pay|Confirm|Continue)/i;

const J = JOBS[job]; if (!J) { console.log("no such job", job, Object.keys(JOBS)); process.exit(1); }
await api("/api/fixture/outbox", {});
const outbox = path.join(info.home, "outbox.jsonl"), sentBefore = existsSync(outbox) ? readFileSync(outbox, "utf8").split("\n").filter(Boolean).length : 0;
if (J.world === "parcels") console.log("world", JSON.stringify(await worlds.parcels()).slice(0, 160));
const ask = typeof J.ask === "function" ? await J.ask() : J.ask;

const { browser, page } = await connect();
await page.reload({ waitUntil: "domcontentloaded" }); await sleep(3000);
const t = await api("/api/tasks", { Title: J.title || name, Kind: "general", Summary: "" }).then((x) => x.taskId);
await open(page, t);
await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 120000 }); await sleep(2000);
const rec = await record(page, path.join(out, "video", name)), t0 = Date.now(), log = [], found = [], pressed = [], asked = [];
const s = () => Math.round((Date.now() - t0) / 1000), note = (m) => { found.push(`${s()}s ${m}`); console.log(`[${s()}s] FINDING ${m}`); };
await page.evaluate((tid) => { window.__tid = tid; }, t); await page.evaluate(sampler, NAMES);
await type(page, ask);

// ── PLAY THE OWNER until the job rests: press cards, answer the one question, deliver mail, watch the working line ──
let pagePresses = 0, inboxSeen = 0, calm = 0, lastLine = "", sameLine = 0, n = 0;
const MAX = (+process.env.JOB_MIN || 75) * 60000;
while (Date.now() - t0 < MAX) {
  await sleep(5000); n++;
  // a site's code, emailed: into his inbox as mail, on the arrival road
  if (existsSync(INBOX)) { const lines = readFileSync(INBOX, "utf8").split("\n").filter(Boolean);
    for (const l of lines.slice(inboxSeen)) { const m = JSON.parse(l); console.log(`[${s()}s] MAIL in: ${m.subject}`);
      await api("/api/fixture/incoming", { from_email: m.from, from_name: m.from.split("@")[1], subject: m.subject, body: m.body }); }
    inboxSeen = lines.length; }
  const c = await api(`/api/tasks/${t}/conversation`);
  const st = await page.evaluate(() => {
    const tp = document.querySelector("[data-tq-task-page]"), vp = tp?.querySelector(".tq-aui-viewport");
    const lit = [...(tp?.querySelectorAll("[data-tq-turn-cards] button, [data-tq-ask] button, [data-tq-permission] button") || [])].filter((b) => !b.disabled && b.getBoundingClientRect().width).map((b) => b.innerText.trim().replace(/\s+/g, " "));
    const cards = [...(tp?.querySelectorAll("[data-tq-turn-cards] > *") || [])].filter((e) => e.querySelector("button:not([disabled])")).map((e) => e.innerText.replace(/\s+/g, " ").slice(0, 220));
    return { line: (() => { const w = tp?.querySelector("[data-tq-working]"); if (!w) return "";
      // ...the line the dots stand beside: the working element, or the row it sits in
      let e = w; while (e && !e.innerText.trim() && e.parentElement && !e.parentElement.hasAttribute("data-tq-item")) e = e.parentElement;
      return (e?.innerText || "").replace(/\s+/g, " ").slice(0, 160); })(), lit, cards, tail: (vp?.innerText || "").slice(-600) };
  });
  // WHAT IT IS DOING, AT ALL TIMES: a working agent always has its line, and the line moves on
  if (c.working && !st.line.trim()) note("working with no line that says what it does");
  if (c.working && st.line && st.line === lastLine) { if ((sameLine += 5) === 300) note(`the same working line for 5 min: "${st.line}"`); } else sameLine = 0;
  lastLine = st.line;
  if (n % 3 === 0) { const x = { s: s(), working: c.working, line: st.line, lit: st.lit.join(" | "), queue: c.queue }; log.push(x); console.log(JSON.stringify(x));
    if (n % 12 === 0) await shot(page, `${name}-${String(s()).padStart(5, "0")}`); }
  // A PAGE HANDED TO HIM (a sign-up's press, a held click - browsergate.hand_over): he presses the site's own button in the pane - Enter in its form
  const pane = await page.evaluate(() => { const c = document.querySelector("[data-tq-task-page] canvas"); if (!c) return null; const b = c.getBoundingClientRect(); return b.width ? [b.left, b.top, b.width, b.height] : null; });
  if (pane && !c.working) {
    if ((pagePresses += 1) > 25) { note("pressed on the page 25 times and it is still handed to him"); break; }
    await shot(page, `${name}-page-${pagePresses}`);
    const [x, y, w, h] = pane; await page.mouse.click(x + w / 2, y + h * 0.3); await sleep(400); await page.keyboard.press("Enter");
    pressed.push({ s: s(), go: "Enter on the page", what: st.tail.slice(-160) }); console.log(`[${s()}s] PRESSED Enter on the page: ${st.tail.slice(-160).replace(/\n/g, " ")}`);
    calm = 0; await sleep(4000); continue;
  }
  // A CARD: pressed as he would, its go-ahead - and what it said kept, to catch the same thing asked again
  const go = st.lit.find((b) => GO.test(b) && !STOP.test(b));
  if (go && !c.working || go && /Allow|Trust/.test(go)) {
    const what = st.cards.at(-1) || st.tail.slice(-200);
    if (pressed.some((p) => p.what === what)) note(`asked again for what he already pressed: "${what.slice(0, 140)}"`);
    await shot(page, `${name}-card-${pressed.length}`);
    const r = await page.evaluate((go) => { const b = [...document.querySelectorAll("[data-tq-task-page] [data-tq-turn-cards] button, [data-tq-task-page] [data-tq-ask] button, [data-tq-task-page] [data-tq-permission] button")]
      .filter((b) => !b.disabled && b.getBoundingClientRect().width && b.innerText.trim().replace(/\s+/g, " ") === go).pop(); b?.click(); return !!b; }, go);
    pressed.push({ s: s(), go, what }); console.log(`[${s()}s] PRESSED ${go} on: ${what.slice(0, 200)}`); calm = 0; continue;
  }
  if (c.working) { calm = 0; continue; }
  // AT REST: a question of his to answer, or the end
  const last = String(c.items.filter((x) => x.kind === "turn").at(-1)?.text || "");
  const q = /\?\s*$/.test(last.trim()) || /\?\s*\n/.test(last.slice(-300));
  if (q && asked.length < 6) {
    if (asked.some((a) => a.q === last.slice(-300))) note("the same question twice");
    if (pressed.length && /should I|shall I|do you want me to|want me to (send|go)|ready to send|go ahead/i.test(last.slice(-300))) note(`asked for a go-ahead in words after a press, not a card: "${last.slice(-200)}"`);
    const a = ANSWERS.find(([re]) => re.test(last.slice(-400)))[1];
    asked.push({ s: s(), q: last.slice(-300), a }); console.log(`[${s()}s] ASKED: ${last.slice(-300).replace(/\n/g, " ")}\n  ANSWER: ${a}`);
    await type(page, a); calm = 0; continue;
  }
  if ((calm += 5) >= 30) break;
}
await rest(page, t, 120000); await sleep(3000); await shot(page, `${name}-end`);
const fr = await page.evaluate(() => window.__frames), bad = [...new Set(check(fr))];
const sent = existsSync(outbox) ? readFileSync(outbox, "utf8").split("\n").filter(Boolean).slice(sentBefore) : [];
const reviews = (await api(`/api/tasks/${t}`))?.reviews || [];
const conv = await api(`/api/tasks/${t}/conversation`);
await save(`${name}-frames.json`, fr); await save(`${name}-log.json`, { log, pressed, asked, found, bad, sent: sent.length });
await save(`${name}-said.txt`, conv.items.map((x) => `[${x.kind}${x.who ? " " + x.who : ""}] ${String(x.text || x.title || "").slice(0, 3000)}`).join("\n\n"));
await rec.stop({ sheet: 16 });
console.log(`\n== ${name}: TOOK ${s()}s · task ${t} · presses ${pressed.length} · questions ${asked.length} · SENT ${sent.length} · cards ${JSON.stringify(reviews.reduce((m, r) => ({ ...m, [`${r.Kind}:${r.Status}`]: (m[`${r.Kind}:${r.Status}`] || 0) + 1 }), {}))}`);
console.log("FINDINGS\n" + [...found, ...bad.slice(0, 25)].join("\n"));
console.log("BUTTONS", (await buttons(page)).slice(0, 300));
await browser.disconnect();
process.exit(0);
