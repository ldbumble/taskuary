// THE ONE REVIEW CARD, DRAWN AND PRESSED (not a test: nothing here runs in CI). node browser/one-card.mjs <out folder>
// The owner, 2026-11-24: "merge the cards into one too". Each kind - an email, a chat reply, a LinkedIn post (connected, and not), a GitHub
// comment, a Jira comment, a bulk job, one that went, one whose press failed - seeded on a task of its own in a disposable home, shot at 1440
// light and dark, and one press per kind recorded (recorder.mjs, capped) to be watched for a flicker or a jump.
import path from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import { startHarness } from "./harness.mjs";
import { record } from "./recorder.mjs";

const OUT = process.argv[2] || path.resolve("one-card-out");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const email = (to, subject) => ({ channel: "email", to: [to], subject });
const KINDS = {
  email: { rows: [{ Kind: "slot", Channel: "email", DraftText: "Hi Ray,\n\nCould you quote a bus for 40 people on March 12?\n\nThanks,\nAlex", Deliver: email("ray.colton@northwind.example", "Bus for the March offsite") }], press: /^Send/ },
  reply: { channel: "whatsapp", rows: [{ Kind: "draft", Channel: "whatsapp", answers: true, DraftText: "Yes - the plans are on their way, Erin." }], press: /^Send/ },
  post: { rows: [{ Kind: "action", Reason: "the post you asked for", DraftText: { action: "run_tool", type: "linkedin_post", network: "LinkedIn", text: "We compared three expense tools for a 40-person team. What mattered most was the approval flow, not the price.", why: "he asked" } }], press: /^Post via the browser/ },
  // ...its Connect pressed on a network never set up: that connection's own setup comes up under the card (ConnectSetup, 2026-11-25)
  connect: { rows: [{ Kind: "action", Reason: "the post you asked for", DraftText: { action: "run_tool", type: "linkedin_post", network: "LinkedIn", text: "Three expense tools, compared for a 40-person team.", why: "he asked" } }], press: /^Connect LinkedIn$/ },
  postlive: { connect: "linkedin", rows: [{ Kind: "action", Reason: "the post you asked for", DraftText: { action: "run_tool", type: "linkedin_post", network: "LinkedIn", text: "Three expense tools, compared for a 40-person team.", why: "he asked" } }], press: /^Post to LinkedIn$/ },
  github: { source: "https://github.com/northwind/ledger/issues/12", github: true, rows: [{ Kind: "action", Reason: "the agent proposes to post a PUBLIC comment on the linked issue/PR",
    DraftText: { action: "comment_issue", repo: "northwind/ledger", number: 12, body: "Fixed in the totals branch - the export rounds to cents now. Thanks for the report.", why: "close the loop" } }], press: /^Comment$/ },
  jira: { rows: [{ Kind: "action", Reason: "the comment Erin asked for", DraftText: { action: "run_tool", type: "jira_comment", item: "NW-12", body: "Deployed this morning - the totals are right again.", why: "she asked" } }], press: /^Dismiss$/ },
  bulk: { rows: [1, 2, 3].map((i) => ({ Kind: "slot", Channel: "email", Batch: "renewals", DraftText: `Hello - your renewal ${i} is due on Friday.`, Deliver: email(`owner${i}@vendor.example`, `Renewal ${i} is due Friday`) })), press: /^Send 3 emails/ },
  sent: { rows: [{ Kind: "draft_reply", Channel: "email", answers: true, Status: "approved", DecidedAt: "2026-11-24 09:05:00", DraftText: "Hi Erin, the plans are attached. Alex",
    FinalText: "Hi Erin, the plans are attached. Alex", Deliver: email("erin@northwind.example", "Re: Vendor plans") }] },
  failed: { rows: [{ Kind: "action", Status: "superseded", ActError: "LinkedIn refused the post: the token has expired - sign in again on its card.", Reason: "the post",
    DraftText: { action: "run_tool", type: "linkedin_post", network: "LinkedIn", text: "Three tools, compared.", why: "he asked" } }] },
};

const h = await startHarness({ fresh: true });
const api = (p, body, method = body ? "POST" : "GET") => fetch(`${h.fixtureApi}${p}`, { method, headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token },
  body: body && JSON.stringify(body) }).then((r) => r.json());
const said = [];
try {
  await api("/api/setup/first-run/ai", { name: "claude" }); await api("/api/setup/dismiss", { dismissed: true });
  await api("/api/fixture/outbox", {});
  const tasks = {};
  for (const [k, v] of Object.entries(KINDS).filter(([k]) => !process.env.ONLY || process.env.ONLY.split(",").includes(k))) tasks[k] = (await api("/api/fixture/review-rows", { title: `One card: ${k}`, ...v, press: undefined })).taskId;
  await mkdir(OUT, { recursive: true });
  const page = await h.newPage();
  const errors = []; page.on("pageerror", (e) => errors.push(e.message)); page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 300)); });
  page.on("requestfailed", (r) => { if (/\/api\/reviews/.test(r.url())) said.push(`  FAILED ${r.method()} ${new URL(r.url()).pathname}: ${r.failure()?.errorText}`); });
  page.on("request", (r) => { if (/\/api\/reviews/.test(r.url()) && r.method() !== "GET") said.push(`  -> ${r.method()} ${new URL(r.url()).pathname} ${(r.postData() || "").slice(0, 200)}`); });
  page.on("response", async (r) => { if (/\/decide$|\/via-browser$|\/batch\/.*\/run$/.test(r.url())) said.push(`  ${r.request().method()} ${new URL(r.url()).pathname} -> ${r.status()} ${(await r.text().catch(() => "")).slice(0, 220)}`); });
  await page.setViewport({ width: 1440, height: 1000 });
  // ...each card on the stage (browser/onecard-preview.html): the real component, in the chat's column and theme, presses to this server
  const stage = (q) => page.goto(`${h.ui}/browser/onecard-preview.html?${q}`, { waitUntil: "domcontentloaded" });
  const card = () => page.waitForSelector("[data-tq-task-page] [data-tq-review-card]", { visible: true, timeout: 60000 }).then(() => sleep(1200));
  for (const theme of ["light", "dark"]) {
    await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: theme }]);
    for (const [k, tid] of Object.entries(tasks)) {
      await stage(`task=${tid}`);
      try { await card(); } catch { said.push(`${k} ${theme}: no card drawn`); }
      const el = await page.$("[data-tq-task-page] [data-tq-review-card]");
      await page.screenshot({ path: path.join(OUT, `${k}-${theme}-page.png`) });
      if (el) await el.screenshot({ path: path.join(OUT, `${k}-${theme}.png`) });
      said.push(`${k} ${theme}: ${await page.evaluate(() => [...document.querySelectorAll("[data-tq-task-page] [data-tq-review-card] button")].map((b) => b.innerText.trim()).filter(Boolean).join(" | "))}`);
    }
  }
  // ...AND A REPORT'S TABLE BY THE ONE FIT (tableFit.js): a 15-row, 6-column trending-repositories table in its frame, as it stood and as it fits
  for (const [fit, theme] of [["0", "light"], ["1", "light"], ["1", "dark"]]) {
    await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: theme }]);
    await stage(`table=1&fit=${fit}`); await page.waitForSelector("[data-tq-table-stage] table", { timeout: 60000 }); await sleep(1200);
    const el = await page.$("[data-tq-table-stage] .tq-turn-frame");
    await el.screenshot({ path: path.join(OUT, `table-${fit === "1" ? "after" : "before"}-${theme}.png`) });
    said.push(`table ${fit === "1" ? "after" : "before"} ${theme}: ${await page.evaluate(() => { const f = document.querySelector("[data-tq-table-stage] .tq-turn-frame"), t = f.querySelector("table");
      const rows = [...t.rows].slice(1), tall = rows.filter((r) => r.offsetHeight > 30).length;
      return `frame ${f.offsetWidth}px, table ${t.offsetWidth}px, font ${getComputedStyle(t).fontSize}, rows over one line ${tall}/${rows.length}, fit ${f.querySelector("[data-tq-fit]")?.dataset.tqFit || "none"}`; })}`);
  }
  await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "light" }]);
  // ...ONE PRESS PER KIND, recorded: the card's top and height sampled every frame - a jump or a second card is a finding
  await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: "light" }]);
  for (const [k, v] of Object.entries(KINDS)) {
    if (!v.press || !tasks[k]) continue;
    await stage(`task=${tasks[k]}`);
    try { await card(); } catch { said.push(`PRESS ${k}: no card to press`); continue; }
    const rec = await record(page, path.join(OUT, "video", k), { secs: 20, mb: 40 });
    await page.evaluate(() => { window.__look = []; const t0 = performance.now(); const tick = () => { const cs = [...document.querySelectorAll("[data-tq-task-page] [data-tq-review-card]")];
      const b = cs[0]?.getBoundingClientRect(); window.__look.push([Math.round(performance.now() - t0), cs.length, Math.round(b?.top || 0), Math.round(b?.height || 0), cs[0]?.getAttribute("data-tq-act-state") || ""]);
      if (window.__look.length < 600) requestAnimationFrame(tick); }; requestAnimationFrame(tick); });
    await sleep(600);
    const pressed = await page.evaluate((src) => { const b = [...document.querySelectorAll("[data-tq-task-page] [data-tq-review-card] button")].find((x) => new RegExp(src).test(x.innerText.trim()) && !x.disabled);
      if (!b) return "no button"; b.click(); return b.innerText.trim(); }, v.press.source);
    await sleep(6000);
    await page.screenshot({ path: path.join(OUT, `${k}-pressed.png`) });
    await rec.stop({ sheet: 8 });
    const look = await page.evaluate(() => window.__look), cards = new Set(look.map((x) => x[1])), tops = new Set(look.map((x) => x[2])), states = [...new Set(look.map((x) => x[4]))];
    const heights = look.map((x) => x[3]), jumps = heights.filter((x, i) => i && Math.abs(x - heights[i - 1]) > 40).length;
    said.push(`PRESS ${k}: pressed "${pressed}" - cards on the page ${[...cards].join("/")}, tops ${[...tops].join("/")}, states ${states.join(" -> ")}, height jumps >40px: ${jumps}`);
  }
  said.push(`page errors: ${errors.length ? errors.join(" || ") : "none"}`);
} finally {
  await writeFile(path.join(OUT, "README.txt"), said.join("\n") + "\n");
  console.log(said.join("\n"));
  await h.close();
}
