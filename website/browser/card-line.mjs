// THREE POSTS IN LINE, DRAWN AND PRESSED (not a test: nothing here runs in CI). node browser/card-line.mjs <out folder>
// The owner, 2026-11-25: the cards waiting in line are one card with a tab each (11-26: a press never changes the tab shown). Three
// posts - X, LinkedIn, Reddit, each network connected to a stand-in - on a chat task in a disposable home; each press recorded (recorder.mjs),
// and the line's top, height and shown tab sampled every frame: a jump, a blank beat or a second card is a finding.
import path from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import { startHarness } from "./harness.mjs";
import { record } from "./recorder.mjs";

const OUT = process.argv[2] || path.resolve("card-line-out");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const POSTS = [["x_post", "We shipped the ledger export - totals now round to cents."], ["linkedin_post", "The ledger export now rounds totals to cents. Thanks to everyone who reported it."],
  ["reddit_post", "Ledger export update: totals round to cents now. Notes in the changelog."]];
const h = await startHarness({ fresh: true });
const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token },
  body: body && JSON.stringify(body) }).then((r) => r.json());
const said = [];
try {
  await api("/api/setup/first-run/ai", { name: "claude" }); await api("/api/setup/dismiss", { dismissed: true });
  const { taskId } = await api("/api/fixture/review-rows", { title: "Announce the export fix", connect: ["x", "linkedin", "reddit"], ask: "Post the export fix on X, LinkedIn and Reddit.",
    answer: "Three posts are set up below, one for each network.", rows: POSTS.map(([type, text]) => ({ Kind: "action", Reason: "the post you asked for",
      DraftText: { action: "run_tool", type, text, why: "he asked", ...(type === "reddit_post" ? { title: "Ledger export: totals round to cents", subreddit: "accounting" } : {}) } })) });
  await api(`/api/tasks/${taskId}/trust`, {});      // ...the fixture's task came in on a colleague's mail no one had trusted yet: he does, first
  await mkdir(OUT, { recursive: true });
  const page = await h.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message)); page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 300)); });
  await page.setViewport({ width: 1440, height: 1000 });
  await page.goto(`${h.ui}/#task=${taskId}`, { waitUntil: "domcontentloaded" });
  try { await page.waitForSelector("[data-tq-task-page] [data-tq-review-card]", { visible: true, timeout: 90000 }); }
  catch (e) { await page.screenshot({ path: path.join(OUT, "no-card.png") }); throw new Error(`no card drawn: ${(await page.evaluate(() => document.body.innerText)).slice(0, 600)}`); }
  await sleep(2500);
  await page.screenshot({ path: path.join(OUT, "0-waiting.png") });
  const rec = await record(page, path.join(OUT, "video"), { secs: 60, mb: 80 });
  await page.evaluate(() => { window.__look = []; const t0 = performance.now(); const tick = () => {
    const l = document.querySelector("[data-tq-card-line]"), cs = [...document.querySelectorAll("[data-tq-task-page] [data-tq-review-card]")];
    const b = (l || cs[0])?.getBoundingClientRect();
    window.__look.push([Math.round(performance.now() - t0), cs.length, Math.round(b?.top || 0), Math.round(b?.height || 0), l?.getAttribute("data-tq-line-at") || "",
      document.querySelector("[data-tq-card-queue]")?.innerText || ""]);
    if (window.__look.length < 3000) requestAnimationFrame(tick); }; requestAnimationFrame(tick); });
  // ...the press of the card he sees: the shown tab's, or the one card drawn where there are no tabs
  const press = (re) => page.evaluate((src) => {
    const scope = document.querySelector("[data-tq-line-pane]:not([inert])") || [...document.querySelectorAll("[data-tq-task-page] [data-tq-review-card]")].pop();
    const b = [...(scope?.querySelectorAll("button") || [])].find((x) => new RegExp(src).test(x.innerText.trim()) && !x.disabled);
    if (!b) return "no button"; b.click(); return b.innerText.trim(); }, re.source);
  const tab = (name) => page.evaluate((n) => { const t = [...document.querySelectorAll("[data-tq-line-tab]")].find((x) => x.innerText.replace("✓ ", "") === n); t?.click(); return !!t; }, name);
  await sleep(800);
  said.push(`press 1: ${await press(/^Post to /)}`); await sleep(3500); await page.screenshot({ path: path.join(OUT, "1-after-first.png") });
  said.push(`look at Reddit: ${await tab("Reddit")}`); await sleep(1200); await page.screenshot({ path: path.join(OUT, "2-reddit-picked.png") });
  said.push(`press on Reddit: ${await press(/^Post to /)}`); await sleep(3500); await page.screenshot({ path: path.join(OUT, "3-after-reddit.png") });
  said.push(`press 3: ${await press(/^Post to /)}`); await sleep(3500); await page.screenshot({ path: path.join(OUT, "4-all-posted.png") });
  await rec.stop({ sheet: 16 });
  const look = await page.evaluate(() => window.__look);
  const tops = [...new Set(look.map((x) => x[2]))], hs = look.map((x) => x[3]), jumps = hs.filter((x, i) => i && Math.abs(x - hs[i - 1]) > 40).length;
  said.push(`cards on the page ${[...new Set(look.map((x) => x[1]))].join("/")}, tops ${tops.join("/")}, shown ${[...new Set(look.map((x) => x[4]))].join(" -> ")}, ` +
    `counts ${[...new Set(look.map((x) => x[5]))].join(" -> ")}, height jumps >40px in one frame: ${jumps}`);
  await writeFile(path.join(OUT, "look.json"), JSON.stringify(look));
  said.push(`page errors: ${errors.length ? errors.join(" || ") : "none"}`);
} finally {
  await writeFile(path.join(OUT, "README.txt"), said.join("\n") + "\n").catch(() => {});
  console.log(said.join("\n"));
  await h.close();
}
