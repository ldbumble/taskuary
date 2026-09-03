// Drive the Assistant tab like an owner would: open, start the walk, click chips, type words; after every
// step record what the chat said, what the pipe holds, any "By the way" bar, and page errors.
//   node ui.mjs <url-with-token> <outdir> <scenario.json>
import { launch } from "file:///C:/Users/unussbaum/Documents/General/Testing/taskhub/website/browser.mjs";
import { writeFileSync, readFileSync, mkdirSync } from "node:fs";
const [url, out, scenarioPath] = process.argv.slice(2);
mkdirSync(out, { recursive: true });
const steps = JSON.parse(readFileSync(scenarioPath, "utf8"));
const b = await launch(); const p = await b.newPage();
const errors = []; p.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
p.on("console", (m) => { if (m.type() === "error" && !/403|404/.test(m.text())) errors.push(`console: ${m.text().slice(0, 200)}`); });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const clickText = (label) => p.evaluate((l) => {
  const els = [...document.querySelectorAll("button, [role=button]")].filter((x) => x.offsetWidth > 0);
  const el = els.find((x) => x.textContent.trim() === l) || els.find((x) => x.getAttribute("aria-label") === l || x.title === l) || els.find((x) => x.textContent.trim().startsWith(l));
  if (el) el.click(); return !!el;
}, label);
const state = () => p.evaluate(() => {
  const msgs = [...document.querySelectorAll(".tq-msg")].slice(-4).map((m) => {
    const role = m.classList.contains("you") ? "YOU" : m.classList.contains("receipt") ? "RECEIPT" : "TQ";
    const card = m.querySelector(".tq-card, [class*=tq-card]");
    const buttons = [...m.querySelectorAll("button")].filter((x) => x.offsetWidth > 0).map((x) => x.textContent.trim()).filter(Boolean);
    return `${role}: ${m.innerText.replace(/\s+/g, " ").slice(0, 260)}${buttons.length ? `  [buttons: ${buttons.join(" | ")}]` : ""}`;
  });
  const rows = [...document.querySelectorAll(".tq-pipe-stack > div")].map((r) => r.innerText.replace(/\s+/g, " ").slice(0, 110));
  const n = document.querySelector(".tq-pipe-head .n")?.textContent;
  const btw = document.querySelector(".tq-btw")?.innerText.replace(/\s+/g, " ");
  const quick = [...document.querySelectorAll(".tq-quick button")].map((x) => `${x.textContent.trim()}${x.disabled ? "(off)" : ""}`);
  const mouth = document.querySelector(".tq-pipe-mouth")?.textContent;
  const err = document.querySelector(".MuiAlert-message, .tq-err, [role=alert]")?.innerText?.slice(0, 200);
  const typing = !!document.querySelector(".tq-typing");
  return { n, rows, msgs, btw, quick, mouth, err, typing };
});
const settle = async (max = 25000) => { const t0 = Date.now(); await wait(600); while (Date.now() - t0 < max) { const s = await p.evaluate(() => !!document.querySelector(".tq-typing")); if (!s) break; await wait(400); } await wait(500); };
const log = [];
const note = async (what) => { const s = await state(); log.push({ what, ...s }); console.log(`\n## ${what}  (pipe ${s.n}${s.mouth ? ", " + s.mouth : ""})${s.btw ? `\n   BTW: ${s.btw}` : ""}${s.err ? `\n   ERR: ${s.err}` : ""}\n   pipe: ${JSON.stringify(s.rows)}\n` + s.msgs.map((m) => `   ${m}`).join("\n") + `\n   quick: ${s.quick.join(" ")}`); };
await p.setViewport({ width: 1440, height: 900 });
await p.goto(url, { waitUntil: "load" }); await wait(6000);
let i = 0;
for (const st of steps) {
  i++;
  if (st.click) { const ok = await clickText(st.click); if (!ok) console.log(`   (no button ${JSON.stringify(st.click)})`); }
  if (st.type) { await p.click(".tq-compose-box textarea"); await p.type(".tq-compose-box textarea", st.type); await p.keyboard.press("Enter"); }
  if (st.wait) await wait(st.wait);
  await settle();
  await note(`${i}. ${st.click ? "click " + JSON.stringify(st.click) : st.type ? "type " + JSON.stringify(st.type) : st.note || "look"}`);
  if (st.shot) await p.screenshot({ path: `${out}/${String(i).padStart(2, "0")}-${st.shot}.png` });
}
await p.screenshot({ path: `${out}/final.png` });
writeFileSync(`${out}/log.json`, JSON.stringify(log, null, 1));
console.log("\nerrors:", errors.length ? errors.join("\n") : "none");
await b.close();
