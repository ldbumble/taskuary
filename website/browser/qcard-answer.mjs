// THE OWNER'S HANDS ON A QUESTIONS CARD (not a test: nothing here runs in CI): on the instance real-run.mjs keeps up, pick a choice or type
// into a question's own line, as a person does, then say what the card shows.
//   node qcard-answer.mjs pick "<choice words>"        press that pick
//   node qcard-answer.mjs write <n> "<words>"          type into the n-th question's line (1 = first)
//   node qcard-answer.mjs show <name>                  the card scrolled into view, a screenshot <name>.png, and what it reads
import { connect, shot, sleep } from "./real-lib.mjs";
const [cmd, a, b] = process.argv.slice(2);
const { browser, page } = await connect();
const at = (sel, n = 0) => page.evaluate((sel, n) => { const e = [...document.querySelectorAll(sel)].filter((e) => e.getBoundingClientRect().width > 0)[n];
  if (!e) return null; e.scrollIntoView({ block: "center" }); const q = e.getBoundingClientRect(); return { x: q.x + q.width / 2, y: q.y + q.height / 2 }; }, sel, n);
if (cmd === "pick") { const p = await at(`[data-tq-ask-choice="${a}"]`); if (p) await page.mouse.click(p.x, p.y); console.log(p ? `picked ${a}` : `no pick says ${a}`); }
if (cmd === "write") { const p = await at("[data-tq-ask-line]", Number(a) - 1); if (p) { await page.mouse.click(p.x, p.y); await page.keyboard.type(b); } console.log(p ? `wrote in question ${a}` : `no line ${a}`); }
await sleep(500);
if (cmd === "show") { await page.evaluate((top) => (document.querySelector("[data-tq-review-kind=questions]") || [...document.querySelectorAll("[data-tq-passed]")].pop())?.scrollIntoView({ block: top ? "start" : "end" }), a.includes("top")); await sleep(400); console.log("SCREENSHOT", await shot(page, a)); }
console.log(await page.evaluate(() => [...document.querySelectorAll("[data-tq-ask]")].map((q) => `${q.querySelector("[data-tq-ask-question]")?.innerText} -> ${
  q.querySelector("[aria-pressed=true]")?.innerText || q.querySelector("textarea")?.value || q.querySelector("[data-tq-ask-answer]")?.innerText || "(empty)"}`).join("\n")));
console.log("PRESS ROW:", await page.evaluate(() => [...document.querySelectorAll("[data-tq-review-kind=questions] [data-tq-press]")].map((b) => b.innerText + (b.disabled ? " (off)" : "")).join(" | ")));
await browser.disconnect();
