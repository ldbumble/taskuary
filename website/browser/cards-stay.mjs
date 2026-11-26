// THE OWNER'S THREE RULES, WATCHED ON THE REAL PAGE (not a test: nothing here runs in CI). node browser/cards-stay.mjs <out folder>
// 2026-11-26: "Things on chat don't go away." "No text after an approval card until the approval card is denied or approved, then agent moves
// on." "Cards never just disappear." Three posts in one card on a chat task in a disposable home, each network a stand-in: he steps with the
// arrows, dismisses one, the agent says something while two still wait, he refreshes, dismisses another, approves the last; then a routine
// change beside a post, the routine approved. Each step a frame, the whole thing recorded (recorder.mjs), and every painted frame sampled:
// the tab shown, the count, where the card stands, and how many of the chat's rows stand UNDER a card that still waits - which must be none.
import path from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import { startHarness } from "./harness.mjs";
import { record } from "./recorder.mjs";

const OUT = process.argv[2] || path.resolve("cards-stay-out");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const POSTS = [["x_post", "We shipped the ledger export - totals now round to cents."], ["reddit_post", "Ledger export update: totals round to cents now. Notes in the changelog."],
  ["linkedin_post", "The ledger export now rounds totals to cents. Thanks to everyone who reported it."]];
const row = ([type, text]) => ({ Kind: "action", Reason: "the post you asked for",
  DraftText: { action: "run_tool", type, text, why: "he asked", ...(type === "reddit_post" ? { title: "Ledger export: totals round to cents", subreddit: "accounting" } : {}) } });
const h = await startHarness({ fresh: true });
const api = (p, body) => fetch(`${h.fixtureApi}${p}`, { method: body ? "POST" : "GET", headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token },
  body: body && JSON.stringify(body) }).then((r) => r.json());
const said = [];
try {
  await api("/api/setup/first-run/ai", { name: "claude" }); await api("/api/setup/dismiss", { dismissed: true });
  await mkdir(OUT, { recursive: true });
  const page = await h.newPage(), errors = [];
  page.on("pageerror", (e) => errors.push(e.message)); page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 300)); });
  await page.setViewport({ width: 1440, height: 1000 });
  const open = async (taskId) => {
    await page.goto(`${h.ui}/#task=${taskId}`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("[data-tq-task-page] [data-tq-review-card]", { visible: true, timeout: 90000 }); await sleep(2500);
  };
  // ...every painted frame: [ms, tab shown, count, the card's top, rows of the chat under a card that still waits, cards drawn, chat rows drawn]
  const watch = () => page.evaluate(() => { window.__look = []; const t0 = performance.now(); const tick = () => {
    const l = document.querySelector("[data-tq-card-line]"), cs = [...document.querySelectorAll("[data-tq-task-page] [data-tq-review-card]")];
    const waits = [...document.querySelectorAll('[data-tq-task-page] [data-tq-act-state="waiting"]')].filter((c) => !c.closest("[inert]") && !c.closest("[data-tq-past-card]"));
    const foot = Math.max(-1, ...waits.map((c) => (c.closest("[data-tq-card-line]") || c).getBoundingClientRect().bottom));
    const items = [...document.querySelectorAll("[data-tq-task-page] [data-tq-item]")];
    const under = foot < 0 ? 0 : items.filter((x) => !x.hasAttribute("data-tq-chat-line") && x.getBoundingClientRect().top >= foot - 1 && x.innerText.trim()).length;
    window.__look.push([Math.round(performance.now() - t0), l?.getAttribute("data-tq-line-at") || "", document.querySelector("[data-tq-card-queue]")?.innerText || "",
      Math.round((l || cs[0])?.getBoundingClientRect().top || 0), under, cs.length, items.length]);
    if (window.__look.length < 6000) requestAnimationFrame(tick); }; requestAnimationFrame(tick); });
  const shot = async (name) => { await page.screenshot({ path: path.join(OUT, `${name}.png`) }); };
  const press = (re) => page.evaluate((src) => {
    const scope = document.querySelector("[data-tq-line-pane]:not([inert])") || [...document.querySelectorAll("[data-tq-task-page] [data-tq-review-card]")].pop();
    const b = [...(scope?.querySelectorAll("button") || [])].find((x) => new RegExp(src).test(x.innerText.trim()) && !x.disabled);
    if (!b) return `no button (${[...(scope?.querySelectorAll("button") || [])].map((x) => x.innerText.trim()).join(" | ")})`; b.click(); return b.innerText.trim(); }, re.source);
  const step = (d) => page.evaluate((n) => { const b = document.querySelector(`[data-tq-line-step="${n}"]`); b?.click(); return !!b; }, d);
  const at = () => page.evaluate(() => `${document.querySelector('[data-tq-line-tab][aria-selected="true"]')?.innerText || "-"} (${document.querySelector("[data-tq-card-queue]")?.innerText || "-"})`);
  const sum = async (what) => {
    const look = await page.evaluate(() => window.__look || []);
    const under = look.filter((x) => x[4] > 0).length, tops = [...new Set(look.map((x) => x[3]))], cards = [...new Set(look.map((x) => x[5]))], rows = look.map((x) => x[6]);
    said.push(`${what}: ${look.length} frames; frames with a chat row under a waiting card: ${under}; cards drawn ${cards.join("/")}; chat rows ${Math.min(...rows)}..${Math.max(...rows)}` +
      `${rows.some((x, i) => i && x < rows[i - 1]) ? " - A ROW WENT AWAY" : ""}; card tops ${tops.join("/")}; shown ${[...new Set(look.map((x) => `${x[1]}:${x[2]}`))].join(" -> ")}`);
    await writeFile(path.join(OUT, `${what.replace(/\W+/g, "-")}.json`), JSON.stringify(look));
  };

  // ── A. three posts in one card ──
  const { taskId, reviewIds } = await api("/api/fixture/review-rows", { title: "Announce the export fix", connect: ["x", "reddit", "linkedin"], ask: "Post the export fix on X, Reddit and LinkedIn.",
    answer: "Three posts are set up below, one for each network.", rows: POSTS.map(row) });
  await api(`/api/tasks/${taskId}/trust`, {});
  await open(taskId);
  await shot("a0-three-posts-arrows");
  const rec = await record(page, path.join(OUT, "video-a"), { secs: 90, mb: 80 });
  await watch(); await sleep(600);
  said.push(`A opens on: ${await at()}`);
  said.push(`next arrow: ${await step(1)}`); await sleep(900); said.push(`  now on: ${await at()}`); await shot("a1-next-arrow");
  said.push(`previous arrow: ${await step(-1)}`); await sleep(900); said.push(`  now on: ${await at()}`);
  said.push(`dismiss X: ${await press(/^Dismiss/)}`); await sleep(3000); said.push(`  still on: ${await at()}`); await shot("a2-x-dismissed-stays");
  await api("/api/fixture/agent-says", { taskId, text: "Noted on X. Reddit and LinkedIn are still there for you." }); await sleep(3000); await shot("a3-agent-words-above-waiting-card");
  said.push(`next arrow: ${await step(1)}`); await sleep(900);
  said.push(`dismiss Reddit: ${await press(/^Dismiss/)}`); await sleep(3000); said.push(`  still on: ${await at()}`); await shot("a4-two-dismissed");
  await sum("A before the refresh");
  await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForSelector("[data-tq-task-page] [data-tq-review-card]", { visible: true, timeout: 90000 }); await sleep(2500);
  said.push(`after a refresh, on: ${await at()}`); await shot("a5-after-refresh");
  await watch();
  said.push(`to LinkedIn: ${await page.evaluate(() => { const t = [...document.querySelectorAll("[data-tq-line-tab]")].find((x) => /LinkedIn/.test(x.innerText)); t?.click(); return !!t; })}`); await sleep(900);
  said.push(`approve LinkedIn: ${await press(/^Post to /)}`); await sleep(3500); said.push(`  still on: ${await at()}`); await shot("a6-linkedin-posted-stays");
  await api("/api/fixture/agent-says", { taskId, text: "LinkedIn is posted." }); await sleep(3000); await shot("a7-words-after-settled-card");
  await sum("A after the refresh"); await rec.stop({ sheet: 16 });
  said.push(`A reviews: ${JSON.stringify(reviewIds)}`);

  // ── B. a routine change beside a post ──
  const b = await api("/api/fixture/change-card", { was: "Draft a LinkedIn post about the week's numbers. Three paragraphs.", now: "Draft a LinkedIn post about the week's numbers. Two sentences, no hashtags." });
  await api("/api/fixture/agent-says", { taskId: b.taskId, rows: [row(POSTS[2])] });
  await open(b.taskId);
  await shot("b0-routine-change-and-post");
  const rec2 = await record(page, path.join(OUT, "video-b"), { secs: 60, mb: 80 });
  await watch(); await sleep(600);
  said.push(`B opens on: ${await at()}`);
  said.push(`approve the routine change: ${await press(/^(Approve|Change|Save)/)}`); await sleep(3500); said.push(`  still on: ${await at()}`); await shot("b1-routine-approved-stays");
  said.push(`next arrow: ${await step(1)}`); await sleep(900); said.push(`  now on: ${await at()}`); await shot("b2-post-tab");
  said.push(`previous arrow: ${await step(-1)}`); await sleep(900); said.push(`  back on: ${await at()}`); await shot("b3-back-on-approved");
  await sum("B routine and post"); await rec2.stop({ sheet: 12 });
  // ...and the three posts again at a phone's width: the arrows and the count on one line with the tab names
  await page.setViewport({ width: 390, height: 800 }); await open(taskId); await shot("c0-phone-width");
  said.push(`page errors: ${errors.length ? errors.join(" || ") : "none"}`);
} catch (e) { said.push(`STOPPED: ${e.message}`); } finally {
  await writeFile(path.join(OUT, "README.txt"), said.join("\n") + "\n").catch(() => {});
  console.log(said.join("\n"));
  await h.close();
}
