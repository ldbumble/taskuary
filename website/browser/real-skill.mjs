// A ROUTINE THAT USES A SKILL, AND HIS ASK ABOUT HOW ITS JOB IS DONE, ON THE REAL CLI (not a test: nothing here runs in CI).
// node real-skill.mjs <out folder> [his words]. Against the instance real-run.mjs keeps up. The owner, 2026-11-26: asked to update his post
// routine, an agent grew the routine's instructions to ~3,000 characters where the style lives in its skill, behind a card that showed
// neither. A routine "Social posts" linked to the skill social-posts; he asks; the walk writes down what the agent read, the card it raised
// (which document, how long before and after), shoots it, presses Approve and reads back what was saved.
import path from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import { api, connect, open, quiet, sleep, buttons } from "./real-lib.mjs";

const [OUT = path.resolve("real-skill-out"), ASK = "make my social posts punchier"] = process.argv.slice(2);
const PAGE = `---
name: social-posts
description: Write Northwind's social posts. Use when a post is due on LinkedIn, X or Reddit.
---
# Social posts

Voice: plain and direct. One idea a post.

1. Open with the lesson.
2. LinkedIn: 80 to 120 words, a short story, then the lesson.
3. X: under 260 characters.
4. Reddit: a title that says what was learned, a body that shows the numbers.
5. No hashtags, no emoji.
`;
const PROMPT = "Write this week's LinkedIn, X and Reddit posts about what Northwind learned, each set up as a post card for my press.";
const said = [], say = (s) => { said.push(s); console.log(s); };
await mkdir(OUT, { recursive: true });
const seed = await api("/api/fixture/routine", { skill: { name: "social-posts", text: PAGE },
  cfg: { title: "Social posts", prompt: PROMPT, goal: "A post card per network each week.", skill: "social-posts", daily_at: "09:00" } });
say(`seeded: ${JSON.stringify(seed)}`);
const got = await api("/api/tasks", { Title: ASK, Kind: "general" }), tid = got.taskId;
say(`asked: ${JSON.stringify(ASK)} -> task ${tid} ${JSON.stringify(await api(`/api/tasks/${tid}/dispatch`, { kind: "general" })).slice(0, 160)}`);
const { browser, page } = await connect();
await page.setViewport({ width: 1440, height: 1300 });
await page.reload({ waitUntil: "domcontentloaded" }); await sleep(3000);
await open(page, tid);
const CARD = "[data-tq-task-page] [data-tq-review-card]";
const cards = async () => ((await api(`/api/tasks/${tid}`))?.reviews || []).filter((r) => r.Kind === "action");
let rows = [];
for (let i = 0; i < 150 && !rows.length; i++) { await sleep(4000); rows = await cards(); if (i % 5 === 4) say(`  ... ${i * 4 + 4}s, no card yet`); }
await quiet(page, 240000);
await page.screenshot({ path: path.join(OUT, "real-1-page.png") });
for (const [i, el] of (await page.$$(CARD)).entries()) await el.screenshot({ path: path.join(OUT, `real-1-card${i ? `-${i + 1}` : ""}.png`) });
for (const r of rows) { const p = JSON.parse(r.DraftText || "{}");
  say(`card rv${r.ReviewId}: action ${p.action}${p.slug ? `, skill ${p.slug}` : ""}${p.title ? `, routine ${p.title}` : ""} (${r.Status})`);
  if (p.action === "save_skill") say(`  the skill page: ${(p.was_text || "").trim().length} -> ${String(p.text || "").trim().length} characters; used by ${JSON.stringify(p.used_by || [])}`);
  for (const t of p.texts || []) say(`  ${t.label}: ${String(t.was).trim().length} -> ${String(t.now).trim().length} characters`);
  if (p.after) say(`  after: ${p.after.map((a) => `${a.label} ${a.now}${a.was ? ` (was ${a.was})` : ""}`).join(" · ")}`); }
say(`on the card:\n${(await page.evaluate((c) => [...document.querySelectorAll(c)].map((x) => x.innerText).join("\n=====\n"), CARD)).split("\n").map((l) => `    ${l}`).join("\n")}`);
const conv = await api(`/api/tasks/${tid}/conversation`);
await writeFile(path.join(OUT, "real-conversation.json"), JSON.stringify(conv, null, 1));
say(`buttons: ${await buttons(page)}`);
if (rows.length) {
  const pressed = await page.evaluate((c) => { const b = [...document.querySelectorAll(`${c} button`)].find((x) => x.innerText.trim() === "Approve" && !x.disabled); if (!b) return "no Approve"; b.click(); return "Approve"; }, CARD);
  await sleep(8000); await quiet(page, 120000);
  await page.screenshot({ path: path.join(OUT, "real-2-approved.png") });
  const skill = (await api("/api/fixture/skill/social-posts")).text, cfg = await api(`/api/fixture/routine/${seed.sourceId}`);
  const shown = JSON.parse(rows.find((r) => JSON.parse(r.DraftText || "{}").action === "save_skill")?.DraftText || "{}").text;
  say(`pressed ${pressed}; the skill changed: ${skill !== PAGE}${shown ? `; saved is the page shown: ${skill.trim() === String(shown).trim()}` : ""}; the routine's instructions unchanged: ${cfg.prompt === PROMPT} (${String(cfg.prompt).length} characters)`);
  say(`the skill now:\n${String(skill).split("\n").map((l) => `    ${l}`).join("\n")}`);
}
await writeFile(path.join(OUT, "real-README.txt"), said.join("\n") + "\n");
await browser.disconnect();
