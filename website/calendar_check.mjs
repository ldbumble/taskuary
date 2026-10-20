// The calendar's buttons on a running demo (calwrite.py): the invite's row offers Accept / Decline / Propose a new time and says what it
// clashes with; Accept lands a draft on the table with Send; Propose a new time opens the free times; the thread asking for half an hour
// offers Find a time, and a pick drafts the invite. Nothing is sent - the demo refuses Send as it refuses every send.
//
//   node website/calendar_check.mjs --port 8981 --token <token> --out <folder for the shots>
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { launch } from "./browser.mjs";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
const base = `http://127.0.0.1:${arg("--port", "8981")}`, token = arg("--token", ""), out = arg("--out", ".");
mkdirSync(out, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const fails = [];
const ok = (cond, what) => { console.log(`${cond ? "ok  " : "FAIL"} ${what}`); if (!cond) fails.push(what); };

const browser = await launch();
const page = await browser.newPage();
await page.setViewport({ width: 1366, height: 860 });
await page.evaluateOnNewDocument((t) => { try { localStorage.setItem("taskuary_token", t); } catch { /* none */ } }, token);
page.on("pageerror", (e) => fails.push(`page error: ${e.message}`));
await page.goto(base, { waitUntil: "networkidle2" });
await wait(4000);

const rowWords = () => page.evaluate(() => [...document.querySelectorAll("[data-tq-row] button")].filter((b) => b.getBoundingClientRect().width > 0).map((b) => b.innerText.trim()));
const press = async (word) => {
  for (const b of await page.$$("[data-tq-row] button")) if (await b.evaluate((e, w) => e.innerText.trim() === w && e.getBoundingClientRect().width > 0, word)) { await b.click(); return true; }
  // ...or behind one of the row's ▾ menus
  for (const more of await page.$$("[data-tq-row] [data-tq-more]")) {
    await more.click(); await wait(500);
    for (const m of await page.$$("[role='menuitem']")) if (await m.evaluate((e, w) => e.innerText.trim() === w, word)) { await m.click(); return true; }
    await page.keyboard.press("Escape"); await wait(300);
  }
  return false;
};
const menuWords = async () => {
  const out = [];
  for (const more of await page.$$("[data-tq-row] [data-tq-more]")) {
    await more.click(); await wait(400);
    out.push(...await page.$$eval("[role='menuitem']", (xs) => xs.map((x) => x.innerText.trim())));
    await page.keyboard.press("Escape"); await wait(300);
  }
  return out;
};
const open = async (words) => {
  const key = await page.evaluate((w) => [...document.querySelectorAll("[data-tq-rail] [data-tq-key]")].find((e) => e.innerText.includes(w))?.getAttribute("data-tq-key"), words);
  if (!key) return false;
  await page.click(`[data-tq-rail] [data-tq-key="${key}"]`); await wait(3500); return true;
};

// 1. the invite
ok(await open("AP cutover dry run"), "the invite is on the rail");
let words = [...await rowWords(), ...await menuWords()];
ok(["Accept", "Decline", "Propose a new time"].every((w) => words.includes(w)) && !words.includes("Reply"), `the row: ${JSON.stringify(words)}`);
const said = await page.evaluate(() => document.querySelector("[data-tq-invite]")?.innerText || "");
ok(/clashes with Quarter-end planning/.test(said), `the card says what it clashes with: ${JSON.stringify(said)}`);
await page.screenshot({ path: join(out, "1-invite-row.png") });

ok(await press("Propose a new time"), "Propose a new time pressed");
await wait(2000);
const slots = await page.evaluate(() => [...document.querySelectorAll("[data-tq-slots] button")].map((b) => b.innerText.trim()));
ok(slots.length >= 2 && slots.length <= 3, `the free times: ${JSON.stringify(slots)}`);
await page.screenshot({ path: join(out, "2-propose-slots.png") });
await page.keyboard.press("Escape"); await wait(600);

ok(await press("Accept"), "Accept pressed");
await wait(4500);
const cal = await page.evaluate(() => document.querySelector("[data-tq-calendar]")?.innerText || "");
ok(/Accept · AP cutover dry run/.test(cal), `the draft on the table: ${JSON.stringify(cal)}`);
ok(await page.evaluate(() => [...document.querySelectorAll("button")].some((b) => b.innerText.trim() === "Send" && b.getBoundingClientRect().width > 0)), "Send is there for the owner's yes");
// the demo's Send says it is the demo - nothing reaches a calendar
ok(await press("Send") || await page.evaluate(() => { const b = [...document.querySelectorAll("button")].find((x) => x.innerText.trim() === "Send"); b?.click(); return !!b; }), "Send pressed");
await wait(2500);
ok(/This is the demo - nothing is sent/.test(await page.evaluate(() => document.body.innerText)), "the demo refuses the send in its own words");
await page.screenshot({ path: join(out, "3-accept-drafted.png") });

// 2. the thread asking for half an hour
ok(await open("Half an hour"), "the thread asking to meet is on the rail");
words = [...await rowWords(), ...await menuWords()];
ok(words.includes("Find a time"), `its row: ${JSON.stringify(words)}`);
ok(await press("Find a time"), "Find a time pressed");
await wait(2000);
const free = await page.evaluate(() => [...document.querySelectorAll("[data-tq-slots] button")].map((b) => b.innerText.trim()));
ok(free.length >= 2, `the free times: ${JSON.stringify(free)}`);
await page.screenshot({ path: join(out, "4-find-a-time.png") });
const first = await page.$("[data-tq-slots] button");
if (first) { await first.click(); await wait(4500); }
const inv = await page.evaluate(() => document.querySelector("[data-tq-calendar]")?.innerText || "");
ok(/Invite · Audit list/.test(inv), `the invite drafted: ${JSON.stringify(inv)}`);
await page.screenshot({ path: join(out, "5-invite-drafted.png") });

await browser.close();
console.log(fails.length ? `\n${fails.length} failed:\n${fails.join("\n")}` : "\nall good");
process.exit(fails.length ? 1 : 0);
