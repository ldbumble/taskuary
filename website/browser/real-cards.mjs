// ONE CARD AT A TIME, WALKED ON THE REAL CLI (not a test: nothing here runs in CI). node real-cards.mjs <name> <emails|push|push-fails>
// The owner, 2026-11-16: "where there are 2 action cards, like approve push then email, it should wait on each approval step or action card ...
// same with 2 emails, it should say I have 2 emails to send, should we send this one? then user clicks then the next one shows". Against the
// instance real-run.mjs keeps up: the agent raises two cards in one turn, the first stands with "1 of 2 · next: ..." over it, he presses it,
// and the second stands only once the turn that heard the first go has ended - recorded, each frame sampled (real-conv's rules), and what
// stood on the page at each step written down beside the video.
import path from "node:path";
import { execFileSync } from "node:child_process";
import { api, connect, open, shot, save, sleep, type, press, buttons, out, info } from "./real-lib.mjs";
import { record } from "./recorder.mjs";
import { NAMES, sampler, check, rest } from "./real-conv.mjs";

const [name = "cards", walk = "emails"] = process.argv.slice(2);
// what stands on the page: the cards' presses lit, the line over the one that stands, and the server's own word on the line
const stands = async (page, tid) => {
  const dom = await page.evaluate(() => {
    const pg = document.querySelector("[data-tq-task-page]"), lit = (re) => [...(pg?.querySelectorAll("button") || [])].filter((b) => re.test(b.innerText.trim()) && !b.disabled && b.getBoundingClientRect().width > 0).length;
    return { send: lit(/^Send$/), push: lit(/^Push/), approve: lit(/^Approve$/), line: [...(pg?.querySelectorAll("[data-tq-card-queue]") || [])].map((e) => e.innerText) };
  });
  const c = await api(`/api/tasks/${tid}/conversation`);
  return { ...dom, queue: c.queue, items: c.items.map((x) => `${x.kind}${x.state ? ":" + x.state : ""}${x.cards?.length ? "[" + x.cards.map((k) => `${k.review}:${k.status}`).join(",") + "]" : ""}`).join(" "), letters: c.letters };
};

async function run(tid, page, ask, steps) {
  await open(page, tid);
  await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 120000 });
  await sleep(2500);
  const rec = await record(page, path.join(out, "video", `${name}-${walk}`)), log = [];
  await page.evaluate((tid) => { window.__tid = tid; }, tid);
  await page.evaluate(sampler, NAMES);
  const snap = async (n) => { await shot(page, `${name}-${walk}-${n}`); const s = await stands(page, tid); log.push([n, s]); console.log(`[${n}]`, JSON.stringify(s)); await save(`${name}-${walk}-${n}-list.json`, await api(`/api/tasks/${tid}/conversation`)); return s; };
  await rest(page, tid); await snap("0rest");
  if (ask) { await type(page, ask); await sleep(1500); await snap("1asked"); await rest(page, tid, 600000); await sleep(2000); }
  const first = await snap("2raised");
  for (const [i, re] of steps.entries()) {
    // ...a step is a press, or a line he types (`{ line }`): the card above it greys where it stands from that frame
    if (re.line) { await type(page, re.line); console.log(`[typed ${i + 1}]`, re.line); await sleep(300); }
    else console.log(`[press ${i + 1}]`, await press(page, re, "[data-tq-task-page]"));
    await sleep(900); await snap(`3pressed-${i + 1}`);
    await sleep(4000); await snap(`4woken-${i + 1}`);
    await rest(page, tid, 600000); await sleep(3000); await snap(`5rest-${i + 1}`);
  }
  const fr = await page.evaluate(() => window.__frames), bad = check(fr);
  await save(`${name}-${walk}-frames.json`, fr); await save(`${name}-${walk}-findings.txt`, [...new Set(bad)].join("\n") || "no rule broken");
  await save(`${name}-${walk}-steps.json`, log);
  await rec.stop({ sheet: 12 });
  console.log("FRAMES", fr.length, "RULES BROKEN", new Set(bad).size); console.log([...new Set(bad)].slice(0, 20).join("\n"));
  console.log("BUTTONS", (await buttons(page)).slice(0, 300));
  return first;
}

const { browser, page } = await connect();
await api("/api/fixture/outbox", {});
// ...a coding task is made before the page loads: the page reads once, as it loads, whether a coding tool is connected (capabilities.js)
const coding = walk === "emails" ? null : await api("/api/fixture/coding", { git: info.git, real: true, title: "Tax on the ledger totals" });
await page.reload({ waitUntil: "domcontentloaded" }); await sleep(3000);
if (walk === "emails") {
  const t = await api("/api/ingest/push", { channel: "email", subject: "Offsite logistics", from_name: "Gail Moreno", from_email: "gail@northwind.example", conversation_id: `conv-${name}-emails`,
    body: "Hi Alex,\n\nTwo things for the March offsite, please - as two separate emails:\n- ask Ray Colton (ray.colton@northwind.example) for a quote for a bus for 40 people on March 12;\n- ask Erin Blake (erin.blake@northwind.example) to approve the $4,000 budget.\n\nThanks,\nGail" });
  console.log("push", JSON.stringify(t).slice(0, 160));
  await run(t.task_id, page, "Draft the two emails Gail asks for - one to Ray, one to Erin. No reply to Gail yet.", [/^Send$/, /^Send$/]);
} else if (walk === "past") {
  // THE CHAT MOVES ON PAST A CARD (the owner, 2026-11-16: "The second a new prompt comes in, from manual or email, it should gray out the action
  // card but never move"): an email stands for his Send, he types a new line instead - it greys in place at once, the agent raises what still holds
  const t = await api("/api/ingest/push", { channel: "email", subject: "Venue deposit", from_name: "Paula Vance", from_email: "paula@northwind.example", conversation_id: `conv-${name}-past`,
    body: ["Hi Alex,", "Can you email Omar Keller (omar.keller@northwind.example) to pay the $1,500 venue deposit for the offsite by Friday?", "Paula"].join("\n\n") });
  await run(t.task_id, page, "Draft the email to Omar that Paula asks for.", [{ line: "Make it $1,200 - Paula said the venue gave us a discount." }]);
} else {
  // a coding task on the home's own repository, with a remote of its own to push to (a bare one beside it) - none for push-fails
  const t = coding;
  if (walk === "push") {
    const bare = path.join(info.home, "ledger-origin.git");
    const git = (...a) => { try { execFileSync(info.git, a, { stdio: "pipe" }); } catch (e) { console.log("git", a.join(" "), String(e.stderr || e).slice(0, 160)); } };
    git("init", "-q", "--bare", bare); git("-C", t.repo, "remote", "add", "origin", bare); git("-C", t.repo, "push", "-q", "-f", "origin", "HEAD:master");
  }
  console.log("coding", JSON.stringify(t).slice(0, 200));
  await run(t.taskId, page, "In totals.py, tax is a rate: total(a, tax) should return a * (1 + tax). Fix it and commit it on master. Then, in this turn, set up both " +
    "cards in order: the push, and after it an email to Erin Blake (erin.blake@northwind.example) telling her the fix is live.", [/^Push$/, /^Send$/]);
}
await browser.disconnect();
