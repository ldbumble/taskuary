// The routing card, shot in every state a first-time owner meets it in: the straight report that
// asks no AI, one line handed to the AI, the prompt it is actually given, the Timeline silenced
// (and why it cannot be), and the replay of the runs already in the history.
//   node website/shot_routing.mjs <url> <outdir>
import fs from "node:fs";
import path from "node:path";
import { launch } from "./browser.mjs";

const [url, outdir] = process.argv.slice(2);
fs.mkdirSync(outdir, { recursive: true });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const b = await launch();
const p = await b.newPage();
await p.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 2 });
const errs = [];
p.on("pageerror", (e) => errs.push(`PAGE ${e.message}`));
p.on("console", (m) => m.type() === "error" && errs.push(`CONSOLE ${m.text().slice(0, 160)}`));

const clickText = (label, tags = "div,span,button,a,p,li") => p.evaluate((l, t) => {
  const norm = (x) => (x || "").replace(/\s+/g, " ").trim();
  const els = [...document.querySelectorAll(t)].filter((d) => d.childElementCount <= 3 && norm(d.textContent) === l);
  const el = els.find((e) => e.offsetParent !== null) || els[0];
  if (!el) return false;
  el.click(); return true;
}, label, tags);

// the card, not the whole page: what the owner is actually reading at that moment
const CARD = `[...document.querySelectorAll("div")].filter((d) => /^ONE PROMPT THAT ROUTES EACH RUN/.test((d.innerText || "").trim()) && d.offsetParent)[0]`;
// the element shoots itself: puppeteer does its own scrolling, and a rect measured by hand lands
// on whatever used to be at those coordinates
const shot = async (name, note = "") => {
  const file = path.join(outdir, `${name}.png`);
  const h = await p.evaluateHandle(CARD);
  const el = h.asElement();
  if (el) await el.screenshot({ path: file });
  else await p.screenshot({ path: file });
  console.log(`  ${name}.png${note ? "  — " + note : ""}${el ? "" : "  (card not found - full page)"}`);
};

// what a first-time reader can actually see on the card, in order
const read = () => p.evaluate(() => {
  const card = [...document.querySelectorAll("div")]
    .find((d) => /^ONE PROMPT THAT ROUTES EACH RUN/.test((d.innerText || "").trim()));
  if (!card) return { missing: true };
  const vw = window.innerWidth;
  const clipped = [...card.querySelectorAll("button,input,textarea,[role=combobox]")]
    .filter((e) => e.offsetParent !== null)
    .map((e) => ({ t: (e.textContent || e.placeholder || e.tagName).trim().slice(0, 32), r: e.getBoundingClientRect() }))
    .filter(({ r }) => r.width > 0 && (r.right > vw + 2 || r.left < -2)).map((x) => x.t);
  return { text: card.innerText.replace(/\n{2,}/g, "\n"), clipped, height: Math.round(card.getBoundingClientRect().height) };
});

// a real click on the real control, because a synthetic one on a MUI Select opens nothing
const setLine = async (label, choice) => {
  const opened = await p.evaluate((l) => {
    const row = [...document.querySelectorAll("p")].find((e) => (e.textContent || "").trim() === l)?.parentElement?.parentElement;
    const box = row?.querySelector("[role=combobox]");
    if (!box) return null;
    box.scrollIntoView({ block: "center" });
    const r = box.getBoundingClientRect();
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
  }, label);
  if (!opened) return console.log(`  ! no control for "${label}"`);
  await p.mouse.click(opened.x, opened.y);
  await wait(500);
  const picked = await p.evaluate((c) => {
    const o = [...document.querySelectorAll("li[role=option]")].find((e) => (e.textContent || "").trim() === c);
    if (!o || o.getAttribute("aria-disabled") === "true") return false;
    o.click(); return true;
  }, choice);
  console.log(`  ${label} -> ${choice}: ${picked ? "set" : "NOT SETTABLE"}`);
  await wait(500);
};

await p.goto(url, { waitUntil: "networkidle0" });
await wait(2500);
if (await p.$('[role="dialog"]')) { await p.keyboard.press("Escape"); await wait(600); }   // the setup panel on a fresh home
await clickText("Reports");
await wait(1800);
// a rows report that has actually run, so the replay has something to replay
const openReport = async (name) => {
  const els = await p.$$("div,button,span,li");
  for (const e of els) {
    const t = await p.evaluate((n) => (n.textContent || "").replace(/\s+/g, " ").trim(), e);
    if (t === name && (await e.boundingBox())) { await e.click(); return true; }
  }
  return false;
};
console.log("opened:", await openReport(process.env.REPORT || "Headcount by site, nightly"));
await wait(2500);

console.log("--- the card, state by state ---");
await shot("01-default", "as a saved report opens it");
console.log(JSON.stringify(await read(), null, 1).slice(0, 1400));
await setLine("put it on my Work rail", "ask the AI");
await shot("02-ask-the-ai", "picked, before a word is typed");
await p.evaluate(() => {
  const ta = [...document.querySelectorAll("textarea")].find((t) => /any error at all/.test(t.placeholder || ""));
  if (!ta) return;
  const set = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
  set.call(ta, "any error at all, or a job that did not run when it should have");
  ta.dispatchEvent(new Event("input", { bubbles: true }));
});
await wait(700);
await shot("02b-the-sentence", "the rule in the owner's words");
await clickText("see the prompt ⌄", "button,span");
await wait(500);
await shot("03-the-prompt", "what the model is literally asked");
await clickText("try it on the last 5 runs", "button,span");
await wait(3500);
await shot("04-replay", "the rule fired against runs that already happened");
console.log(JSON.stringify(await read(), null, 1).slice(0, 1800));
await p.setViewport({ width: 390, height: 844, isMobile: true, deviceScaleFactor: 2 });
await p.goto(url + "#reports", { waitUntil: "networkidle0" });
await wait(2500);
if (await p.$('[role="dialog"]')) { await p.keyboard.press("Escape"); await wait(600); }
await clickText("Reports");
await wait(1800);
await openReport(process.env.REPORT || "Headcount by site, nightly");
await wait(2500);
await setLine("put it on my Work rail", "ask the AI");
await shot("05-phone", "390px");
console.log("phone, cut off at the edge:", JSON.stringify((await read()).clipped));
console.log(errs.length ? "ERRORS:\n" + errs.join("\n") : "no page or console errors");
await b.close();
