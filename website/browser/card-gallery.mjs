// THE CARD GALLERY (not a test: nothing here runs in CI). node browser/card-gallery.mjs <out folder>      ONLY=pdf,bulk narrows it
// The owner, 2026-11-25: "make sure cards are showing up correct - from json-render charts, to pdf / markdown / PowerPoint / Excel / images /
// videos (or multiples of these), and then email sending / GitHub PRs / any card that has an action on it ... bulk ones, steps through multiple
// requests, brings up browsers when needed, cards for approval". One task per shape in a disposable home, each raised the way an agent raises
// it - Taskuary's own tools over /api/mcp, files made in its folder (fixture_gallery.py) - then opened on the real task page in Chrome and shot
// wide, narrow and dark, and the presses a card has pressed (a tick, Open, Send, a press that fails, Connect, Download all). The shots are for
// looking at: README.txt beside them says what each shape was answered, which buttons stood, and what the page said that it should not.
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
process.env.TASKUARY_FIXTURE_GALLERY = "1";
if (process.platform === "win32") { process.env.TASKUARY_BROWSER_PLAIN_ENV ||= "1"; if (existsSync(CHROME)) process.env.TASKUARY_BROWSER_EXECUTABLE ||= CHROME; }
const { startHarness } = await import("./harness.mjs");

const OUT = path.resolve(process.argv[2] || "card-gallery-out"), ONLY = (process.env.ONLY || "").split(",").filter(Boolean);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
// ...git's own launcher where there is one (Git for Windows' cmd\git.exe): the bare program beside it cannot push without the rest of its PATH
const GITS = execFileSync(process.platform === "win32" ? "where" : "which", process.platform === "win32" ? ["git"] : ["-a", "git"], { encoding: "utf8" }).trim().split(/\r?\n/);
const GIT = GITS.find((g) => /[\\/]cmd[\\/]git\.exe$/i.test(g)) || GITS[0];
const h = await startHarness({ fresh: true, bin: path.dirname(GIT) }), said = [];
const api = (p, body, method = body ? "POST" : "GET") => fetch(`${h.fixtureApi}${p}`, { method, headers: { "Content-Type": "application/json", "X-Taskuary-Token": h.token },
  body: body && JSON.stringify(body) }).then(async (r) => { const t = await r.text(); try { return JSON.parse(t); } catch { return t; } });
// ...a stand-in that could not be made is said (NOT SEEDED), never worked on as if it were there
const fx = async (p, body) => { const r = await api(`/api/fixture/gallery/${p}`, body); if (typeof r === "string" || r?.detail) throw new Error(`fixture ${p}: ${JSON.stringify(r).slice(0, 200)}`); return r; };
// one tool call of the task's agent, over the route its CLI's MCP client posts to: what it was answered
const agent = async (t, name, args = {}) => {
  const r = await fetch(`${h.fixtureApi}/api/mcp?task=${t.taskId}`, { method: "POST", headers: { "Content-Type": "application/json", ...t.headers },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "tools/call", params: { name, arguments: args } }) }).then((x) => x.json());
  const res = r.result || {}, text = res.content?.[0]?.text || JSON.stringify(r.error || r);
  t.said.push(`    ${name}${res.isError ? " REFUSED" : ""}: ${text.replace(/\s+/g, " ").slice(0, 260)}`);
  t.trace.push({ name, args, result: text, err: !!res.isError });
  let json = null; try { json = JSON.parse(text); } catch { /* words */ }
  return { text, err: !!res.isError, json };
};
// ...and its agent takes a moment over his line before it raises anything, as any agent does: the chat orders a card and a line by the second
const task = async (title, ask, more = {}) => { const t = { ...(await fx("task", { title, ask, ...more })), said: [], trace: [] }; await sleep(1100); return t; };
const files = async (t, ...names) => (await fx("files", { taskId: t.taskId, names })).paths;
const end = (t, text) => fx("end", { taskId: t.taskId, text, trace: t.trace });
const LETTERS = ["erin", "gail", "paula"].map((who) => ({ to: `${who}@northwind.example`, subject: "The ledger portal is live Monday",
  text: `Hello ${who[0].toUpperCase()}${who.slice(1)},\n\nYour invoices move to the ledger portal on Monday - nothing to do on your side.\n\nAlex` }));
const POST = "We compared three expense tools for a 40-person team. What mattered most was the approval flow, not the price.";
const VIEW = { title: "Payworth seats", state: { seats: 40 }, root: "g", elements: {
  g: { type: "grid", props: { cols: 1 }, children: ["k", "s", "row"] },
  k: { type: "stats", props: { items: [{ label: "Per month", format: "currency", value: { $expr: "seats * 12" } }, { label: "Per year", format: "currency", value: { $expr: "seats * 12 * 12" } },
    { label: "Cheapest paid", value: 200, format: "currency", note: "Payworth Basic", trend: { dir: "up", text: "+$340 to Pro" } }] } },
  s: { type: "slider", props: { label: "Seats", value: { $bindState: "/seats" }, min: 5, max: 200, step: 5 } },
  row: { type: "grid", props: { cols: 2 }, children: ["c", "t"] },
  c: { type: "chart", props: { kind: "bar", title: "Per month", format: "currency", points: [{ label: "Spendly Free", value: 0 }, { label: "Payworth Basic", value: 200, highlight: true }, { label: "Payworth Pro", value: 540 }] } },
  t: { type: "table", props: { title: "What each plan costs", columns: ["Plan", { label: "Per month", format: "currency" }, { label: "Per person", format: "currency" }],
    rows: [["Spendly Free", 0, 0], ["Payworth Basic", 200, 5], ["Payworth Pro", 540, 13.5]] } } } };
const CHARTS = { title: "Invoices this quarter", root: "g", elements: { g: { type: "grid", props: { cols: 2 }, children: ["l", "p"] },
  l: { type: "chart", props: { kind: "line", title: "Open invoices by week", points: [12, 15, 9, 14, 7, 5].map((v, i) => ({ label: `W${i + 1}`, value: v })) } },
  p: { type: "chart", props: { kind: "pie", title: "By vendor", points: [{ label: "Payworth", value: 6 }, { label: "Trainly", value: 3 }, { label: "Spendly", value: 2 }] } } } };

// EACH SHAPE: a task, what its agent calls, and its turn's end. `press`: what is pressed on it after it is shot - a step each, shot again
const one = (title, ask, names, text, press) => async () => { const t = await task(title, ask); await agent(t, "show", { files: await files(t, ...names) }); await end(t, text); return { ...t, press }; };
const SHAPES = {
  view: async () => { const t = await task("Payworth seats, worked out", "What would Payworth cost us by seats?"); await agent(t, "show", VIEW); await end(t, "Move the slider - the cost follows it."); return t; },
  charts: async () => { const t = await task("Invoices this quarter", "Chart the open invoices."); await agent(t, "show", CHARTS); await end(t, "Open invoices are down to 5, most of them Payworth's."); return t; },
  pdf: one("Offsite budget as a PDF", "Make the offsite budget a PDF.", ["offsite-budget.pdf"], "The budget is a two-page PDF."),
  markdown: one("Expense tools write-up", "Write up the three expense tools.", ["expense-tools.md"], "The write-up is ready."),
  pptx: one("Launch deck", "Make a three-slide deck for the launch.", ["ledger-launch.pptx"], "The deck has three slides."),
  xlsx: one("Open invoices workbook", "Put the open invoices in a workbook.", ["open-invoices.xlsx"], "The workbook has two sheets."),
  csv: one("Open invoices as CSV", "Export the open invoices as CSV.", ["open-invoices.csv"], "Four rows exported."),
  image: one("Chart of open invoices", "Draw the open invoices as a picture.", ["open-invoices.png"], "Here is the chart."),
  images: one("Three versions of the banner", "Make three versions of the banner.", ["banner-one.png", "banner-two.png", "banner-tall.png"], "Three versions - pick one."),
  video: one("Walkthrough clip", "Record a short walkthrough.", ["portal-walkthrough.mp4"], "The clip is four seconds."),
  mix: one("Everything for the board", "Put together the board pack.", ["board-pack.pdf", "board-notes.md", "board-deck.pptx", "board-numbers.xlsx", "board-export.csv", "board-chart.png", "board-clip.mp4"],
    "The board pack: seven files.", [["pick:board-deck.pptx", "deck"], ["pick:board-numbers.xlsx", "sheet"], ["pick:board-clip.mp4", "clip"], ["pick:board-notes.md", "notes"], [/^Download all$/, "downloaded", 2500]]),
  // ...separate calls are separate artifacts: a picture and a sheet, each shown by its own call in one turn
  separate: async () => { const t = await task("A chart and its numbers", "Chart the invoices and give me the numbers."); const [a, b] = await files(t, "invoices-chart.png", "invoices.xlsx");
    await agent(t, "show", { files: [a] }); await agent(t, "show", { files: [b] }); await end(t, "The chart, and the workbook behind it."); return t; },
  email: async () => { const t = await task("Bus quote for the offsite", "Ask Ray for a bus quote and attach the budget.");
    await files(t, "offsite-budget.pdf", "open-invoices.xlsx");
    await agent(t, "propose", { kind: "email", to: "ray.colton@northwind.example", cc: ["gail.moreno@northwind.example"], subject: "Bus for the March offsite",
      text: "Hi Ray,\n\nCould you quote a bus for 40 people on March 12? The budget is attached.\n\nThanks,\nAlex", attach: ["offsite-budget.pdf", "open-invoices.xlsx"], why: "he asked for the quote" });
    await end(t, "The email to Ray is set up with the budget attached."); return { ...t, press: [[/^Send/, "sent"]] }; },
  reply: async () => { const t = await task("Erin asks for the plans", "Answer Erin.", { mail: "Hi Alex, could you send me the vendor plans before Friday? Thanks, Erin" });
    await agent(t, "propose", { kind: "reply", text: "Hi Erin,\n\nYes - the three plans are below, and I would go with Payworth Basic.\n\nAlex" });
    await end(t, "The reply to Erin is set up."); return t; },
  // ...one letter written two ways is ONE card with a Version pick (agenttools._many, review.Versions): the second picked, the box follows
  replyversions: async () => { const t = await task("Erin asks to move the review", "Answer Erin.", { mail: "Hi Alex, could we move the vendor review to Thursday 2pm? Erin" });
    await agent(t, "propose", { kind: "reply", items: [{ text: "Hi Erin,\n\nYes - Thursday 2pm works. I will move the invite.\n\nAlex" },
      { text: "Hi Erin,\n\nThursday is full for me - can we keep Friday at 10?\n\nAlex" }] });
    await end(t, "Two versions of the reply to Erin - a yes and a no; pick one."); return { ...t, press: [[(page) => page.select("[data-tq-act-choice=version]", "1").then((v) => `picked version ${v}`), "picked", 1500]] }; },
  chatreply: async () => { const t = await task("Erin asks on WhatsApp", "Answer Erin.", { mail: "Are the plans ready?", channel: "whatsapp" });
    await agent(t, "propose", { kind: "reply", text: "Yes - the plans are on their way, Erin." }); await end(t, "The reply is set up."); return t; },
  post: async () => { const t = await task("LinkedIn post, connected", "Post about the expense tools on LinkedIn."); await files(t, "expense-tools.png");
    await agent(t, "propose", { kind: "post", network: "linkedin", text: POST, picture: "expense-tools.png", then: "tell Gail it is up" });
    await end(t, "The LinkedIn post is set up with its picture."); return { ...t, press: [[/^Post to LinkedIn$/, "posted"]] }; },
  postbrowser: async () => { const t = await task("X post, not connected", "Post about the expense tools on X."); await files(t, "expense-tools.png");
    await agent(t, "propose", { kind: "post", network: "x", text: "Three expense tools, compared for a 40-person team.", picture: "expense-tools.png" });
    await end(t, "The X post is set up."); return { ...t, press: [[/^Connect X/, "connect"]] }; },
  // ...and put up through the browser: his press hands it to the agent's browser (proposals.via_browser), and each step of HIS on the way - the
  // page handed to him (hand_over), then the site's own Post held for his Approve (browsergate) - is drawn on that same card as its next press
  postvia: async () => { const t = await task("X post through the browser", "Post about the expense tools on X.");
    await agent(t, "propose", { kind: "post", network: "x", text: "Three expense tools, compared for a 40-person team." });
    await end(t, "The X post is set up."); await fx("session", { taskId: t.taskId, url: "https://x.example/compose" });
    const step = (what, f) => [async () => { await f(); return what; }, what.split(" ")[0], 3500];
    return { ...t, press: [[/^Post via the browser$/, "handed", 3000],
      step("handover the sign-in", () => agent(t, "hand_over", { what: "sign in to X", site: "x.example" })), [/^I.m done$/, "done", 3500],
      step("held the site's Post", () => fx("browserhold", { taskId: t.taskId, what: "Press Post on x.example", site: "x.example" })), [/^Approve$/, "approved", 4000]] }; },
  reddit: async () => { const t = await task("Reddit post", "Ask r/smallbusiness which expense tool they use.");
    await agent(t, "propose", { kind: "post", network: "reddit", subreddit: "smallbusiness", title: "Which expense tool for a 40-person team?", text: "We are choosing between three. What mattered most to you?" });
    await end(t, "The Reddit post is set up."); return t; },
  push: async () => { const { repo } = await fx("checkout", { git: GIT }); const t = await task("Fix the ledger rounding", `Fix the rounding bug in the ledger totals and push it on my press. My checkout is at ${repo}`);
    await fx("checkout", { git: GIT, repo });
    await agent(t, "propose", { kind: "act", action: "push", cwd: repo, why: "the rounding fix", then: "reply to Gail that it is live" });
    await end(t, "Fixed the rounding to cents and committed it in your checkout."); return { ...t, press: [[/^Push$/, "pushed", 5000]] }; },
  pushdeploy: async () => { const { repo } = await fx("checkout", { git: GIT }); const t = await task("Fix and deploy the ledger", `Fix the rounding in the ledger and put it live. My checkout is at ${repo}`);
    await fx("checkout", { git: GIT, repo });
    await agent(t, "propose", { kind: "act", action: "push", cwd: repo, deploy: "production", why: "the rounding fix, live" });
    await end(t, "Fixed and committed; the push and the deploy wait on you."); return t; },
  pr: async () => { const { repo } = await fx("checkout", { git: GIT }); const t = await task("Rounding fix as a pull request", `Fix the rounding and open a PR. My checkout is at ${repo}`);
    await fx("checkout", { git: GIT, repo, branch: "fix-rounding" });
    await agent(t, "propose", { kind: "act", action: "open_pr", cwd: repo, repo: "northwind/ledger", title: "Keep cents in totals", body: "Rounds to two places.\n\n- totals.py: round(sum(a), 2)", why: "the rounding fix" });
    await end(t, "The pull request is set up."); return { ...t, press: [[/^Approve$/, "opened", 6000]] }; },
  // ...the same asked for with no checkout of his on the task: REFUSED at the raise (ci.pr_why - a card that cannot go is never shown), and
  // the agent's turn says so and asks for the one thing missing - the step line reads that it could not be set up
  prbare: async () => { const t = await task("A pull request, no checkout", "Open the PR for the rounding fix on the ledger.");
    await agent(t, "propose", { kind: "act", action: "open_pr", repo: "northwind/ledger", title: "Keep cents in totals", body: "Rounds to two places.\n\n- totals.py: round(sum(a), 2)", why: "the rounding fix" });
    await end(t, "No pull request is set up yet: I do not know which checkout holds the rounding fix. Where is it on your machine?"); return t; },
  comment: async () => { const t = await task("Close the loop on the issue", "Tell them it is fixed.", { source: "https://github.com/northwind/ledger/issues/12" });
    await agent(t, "propose", { kind: "act", action: "comment_issue", repo: "northwind/ledger", number: 12, body: "Fixed in the totals branch - the export rounds to cents now. Thanks for the report.", why: "close the loop" });
    await end(t, "The comment is set up."); return { ...t, press: [[/^Comment$/, "commented"]] }; },
  issue: async () => { const t = await task("File the export bug", "File the export bug on the ledger.");
    await agent(t, "propose", { kind: "act", action: "run_tool", type: "github_issue", repo: "northwind/ledger", title: "Export drops the cents", labels: "bug",
      body: "## What happens\nThe CSV export rounds every total to whole dollars.\n\n## Expected\nTwo decimal places.", why: "he asked" });
    await end(t, "The issue is set up."); return { ...t, press: [[/^Connect GitHub$/, "connect"]] }; },
  jira: async () => { const t = await task("Comment on the ledger ticket", "Tell Erin on the ticket that it is deployed."); const w = await fx("world", { connect: ["jira"], lands: ["jira_comment"] });
    await agent(t, "propose", { kind: "act", action: "run_tool", type: "jira_comment", connector_id: w.connectors.jira, item: "NW-12", body: "Deployed this morning - the totals are right again.", why: "she asked" });
    await end(t, "The comment on NW-12 is set up."); return { ...t, press: [[/^Post comment$/, "commented"]] }; },
  // ...a write on his books: read against them before its card is drawn (reports.CHECKS) - the vendor and account by name, each with its id
  qbobill: async () => { const t = await task("Enter the Payworth bill", "Enter Payworth's November invoice in QuickBooks.");
    const w = await fx("world", { connect: ["quickbooks"], lands: ["quickbooks_bill"], books: { Vendor: { Payworth: 58 }, Account: { "Software subscriptions": 7 } } });
    await agent(t, "propose", { kind: "act", action: "run_tool", type: "quickbooks_bill", connector_id: w.connectors.quickbooks, vendor: "Payworth", amount: "200",
      account: "Software subscriptions", date: "2026-11-24", memo: "November - Basic plan, 40 seats", doc_number: "PW-1124", why: "the November invoice" });
    await end(t, "The Payworth bill is set up for your press."); return { ...t, press: [[/^Approve$/, "approved"]] }; },
  // ...a write on one of his systems asked for through run_system: held as a card, whatever its type
  syswrite: async () => { const t = await task("Move the ticket to Done", "Move NW-12 to Done."); const w = await fx("world", { connect: ["jira"], lands: ["jira_move"] });
    await agent(t, "run_system", { type: "jira_move", connector_id: w.connectors.jira, item: "NW-12", status: "Done" });
    await end(t, "The move is set up for your press."); return { ...t, press: [[/^Approve$/, "approved"]] }; },
  bulk: async () => { const t = await task("Tell the three approvers", "Tell Erin, Gail and Paula the portal goes live Monday.");
    await agent(t, "propose", { kind: "email", items: LETTERS, why: "one note to each approver" }); await end(t, "Three emails, one card.");
    return { ...t, before: () => api("/api/fixture/outbox", { delay: 2.5 }), after: () => api("/api/fixture/outbox", { delay: 0.6 }),
      press: [["tick", "unticked"], [/^Hide$/, "hidden"], [/^Open$/, "opened"], [/^Send \d+ emails?/, "sending", 1500], [null, "finished", 9000]] }; },
  bulkposts: async () => { const t = await task("Six tips for LinkedIn", "Six LinkedIn tips about the portal.");
    await agent(t, "propose", { kind: "post", network: "linkedin", items: [1, 2, 3, 4, 5, 6].map((i) => ({ text: `Ledger portal tip ${i}: invoices in one place, approvals in two steps.` })) });
    await end(t, "Six posts, one card."); return { ...t, press: [[/^Post to LinkedIn - all/, "posting", 900], [null, "finished", 6000]] }; },
  line: async () => { const t = await task("Three separate emails", "Write to Erin, Gail and Paula - each their own email.");
    for (const x of LETTERS) await agent(t, "propose", { kind: "email", ...x, subject: `${x.subject} (${x.to.split("@")[0]})` });
    await end(t, "Three emails, one after another."); return { ...t, press: [[/^Send/, "first-sent", 3000], [/^Don't send$/, "second-not-sent", 3000], [/^Send/, "third-sent", 3000]] }; },
  shell: async () => { const t = await task("Order the bus", "Order the bus from the vendor's API.");
    t.said.push(`    hold: ${JSON.stringify(await fx("hold", { taskId: t.taskId, command: "curl -X POST https://api.vendor.example/orders -d '{\"bus\": 1, \"seats\": 40}'", about: "Order the bus for March 12" })).slice(0, 260)}`);
    await end(t, "The order is ready to send; it waits on your press."); return { ...t, press: [[/^Dismiss$/, "dismissed"]] }; },
  handover: async () => { const t = await task("Pay the venue deposit", "Pay the venue deposit on the vendor's site."); await fx("session", { taskId: t.taskId, url: "https://pay.vendor.example/checkout" });
    await agent(t, "hand_over", { what: 'tick the "I am not a robot" box', site: "pay.vendor.example" }); await end(t, "The checkout is filled in; one step is yours."); return { ...t, press: [[/^I.m done/, "done"]] }; },
  // ...a sign-in its page asks for: ONE card says it, with I'm done and the way to the fill page - never a line over the card too
  signin: async () => { const t = await task("Download the October statement", "Get the October statement from the vendor portal.");
    await fx("session", { taskId: t.taskId, url: "https://portal.vendor.example/login" }); await fx("signin", { taskId: t.taskId, site: "portal.vendor.example", name: "Vendor portal" });
    await end(t, "The portal wants you signed in before I can download it."); return t; },
  question: async () => { const t = await task("Which plan to renew", "Renew the expense tool.");
    await agent(t, "ask_owner", { question: "Which plan should I renew? I would take Basic - the approval flow is the same.", choices: ["Basic - $200/mo", "Pro - $540/mo", "Let it lapse"] });
    await end(t, "One thing I need from you before I renew."); return { ...t, press: [[/^Basic/, "answered"]] }; },
  choice: async () => { const t = await task("Pick a plan in a view", "Show me the plans to pick from.");
    await agent(t, "show", { root: "c", elements: { c: { type: "choice", props: { label: "Which plan should I renew?", options: ["Basic - $200/mo", "Pro - $540/mo", "Let it lapse"] } } } });
    await end(t, "Pick one and I will renew it."); return { ...t, press: [[/^Pro/, "picked"]] }; },
  failed: async () => { const t = await task("A post Bluesky refuses", "Post it on Bluesky.");
    await fx("world", { connect: ["bluesky"], refuse: { bluesky_post: "Bluesky refused the post: the app password has expired - make a new one on its card." } });
    await agent(t, "propose", { kind: "post", network: "bluesky", text: "Three tools, compared." }); await end(t, "The post is set up."); return { ...t, press: [[/^Post to Bluesky$/, "failed", 4000]] }; },
  mailfails: async () => { const t = await task("An email the mailbox refuses", "Tell Omar the deposit is paid.");
    await agent(t, "propose", { kind: "email", to: "omar.keller@vendor.example", subject: "Deposit paid", text: "Hi Omar,\n\nThe venue deposit went out today.\n\nAlex" });
    await end(t, "The email to Omar is set up."); return { ...t, before: () => api("/api/fixture/outbox", { fail: "The mailbox refused the message: 550 mailbox unavailable." }),
      after: () => api("/api/fixture/outbox", { delay: 0.6 }), press: [[/^Send/, "failed", 4000]] }; },
  settings: async () => { const t = await task("Check mail more often", "Check my mail every 10 minutes, and sign my mail with my title.");
    await agent(t, "propose", { kind: "act", action: "settings", changes: { poll_minutes: 10, email_signature: "Alex Doyle\nNorthwind - Finance" }, why: "he asked" }); await end(t, "The two settings wait for your press.");
    return { ...t, press: [[/^Approve$/, "approved"]] }; },
  playbook: async () => { const t = await task("How we renew vendors", "Write down how we renew a vendor.");
    await agent(t, "propose", { kind: "act", action: "write_playbook", slug: "vendor-renewals", text: "# Vendor renewals\nwhen: a vendor's renewal notice arrives\n\n1. Check the price against last year.\n2. Ask Erin to approve anything over $500.\n3. Renew, and file the receipt.", why: "he asked" });
    await end(t, "The playbook page waits for your press."); return t; },
};

const errors = [];
try {
  await api("/api/setup/first-run/ai", { name: "claude" }); await api("/api/setup/dismiss", { dismissed: true });
  await api("/api/fixture/outbox", { delay: 0.6 });
  await fx("world", { connect: ["linkedin"], lands: ["linkedin_post"], github: true, delay: 0.4 });
  await mkdir(OUT, { recursive: true });
  const made = {};
  for (const [k, f] of Object.entries(SHAPES)) {
    if (ONLY.length && !ONLY.includes(k)) continue;
    try { made[k] = await f(); } catch (e) { said.push(`${k}: NOT SEEDED - ${e.message}`); }
  }
  const page = await h.newPage();
  // ...Chrome's own PDF viewer is a page of the browser's (chrome-extension:, chrome:): let through, or every PDF preview is a black box. All else stays shut
  page.off("request", page.fixtureRequestGuard);
  page.on("request", (r) => (/^chrome(-extension|-untrusted)?:/.test(r.url()) ? r.continue() : page.fixtureRequestGuard(r)));
  page.on("response", (r) => { if (r.status() >= 500) errors.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`); });
  page.on("pageerror", (e) => errors.push(`pageerror: ${e.message.slice(0, 300)}`)); page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 300)); });
  await page.goto(h.ui, { waitUntil: "domcontentloaded" }); await sleep(3000);
  // what stands on the task's page: its buttons, and what a card should never read
  const read = () => page.evaluate(() => { const pg = document.querySelector("[data-tq-task-page]"); if (!pg) return { none: true };
    const seen = (e) => e.getBoundingClientRect().width > 0, text = pg.innerText;
    const wide = [...pg.querySelectorAll(".tq-turn-frame, .tq-turn-frame *")].filter((e) => seen(e) && e.scrollWidth > e.clientWidth + 2 && !["auto", "scroll", "hidden"].includes(getComputedStyle(e).overflowX))
      .map((e) => `${e.tagName.toLowerCase()}.${String(e.className).split(" ")[0]} ${e.scrollWidth}>${e.clientWidth}`);
    return { frames: pg.querySelectorAll(".tq-turn-frame").length, cards: pg.querySelectorAll("[data-tq-review-card]").length, files: pg.querySelectorAll("[data-tq-turn-file]").length,
      buttons: [...pg.querySelectorAll(".tq-aui-viewport button")].filter(seen).map((b) => (b.innerText.trim() || b.getAttribute("aria-label") || "").replace(/\s+/g, " ") + (b.disabled ? " (off)" : "")).filter(Boolean).join(" | "),
      junk: ["could not be drawn", "{\"", "TASKUARY-", "[object Object]", "undefined", "NaN", "```", "no preview"].filter((w) => text.includes(w)), overflow: [...new Set(wide)].slice(0, 6),
      imgs: [...pg.querySelectorAll("img")].filter(seen).map((i) => `${(i.getAttribute("src") || "").split("/").slice(-1)[0].slice(0, 40)}:${i.naturalWidth ? "ok" : "BROKEN"}`).join(","),
      focus: (({ tagName: n, className: c } = document.activeElement || {}) => `${String(n || "").toLowerCase()}.${String(c || "").split(" ")[0]}`)(),
      video: [...pg.querySelectorAll("video")].map((v) => `video ${v.videoWidth}x${v.videoHeight} ready=${v.readyState}`).join(","), pageX: document.documentElement.scrollWidth > innerWidth + 2 }; });
  // WHAT HE SEES, THEN ALL OF IT: `name` as the page stands in a window 1000 tall - nothing resized or scrolled by this, so a card drawn off
  // the screen or a blank chat is in the shot - and, where the chat is longer than its window, `name-all` with the window grown to hold it
  const chat = () => page.evaluate(() => { const v = document.querySelector("[data-tq-task-page] .tq-aui-viewport"); if (!v) return null;
    const b = v.getBoundingClientRect(), on = [...v.querySelectorAll(".tq-turn-frame, [data-tq-held-steps], [data-tq-passed], .tq-aui-agent-body p")].filter((e) => e.getBoundingClientRect().height > 0);
    const seen = on.filter((e) => { const r = e.getBoundingClientRect(); return r.bottom > b.top + 4 && r.top < b.bottom - 4; }).length;
    // ...and what hides it, where something does: an ancestor faded or unseen (a blank chat over a card that is there)
    const veil = on[0] ? (() => { for (let e = on[0]; e && e !== document.body; e = e.parentElement) { const c = getComputedStyle(e);
      if (Number(c.opacity) < 0.5 || c.visibility === "hidden") return `${e.tagName.toLowerCase()}.${String(e.className).split(" ").slice(0, 2).join(".")} opacity ${c.opacity} ${c.visibility}`; } return ""; })() : "";
    return { top: Math.round(v.scrollTop), tall: v.scrollHeight, room: v.clientHeight, drawn: on.length, seen, ...(veil ? { HIDDEN_BY: veil } : {}) }; });
  const clip = async () => { const box = await page.evaluate(() => { const r = document.querySelector("[data-tq-task-page]")?.getBoundingClientRect(); return r && r.width > 50 ? { x: r.x, y: r.y, width: r.width, height: r.height } : null; });
    return box ? { clip: { x: Math.max(0, box.x - 8), y: Math.max(0, box.y - 8), width: box.width + 16, height: box.height + 16 } } : {}; };
  // ...and never with Chrome laying the page out again under the capture (captureBeyondViewport): the chat answers a window that changes size, and
  // every other shot was a chat caught mid-move - a card above the fold, a blank view - that no window of his ever showed
  const shot = async (name) => {
    const c = await chat(), w = page.viewport().width;
    await page.screenshot({ path: path.join(OUT, `${name}.png`), captureBeyondViewport: false, ...(await clip()) });
    if (!c || c.tall <= c.room + 2) return c;
    let tall = 1000;
    for (let i = 0; i < 4 && tall < 3600; i++) {
      const need = await page.evaluate(() => { const v = document.querySelector("[data-tq-task-page] .tq-aui-viewport"); return v ? v.scrollHeight - v.clientHeight : 0; });
      if (need <= 0) break;
      tall = Math.min(3600, tall + need + 60); await page.setViewport({ width: w, height: tall }); await sleep(600);
    }
    await page.evaluate(() => { const v = document.querySelector("[data-tq-task-page] .tq-aui-viewport"); if (v) v.scrollTop = 0; }); await sleep(200);
    await page.screenshot({ path: path.join(OUT, `${name}-all.png`), captureBeyondViewport: false, ...(await clip()) });
    await page.setViewport({ width: w, height: 1000 }); await sleep(500);
    return c;
  };
  // ...the task opened as he opens it: from the Assistant, at this window and theme
  const open = async (tid, w = 1440, theme = "light") => {
    await page.evaluate(() => { location.hash = ""; }); await sleep(250);
    await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: theme }]); await page.setViewport({ width: w, height: 1000 }); await sleep(300);
    await page.mouse.move(0, 0);       // ...the pointer off the page: left where the last viewer's picture was, it hovered the next card in its shot
    for (const again of [false, true]) {
      if (again) { await page.goto(`${h.ui}/#task=${tid}`, { waitUntil: "domcontentloaded" }); await page.reload({ waitUntil: "domcontentloaded" }); }
      else await page.evaluate((id) => { location.hash = `task=${id}`; }, tid);
      const ok = await page.waitForFunction((id) => document.querySelector("[data-tq-task-page] .tq-aui-viewport") && location.hash.includes(`task=${id}`), { timeout: 20000 }, tid).then(() => true, () => false);
      if (ok) break;
    }
    await sleep(2600);
  };
  // one press of his: a tick box, a row of a group of files picked by its name, or the lit button whose words match
  const press = (re) => page.evaluate((src) => { const pg = document.querySelector("[data-tq-task-page]"); if (!pg) return "NO TASK PAGE";
    if (src === "tick") { const c = pg.querySelector("[data-tq-bulk-row] input[type=checkbox]"); if (!c) return "NO TICK BOX"; c.click(); return "ticked the first row's box"; }
    if (src.startsWith("pick:")) { const r = [...pg.querySelectorAll("[data-tq-pick]")].find((x) => x.innerText.trim() === src.slice(5)); if (!r) return "NO SUCH ROW"; r.click(); return `picked ${src.slice(5)}`; }
    const b = [...pg.querySelectorAll(".tq-aui-viewport button, .tq-aui-viewport [role=button], [data-tq-browser-pane] button, button")].find((x) => new RegExp(src).test(x.innerText.trim()) && !x.disabled && x.getBoundingClientRect().width > 0);
    if (!b) return "NO SUCH BUTTON"; b.click(); return `pressed ${b.innerText.trim()}`; }, typeof re === "string" ? re : re.source);
  // ...AND EVERY PICTURE A CARD DRAWS OPENS LARGER, TO ZOOM (PictureView): pressed, zoomed by + and the wheel, dragged, stepped to the next where
  // the card holds several, shut by Esc - each shot whole, the viewer standing over the window. Nothing to press, nothing said
  const zoomed = async (tid, k, w, theme) => {
    await open(tid, w, theme);
    const at = await page.evaluate(() => { const i = [...document.querySelectorAll("[data-tq-task-page] .tq-turn-frame img")].find((x) => x.getBoundingClientRect().width > 0);
      if (!i) return null; i.scrollIntoView({ block: "center" }); const r = i.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2, cursor: getComputedStyle(i).cursor }; });
    if (!at) return "";
    const state = () => page.evaluate(() => { const d = document.querySelector("[data-tq-picture-viewer]"); if (!d) return "no viewer";
      const i = d.querySelector("[data-tq-picture-big]"), r = i.getBoundingClientRect();
      return `${i.getAttribute("data-tq-picture-big")} ${d.querySelector("[data-tq-zoom-at]")?.innerText} ${d.querySelector("[data-tq-picture-at]")?.innerText || ""} img ${Math.round(r.width)}x${Math.round(r.height)} ${i.naturalWidth ? "ok" : "BROKEN"}`.trim(); });
    const snap = async (name) => { await sleep(500); await page.screenshot({ path: path.join(OUT, `${k}-${name}.png`), captureBeyondViewport: false }); return `${name}: ${await state()}`; };
    const tag = `viewer-${w}-${theme}`, out = [`card cursor ${at.cursor}`];
    await page.mouse.click(at.x, at.y); out.push(await snap(tag));
    if (w === 1440 && theme === "light") {
      await page.keyboard.press("+"); await page.keyboard.press("+"); out.push(await snap(`${tag}-plus`));
      const s = await page.evaluate(() => { const r = document.querySelector("[data-tq-picture-stage]").getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; });
      await page.mouse.move(s.x, s.y); await page.mouse.down(); await page.mouse.move(s.x + 160, s.y + 90, { steps: 8 }); await page.mouse.up(); out.push(await snap(`${tag}-dragged`));
      await page.keyboard.press("0"); await page.mouse.move(s.x - 200, s.y - 100); await page.mouse.wheel({ deltaY: -400 }); out.push(await snap(`${tag}-wheel`));
      if (await page.$("[data-tq-picture-next]")) { await page.click("[data-tq-picture-next]"); out.push(await snap(`${tag}-next`)); await page.keyboard.press("ArrowRight"); out.push(await snap(`${tag}-arrow`)); }
    }
    if (w === 430) { const c = await page.evaluate(() => { const r = document.querySelector("[data-tq-picture-stage]")?.getBoundingClientRect(); return r && { x: r.x + 6, y: r.bottom - 6 }; });
      if (c) await page.mouse.click(c.x, c.y); await sleep(400); out.push(`press past it: ${await state()}`); }
    else { await page.keyboard.press("Escape"); await sleep(400); out.push(`Esc: ${await state()}`); }
    return out.join(" | ");
  };
  const flush = () => writeFile(path.join(OUT, "README.txt"), said.join("\n") + "\n");
  for (const [k, t] of Object.entries(made)) {
    said.push(`${k}  (task ${t.taskId})`, ...t.said);
    // ...and where each of its cards stands in the store as the page is opened: a card greyed on the screen is one something settled
    const rows = (await api(`/api/tasks/${t.taskId}`)).reviews || [];
    if (rows.length) said.push(`    cards: ${rows.map((r) => `rv${r.ReviewId} ${r.Kind} ${r.Status}${r.DecideNote ? ` (${r.DecideNote})` : ""}`).join(", ")}`);
    try {
      await open(t.taskId, 1440, "light"); said.push(`    wide: ${JSON.stringify({ chat: await shot(`${k}-wide`), ...(await read()) })}`);
      await open(t.taskId, 430, "light"); said.push(`    narrow: ${JSON.stringify({ chat: await shot(`${k}-narrow`), ...(await read()) })}`);
      await open(t.taskId, 1440, "dark"); said.push(`    dark: ${JSON.stringify({ chat: await shot(`${k}-dark`) })}`);
      for (const [w, theme] of [[1440, "light"], [430, "light"], [1440, "dark"]]) { const v = await zoomed(t.taskId, k, w, theme); if (v) said.push(`    viewer ${w} ${theme}: ${v}`); }
      if (t.press?.length) await open(t.taskId, 1440, "light");
      await t.before?.();
      for (const [re, name, wait = 3500] of t.press || []) {
        const did = re === null ? "waited" : typeof re === "function" ? await re(page) : await press(re);
        await sleep(wait); said.push(`    ${name}: ${did} -> ${JSON.stringify({ chat: await shot(`${k}-${name}`), ...(await read()) })}`);
      }
      await t.after?.();
    } catch (e) { said.push(`    NOT SHOT - ${e.message.slice(0, 300)}`); }
    await flush();
  }
  said.push(`woken: ${JSON.stringify((await fx("woken")).woken)}`, `outbox: ${await readFile(path.join(h.home, "outbox.jsonl"), "utf8").then((s) => s.trim().split("\n").length, () => 0)} sends`,
    `page errors: ${errors.length ? [...new Set(errors)].join(" || ") : "none"}`);
} finally {
  await mkdir(OUT, { recursive: true }); await writeFile(path.join(OUT, "README.txt"), said.join("\n") + "\n");
  await writeFile(path.join(OUT, "server.log"), h.log());       // ...what the server said meanwhile: a tool refused for a reason of its own
  console.log(said.join("\n"));
  await h.close();
}
