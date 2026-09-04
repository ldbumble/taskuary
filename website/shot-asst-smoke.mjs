// A walk through every chat interaction on the Assistant tab against a --demo server: the opening
// brief, the walk, the quick chips, a typed decision, a typed lookup, the pipe's All list, past
// chats and New chat. Prints what the chat said at each stop and any page error.
//   node website/shot-asst-smoke.mjs <url> <outdir>
import { launch } from "./browser.mjs";
const [url, out] = process.argv.slice(2);
const b = await launch(); const p = await b.newPage();
const errors = []; p.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
p.on("console", (m) => { if (m.type() === "error" && !/403|404/.test(m.text())) errors.push(`console: ${m.text().slice(0, 160)}`); });
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
const click = (label) => p.evaluate((l) => { const el = [...document.querySelectorAll("button")].find((x) => x.textContent.trim() === l || x.getAttribute("aria-label") === l || x.title === l); if (el) el.click(); return !!el; }, label);
const last = () => p.evaluate(() => { const ms = [...document.querySelectorAll(".tq-msg")]; return ms.slice(-2).map((m) => m.innerText.replace(/\s+/g, " ").slice(0, 140)); });
const type = async (t) => { await p.type(".tq-compose-box textarea", t); await p.keyboard.press("Enter"); };
const steps = [];
const note = async (what) => { steps.push([what, await last(), await p.evaluate(() => String(document.querySelectorAll(".tq-pile-row").length))]); };
await p.setViewport({ width: 1440, height: 900 });
await p.goto(url, { waitUntil: "networkidle0" }); await wait(8000);
await note("open");
await click("Start with the mail"); await wait(3500); await note("start with the mail");
await click("Done"); await wait(3500); await note("Done chip");
await click("Later"); await wait(3500); await note("Later chip");
await type("not my issue, let them sort it out"); await wait(4500); await note("typed: not my issue");
await type("what did Marcus send?"); await wait(4500); await note("typed lookup: Marcus");
await click("Next"); await wait(3500); await note("Next chip");
await click("Read it"); await wait(1500); await note("Read it (inline)");
await p.evaluate(() => document.querySelector(".tqRow [data-tq-keep]")?.click()); await wait(3500); await note("Timeline row → pull it in");
await click("Past chats"); await wait(800); await note("chats open");
await p.evaluate(() => document.querySelector(".tq-chats-head button")?.click()); await wait(300);
await click("New chat — archives this one"); await wait(6000); await note("new chat");
await p.screenshot({ path: `${out}/asst-smoke.png` });
for (const [what, said, n] of steps) console.log(`\n## ${what} (pipe ${n})\n` + said.map((s) => `  ${s}`).join("\n"));
console.log("\nerrors:", errors.length ? errors.join("\n") : "none");
await b.close();
