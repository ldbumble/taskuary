// THE OWNER'S THREE RULES, WATCHED ON THE REAL PAGE (not a test: nothing here runs in CI). node browser/cards-stay.mjs <out folder>
// 2026-11-26: "Things on chat don't go away." "No text after an approval card until the approval card is denied or approved, then agent moves
// on." "Cards never just disappear." A: the same post for three networks, raised in one call - ONE card with a tab each, on a chat task in a
// disposable home, each network a stand-in: he steps with the arrows, dismisses one, the agent says something while two still wait, he
// refreshes, dismisses another, approves the last. B: a routine change and a post, a call each - two cards, one after another, never tabs.
// C: one act to many - the list card, before and after its one press. Each step a frame, the whole recorded (recorder.mjs), every frame sampled:
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
      // ...where the card stands IN THE CHAT (from the chat's first row, so the chat scrolling to its foot is no move), and what is above it
      Math.round(((l || cs[0])?.getBoundingClientRect().top || 0) - (items[0]?.getBoundingClientRect().top || 0)), under, cs.length, items.length,
      document.querySelectorAll("[data-tq-task-page] [data-tq-turn-retry]").length]);
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
    const moved = look.filter((x, i) => i && x[3] && look[i - 1][3] && x[3] !== look[i - 1][3]).length;
    const retry = [...new Set(look.map((x) => x[7]))].join("/");
    said.push(`${what}: ${look.length} frames; frames with a chat row under a waiting card: ${under}; frames where the card moved: ${moved}; cards drawn ${cards.join("/")}; chat rows ${Math.min(...rows)}..${Math.max(...rows)}` +
      `${rows.some((x, i) => i && x < rows[i - 1]) ? " - A ROW WENT AWAY" : ""}; card at ${tops.join("/")} px down the chat; Try again buttons above ${retry}; shown ${[...new Set(look.map((x) => `${x[1]}:${x[2]}`))].join(" -> ")}`);
    await writeFile(path.join(OUT, `${what.replace(/\W+/g, "-")}.json`), JSON.stringify(look));
  };

  // ── A. three posts in one card ──
  const { taskId, reviewIds } = await api("/api/fixture/review-rows", { title: "Announce the export fix", connect: ["x", "reddit", "linkedin"], ask: "Post the export fix on X, Reddit and LinkedIn.",
    answer: "Three posts are set up below, one for each network.", rows: POSTS.map((x) => ({ ...row(x), Batch: "set1" })) });
  await api(`/api/tasks/${taskId}/trust`, {});
  await open(taskId);
  await shot("a0-three-posts-arrows");
  const rec = await record(page, path.join(OUT, "video-a"), { secs: 90, mb: 80 });
  await watch(); await sleep(600);
  said.push(`A opens on: ${await at()}`);
  said.push(`next arrow: ${await step(1)}`); await sleep(900); said.push(`  now on: ${await at()}`); await shot("a1-next-arrow");
  said.push(`previous arrow: ${await step(-1)}`); await sleep(900); said.push(`  now on: ${await at()}`);
  said.push(`dismiss X: ${await press(/^Dismiss/)}`); await sleep(3000); said.push(`  still on: ${await at()}`); await shot("a2-x-dismissed-stays");
  said.push(`next arrow: ${await step(1)}`); await sleep(900);
  said.push(`dismiss Reddit: ${await press(/^Dismiss/)}`); await sleep(3000); said.push(`  still on: ${await at()}`); await shot("a4-two-dismissed");
  await sum("A before the refresh");
  await page.reload({ waitUntil: "domcontentloaded" }); await page.waitForSelector("[data-tq-task-page] [data-tq-review-card]", { visible: true, timeout: 90000 }); await sleep(2500);
  said.push(`after a refresh, on: ${await at()}`); await shot("a5-after-refresh");
  await watch();
  said.push(`to LinkedIn: ${await page.evaluate(() => { const t = [...document.querySelectorAll("[data-tq-line-tab]")].find((x) => /LinkedIn/.test(x.innerText)); t?.click(); return !!t; })}`); await sleep(900);
  said.push(`approve LinkedIn: ${await press(/^Post to /)}`); await sleep(3500); said.push(`  still on: ${await at()}`); await shot("a6-linkedin-posted-stays");
  await api("/api/fixture/agent-says", { taskId, text: "LinkedIn is posted." }); await sleep(3000); await shot("a7-words-after-settled-card");
  await sum("A after the refresh");
  // ...THE NET, on its own beat: something that still arrives while a card waits (a failed press's turn, a message's) is never under the card
  const net = await api("/api/fixture/review-rows", { title: "One post", connect: ["linkedin"], ask: "Post the fix on LinkedIn.", answer: "The post is set up.", rows: [row(POSTS[2])] });
  await api(`/api/tasks/${net.taskId}/trust`, {}); await open(net.taskId); await watch();
  await api("/api/fixture/agent-says", { taskId: net.taskId, text: "A message came in on this while the post waits." }); await sleep(3000); await shot("a8-the-net-what-arrives-is-never-under-a-waiting-card");
  await sum("A8 the net (the card is set down under what arrived: it moves here, by design)"); await rec.stop({ sheet: 16 });
  said.push(`A reviews: ${JSON.stringify(reviewIds)}`);

  // ── B. a routine change and a post: a call each, so a card each - one after another ──
  const b = await api("/api/fixture/change-card", { was: "Draft a LinkedIn post about the week's numbers. Three paragraphs.", now: "Draft a LinkedIn post about the week's numbers. Two sentences, no hashtags." });
  await api("/api/fixture/agent-says", { taskId: b.taskId, rows: [row(POSTS[2])] });
  await open(b.taskId);
  await shot("b0-two-unrelated-cards-the-first");
  const rec2 = await record(page, path.join(OUT, "video-b"), { secs: 60, mb: 80 });
  await watch(); await sleep(600);
  said.push(`B: tabs on the page: ${await page.evaluate(() => document.querySelectorAll("[data-tq-line-tab]").length)}; cards drawn: ${await page.evaluate(() => document.querySelectorAll("[data-tq-task-page] [data-tq-review-card]").length)}`);
  said.push(`approve the routine change: ${await press(/^(Approve|Change|Save)/)}`); await sleep(4000); await shot("b1-first-approved-second-stands-after-it");
  said.push(`B after the press: tabs ${await page.evaluate(() => document.querySelectorAll("[data-tq-line-tab]").length)}; cards waiting ${await page.evaluate(() => document.querySelectorAll('[data-tq-task-page] [data-tq-act-state="waiting"]').length)}`);
  await sum("B two unrelated cards"); await rec2.stop({ sheet: 12 });

  // ── C. one act to many: the list card, and its one press ──
  const TIPS = [1, 2, 3, 4].map((i) => ({ ...row(["linkedin_post", `Ledger portal tip ${i}: invoices in one place.`]), Batch: "bulk1" }));
  const cTask = await api("/api/fixture/review-rows", { title: "Four portal tips", connect: ["linkedin"], ask: "Post the four portal tips on LinkedIn.", answer: "The four tips are on one card.", rows: TIPS });
  await api(`/api/tasks/${cTask.taskId}/trust`, {});
  await open(cTask.taskId);
  await shot("c0-bulk-card-before");
  const rec3 = await record(page, path.join(OUT, "video-c"), { secs: 60, mb: 80 });
  await watch(); await sleep(600);
  said.push(`C: tabs on the page: ${await page.evaluate(() => document.querySelectorAll("[data-tq-line-tab]").length)}; rows on the card: ${await page.evaluate(() => document.querySelectorAll("[data-tq-bulk-row]").length)}`);
  said.push(`C press: ${await page.evaluate(() => { const x = document.querySelector("[data-tq-bulk-press]"); x?.click(); return x?.innerText || "no press"; })}`);
  await sleep(700); await shot("c1-bulk-card-going"); await sleep(5000); await shot("c2-bulk-card-after-with-progress");
  said.push(`C after: ${await page.evaluate(() => document.querySelector("[data-tq-bulk-progress]")?.innerText || "no progress line")}`);
  await sum("C the list card"); await rec3.stop({ sheet: 12 });
  // ...and the three posts again at a phone's width: the arrows and the count on one line with the tab names
  await page.setViewport({ width: 390, height: 800 }); await open(taskId); await shot("d0-phone-width");
  said.push(`page errors: ${errors.length ? errors.join(" || ") : "none"}`);
} catch (e) { said.push(`STOPPED: ${e.message}`); } finally {
  await writeFile(path.join(OUT, "README.txt"), said.join("\n") + "\n").catch(() => {});
  console.log(said.join("\n"));
  await h.close();
}
