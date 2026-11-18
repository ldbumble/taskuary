// FILES THROUGH THE BOX, ON THE REAL CLI (not a test: nothing here runs in CI). node real-attach.mjs <name>
// A picture and a PDF dropped on a general task's box with his line, then a sheet on a second line mid-chat: each must sit on HIS line as a
// chip, and the agent must have READ each - its own session log (the CLI's, not the app's) is searched for a Read of every file.
import path from "node:path";
import os from "node:os";
import { readFile, readdir, stat, writeFile, mkdir } from "node:fs/promises";
import { api, connect, open, chat, shot, save, sleep, quiet, type, out } from "./real-lib.mjs";
import { record } from "./recorder.mjs";

const [name = "attach"] = process.argv.slice(2);
const dir = path.join(out, `${name}-files`); await mkdir(dir, { recursive: true });
// ...invented content the agent can only know by reading it
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
const pdf = `%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj 3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 100]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj 4 0 obj<</Length 60>>stream\nBT /F1 14 Tf 10 50 Td (October total: 48210 dollars) Tj ET\nendstream endobj 5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF`;
const files = { "totals.png": png, "october-report.pdf": pdf, "budget.csv": "line,amount\nvenue,9100\ncatering,4400\nTOTAL,13500\n" };
for (const [f, b] of Object.entries(files)) await writeFile(path.join(dir, f), b);

const got = await api("/api/tasks", { Title: "Look over the October pack", Kind: "general" }); const tid = got.taskId;
console.log("task", tid);
const { page } = await connect();
await page.reload({ waitUntil: "domcontentloaded" }); await sleep(2500); await open(page, tid);
await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 60000 });
const rec = await record(page, path.join(out, "video", name));
const findings = [];
const drop = async (names, words) => {
  const input = await page.$("[data-tq-task-page] input[type=file]");
  if (!input) { findings.push("no file input on the task's box"); return; }
  await input.uploadFile(...names.map((f) => path.join(dir, f))); await sleep(1500);
  await type(page, words); await sleep(4000);
  await quiet(page, 240000, 6000);
  const c = await chat(page);
  for (const f of names) if (!c.includes(f)) findings.push(`${f} is not on his line in the chat`);
};
await drop(["totals.png", "october-report.pdf"], "Here is the October pack. What total does the PDF give?");
await shot(page, `${name}-1`);
await drop(["budget.csv"], "And this budget - what is its TOTAL row?");
await shot(page, `${name}-2`);
const c = await chat(page); await save(`${name}-chat.txt`, c);
if (!/48[, ]?210/.test(c)) findings.push("the agent never said the PDF's total (48210) - it did not read it");
if (!/13[, ]?500/.test(c)) findings.push("the agent never said the sheet's TOTAL (13500) - it did not read it");
// ...the agent's OWN log: the newest Claude session files written since the walk began, searched for each file's name
const proj = path.join(os.homedir(), ".claude", "projects"), since = Date.now() - 20 * 60000, logs = [];
for (const d of await readdir(proj).catch(() => [])) for (const f of await readdir(path.join(proj, d)).catch(() => []))
  if (f.endsWith(".jsonl")) { const p = path.join(proj, d, f); if ((await stat(p)).mtimeMs > since) logs.push(p); }
const text = (await Promise.all(logs.map((p) => readFile(p, "utf8")))).join("\n");
for (const f of Object.keys(files)) if (!text.includes(f)) findings.push(`the agent's own log never names ${f}`);
await rec.stop?.();
await save(`${name}-findings.txt`, findings.join("\n") || "no finding");
console.log(findings.length ? findings.join("\n") : "no finding"); console.log(c.slice(-1500));
process.exit(0);
