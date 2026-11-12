// THE CONVERSATION, WALKED ON THE REAL CLI WITH A PER-FRAME SAMPLER (not a test: nothing here runs in CI). node real-conv.mjs <name> <general|acp|pty> [steps...]
// Each animation frame the page writes down what the chat holds - the items in order (their names, where each stands), what waits by the box,
// the scroll - and the rules are read off the frames afterwards (check): his line once from the frame it is heard, nothing new above what was
// drawn, the working line under it in that frame, the scroll never going back, a waiting line never in the conversation, and words that
// name a button only where that button can be pressed in the same frame.
import path from "node:path";
import { readFile, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { api, connect, open, chat, shot, save, sleep, type, press, buttons, out, info } from "./real-lib.mjs";
import { record } from "./recorder.mjs";

// THE BUTTONS' OWN NAMES (taskuary/buttons.json, one name per button) and the ones a card draws: what "names a button" is read against
export const NAMES = [...new Set([...Object.values(JSON.parse(await readFile(path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "taskuary", "buttons.json"), "utf8")).verbs).map((v) => v.label || v.name || v),
  "Approve", "Reject", "Allow once", "Trust", "Withdraw", "Not now"].filter((x) => typeof x === "string" && x))];

export const sampler = (names) => {
  window.__frames = []; let last = "";
  const seen = new Set(names), esc = (s) => s.replace(/[^A-Za-z0-9 ]/g, "\\$&");
  // ...named: a name of several words anywhere; a single word only as a name in the middle of a sentence or marked ("your Send", `Send`) -
  // "Send me the list" names nothing
  const namedIn = (text) => [...seen].filter((n) => new RegExp(n.includes(" ") ? `(^|[^A-Za-z])${esc(n)}($|[^A-Za-z])` : `([a-z,] |["'\`*(])${esc(n)}($|[^A-Za-z])`).test(text));
  const tick = () => {
    const vp = document.querySelector("[data-tq-task-page] .tq-aui-viewport");
    if (vp) {
      const items = [...vp.querySelectorAll("[data-tq-item]")].map((e) => [e.getAttribute("data-tq-item"), e.getAttribute("data-tq-turn") || "", Math.round(e.getBoundingClientRect().top - vp.getBoundingClientRect().top + vp.scrollTop)]);
      const pend = [...document.querySelectorAll("[data-tq-task-page] [data-tq-pending-item]")].map((e) => e.getAttribute("data-tq-pending-item"));
      const f = { items, pend, top: Math.round(vp.scrollTop), h: vp.scrollHeight, ch: vp.clientHeight, working: !!vp.querySelector("[data-tq-working]"), cards: vp.querySelectorAll("[data-tq-turn-cards] button:not([disabled])").length };
      // WORDS THAT NAME A BUTTON, AND THE BUTTON (the owner: never "press X" with nothing to press): the newest thing in the chat, where it is
      // the agent's answer - an older one named a button he has pressed since
      const shown = [...document.querySelectorAll("[data-tq-task-page] button")].filter((b) => b.getBoundingClientRect().width > 0).map((b) => [b.innerText.trim().replace(/\s+/g, " "), !b.disabled]);
      vp.querySelectorAll("[data-tq-turn-cards] button").forEach((b) => { const n = b.innerText.trim().replace(/\s+/g, " "); if (n.length > 2 && n.length < 40 && /^[A-Z]/.test(n)) seen.add(n); });
      const tail = [...vp.querySelectorAll("[data-tq-item]")].pop(), said = tail?.hasAttribute("data-tq-turn") ? [...tail.querySelectorAll("[data-tq-said]")].map((e) => e.innerText).join(" / ") : "";
      // NOTHING EMPTY IS DRAWN (the owner, 2026-11-11: a blank card stood for his approval): an item with no words that is not a turn at work,
      // a card in a turn with none, a line waiting by the box with none
      const bare = (e) => !e.innerText.trim() && !e.querySelector("[data-tq-working], img, video, canvas, textarea");
      const empty = [...[...vp.querySelectorAll("[data-tq-item]")].filter(bare).map((e) => e.getAttribute("data-tq-item")),
        ...[...vp.querySelectorAll("[data-tq-turn-cards] > *")].filter(bare).map((e) => `a card of ${e.closest("[data-tq-item]")?.getAttribute("data-tq-item")}`),
        ...[...document.querySelectorAll("[data-tq-task-page] [data-tq-pending-item]")].filter(bare).map((e) => `waiting ${e.getAttribute("data-tq-pending-item")}`)];
      if (empty.length) f.empty = empty;
      // A CARD THAT CANNOT BE PRESSED SHOWS NO BUTTON, AND ONE ACTION IS ONE CARD (the owner, 2026-11-11: "the question has 2 approve buttons?"):
      // a disabled button on a card at rest, and a settled card standing under a live one
      const cardsOf = [...vp.querySelectorAll("[data-tq-turn-cards] > *, [data-tq-row-cards] .tq-aui-agent-body > *")];
      const dead = cardsOf.filter((c) => c.matches("[data-tq-passed], [data-tq-past-card]") || c.querySelector("[data-tq-passed]"));
      // ...and so does every card that is SETTLED - pressed, sent, dismissed, failed (the card round, 2026-11-12: a greyed "✓ Approved" / "✓ Sent"
      // <button> on each): its state is a mark, and any <button> on it is a finding, greyed or not
      const settled = cardsOf.flatMap((c) => [c, ...c.querySelectorAll("[data-tq-act-state]")]).filter((c) => c.matches("[data-tq-act-state]:not([data-tq-act-state=waiting]):not([data-tq-act-state=resting]), [data-tq-past-card], [data-tq-passed]"));
      if (dead.some((c) => c.querySelector("button[disabled]")) || settled.some((c) => c.querySelector("button"))) f.deadButton = true;
      // ...ONE REVIEW, ONE CARD, AND NO CARD SHOWS ITS OWN JSON: two cards of one review in the chat, and a card whose box holds `{"action": ...`
      const rids = cardsOf.map((c) => (c.matches("[data-tq-passed], [data-tq-act]") ? c : c.querySelector("[data-tq-passed], [data-tq-act]"))).filter(Boolean).map((c) => c.getAttribute("data-tq-passed") || c.getAttribute("data-tq-act")).filter(Boolean);
      if (new Set(rids).size < rids.length) f.cardTwice = true;
      if (cardsOf.some((c) => [...c.querySelectorAll("textarea")].some((t) => /^\s*\{\s*"action"\s*:/.test(t.value)))) f.rawCard = true;
      // EACH MESSAGE OF A TURN IS A PARAGRAPH (the owner, 2026-11-11: three messages of one turn stacked as consecutive lines): two blocks of a
      // turn's words with no room between them
      const box = document.querySelector("[data-tq-task-page] .tq-aui-footer")?.getBoundingClientRect();
      f.w = Math.round(vp.getBoundingClientRect().width);
      if (box && (box.right > innerWidth + 1 || box.bottom > innerHeight + 1)) f.boxOff = [Math.max(0, Math.round(box.right - innerWidth)), Math.max(0, Math.round(box.bottom - innerHeight))];
      if ([...vp.querySelectorAll(".tq-aui-agent-body > .tq-md + .tq-md")].some((e) => e.getBoundingClientRect().top - e.previousElementSibling.getBoundingClientRect().bottom < 4)) f.tight = true;
      // ...and where each card stands, by its own first line and the item it is under: one that goes back UP the chat is a finding (check)
      f.at = cardsOf.filter((c) => !c.matches("[data-tq-past-card]")).map((c) => [c.innerText.trim().split("\n")[0].slice(0, 60), c.closest("[data-tq-item]")?.getAttribute("data-tq-item") || ""]);
      // ...ONE STEP, ONE PAIR OF BUTTONS, AND HIS WORDS ONCE (recorded on a coding agent, 2026-11-11: a held delete drew Allow once / Reject
      // twice - its card, and the same request as the agent's question - and the line he typed under it stood in the chat twice)
      f.allows = [...document.querySelectorAll("[data-tq-task-page] button:not([disabled])")].filter((b) => b.getBoundingClientRect().width > 0 && b.innerText.trim() === "Allow once").length;
      const said2 = [...vp.querySelectorAll(".tq-aui-user-bubble")].map((e) => e.innerText.trim());
      f.twice = said2.filter((w, i) => i && w === said2[i - 1] && w.length > 12);
      if (!f.twice.length) delete f.twice;
      const lastLive = cardsOf.map((c, i) => (c.querySelector("button:not([disabled])") ? i : -1)).reduce((a, b) => Math.max(a, b), -1);
      if (lastLive >= 0 && dead.some((c) => cardsOf.indexOf(c) > lastLive && c.matches("[data-tq-passed]"))) f.staleUnder = true;
      const named = said ? namedIn(said) : [];
      // ...read once its turn is at rest (its card lands when its words have), and never for a button that WAS lit under this answer and
      // has been pressed since: "it waits for your Send" was true when said
      const lit = (window.__lit ||= {}), key = tail?.getAttribute("data-tq-item"), had = (lit[key] ||= []);
      named.filter((n) => shown.some(([b, on]) => on && b === n) && !had.includes(n)).forEach((n) => had.push(n));
      if (named.length && !f.working) { f.named = named; f.unlit = named.filter((n) => !had.includes(n)); if (!f.unlit.length) delete f.unlit; }
      const sig = JSON.stringify(f);
      if (sig !== last) { last = sig; window.__frames.push({ t: Math.round(performance.now()), ...f }); }
    }
    window.__raf = requestAnimationFrame(() => setTimeout(tick, 0));     // read AFTER the frame is painted: what he saw, never a layout the page had not pinned yet
  };
  tick();
};
export function check(frames) {
  const bad = [], say = (t, m) => bad.push(`${t} ms: ${m}`);
  let prev = null, before = null; const heard = new Set();
  for (const f of frames) {
    const ids = f.items.map((x) => x[0]), seen = new Set();
    for (const id of ids) { if (seen.has(id)) say(f.t, `${id} drawn twice`); seen.add(id); }
    for (const id of f.pend) if (seen.has(id)) say(f.t, `${id} is by the box AND in the conversation`);
    for (const id of heard) if (!seen.has(id)) say(f.t, `${id} was in the conversation and is gone`);
    if (prev) {
      const was = new Set(prev.items.map((x) => x[0])), lastOld = Math.max(-1, ...ids.map((id, i) => (was.has(id) ? i : -1)));
      ids.forEach((id, i) => { if (!was.has(id) && i < lastOld) say(f.t, `${id} drawn ABOVE ${ids[lastOld]}, which was already there`); });
      // ...the view went back: only where it is no longer at its end, or went back though nothing above got shorter (a fold closing at the end keeps it pinned)
      if (f.top < prev.top - 2 && f.h - f.top - f.ch > 2 && (f.h - f.top - f.ch > 60 || f.h >= prev.h)) say(f.t, `scrolled back ${prev.top} -> ${f.top} (height ${prev.h} -> ${f.h})`);
      // THE CHAT FOLLOWS ITS END (the owner, 2026-11-11): at the bottom it stays at the bottom through every draw; scrolled up to read, it is
      // not moved (this driver never scrolls, so any move there is the page's own)
      const gap = (x) => x.h - x.top - x.ch;
      if (gap(prev) <= 2 && gap(f) > 2) say(f.t, `was at its end and fell ${gap(f)} px behind (height ${prev.h} -> ${f.h})`);
      if (gap(prev) > 60 && f.top !== prev.top) say(f.t, `moved by itself while he read above: ${prev.top} -> ${f.top}`);
      // his line, the frame it enters the conversation: a turn at work right under it
      ids.forEach((id, i) => { if (!was.has(id) && /^(l|s)[0-9a-z]/.test(id) && !f.items.slice(i + 1).some((x) => x[1] === "starting" || x[1] === "working")) say(f.t, `${id} heard with no turn at work under it in that frame`); });
    }
    // words that name a button, with no such button to press in that frame (said once per run of frames that lack it)
    if (f.unlit?.length && JSON.stringify(f.unlit) !== JSON.stringify(prev?.unlit || [])) say(f.t, `the agent's words name ${f.unlit.map((n) => `"${n}"`).join(", ")} and no such button is lit`);
    for (const id of f.empty || []) if (!(prev?.empty || []).includes(id)) say(f.t, `${id} is drawn empty`);
    if (f.deadButton && !prev?.deadButton) say(f.t, "a card nobody can press draws a button");
    if (f.cardTwice && !prev?.cardTwice) say(f.t, "one action stands in the chat as two cards");
    if (f.rawCard && !prev?.rawCard) say(f.t, "a card shows its own JSON");
    if (f.tight && !prev?.tight) say(f.t, "two messages of one turn stand as consecutive lines, no paragraph's room between");
    // A CHAT IS FIRST SEEN AT ITS END (the owner, 2026-11-11: "task should open on last thing not randomly in middle"): the first painted frame too
    if (!prev && f.h - f.top - f.ch > 2) say(f.t, `first seen ${f.h - f.top - f.ch} px short of its end`);
    // NOTHING JUMPS OR RESIZES (the owner, 2026-11-11): a chat whose width changes and is back within 600 ms drew a layout nobody meant - the
    // pane beside it arriving in three steps, the section's room changing as its agent started - and the box never stands past the window
    if (prev && before && f.w && f.w === before.w && prev.w !== f.w && f.t - before.t < 600) say(f.t, `the chat's width jumped ${before.w} -> ${prev.w} -> ${f.w} px within ${f.t - before.t} ms`);
    if (f.boxOff && !prev?.boxOff) say(f.t, `the box stands past the window's edge (${f.boxOff[0]} px right, ${f.boxOff[1]} px down)`);
    before = prev;
    if (f.staleUnder && !prev?.staleUnder) say(f.t, "a settled card stands under the live one");
    // A CARD NEVER GOES BACK UP THE CHAT (the recorded held step, 2026-11-11: approved under the newest answer, it failed and was drawn again
    // under the turn that first raised it - where he had pressed stood nothing): the lowest place a card stood is where it stays, or lower
    if (prev) for (const [title, host] of prev.at || []) {
      const was = ids.indexOf(host), now = Math.max(-1, ...(f.at || []).filter(([t]) => t === title).map(([, h]) => ids.indexOf(h)));
      if (title && was >= 0 && now >= 0 && now < was && !(f.at || []).some(([t, h]) => t === title && ids.indexOf(h) >= was)) say(f.t, `the card "${title}" went back up the chat: from under ${host} to under ${ids[now]}`);
    }
    if (f.allows > 1 && !(prev?.allows > 1)) say(f.t, `${f.allows} lit "Allow once" buttons: one step drawn as two cards`);
    for (const w of f.twice || []) if (!(prev?.twice || []).includes(w)) say(f.t, `his line "${w.slice(0, 60)}" stands in the chat twice, one under the other`);
    // THE CHAT OPENS WITH AN INPUT, NEVER WITH THE AGENT (the owner, 2026-11-11: "it did not show the prompt i asked it to do"): the first
    // thing drawn is what the first turn heard - his ask, a message that came in - and a turn at work has his newest line above it
    if (f.items.length && f.items[0][1] && !(prev?.items.length && prev.items[0][1])) say(f.t, `the chat begins with the agent's turn ${f.items[0][0]} - no ask above it`);
    ids.filter((id) => !id.startsWith("t:")).forEach((id) => heard.add(id)); prev = f;
  }
  // NO DEAD END AT THE END (the recorded restart, 2026-11-11: his line stood heard, nothing under it, nothing at work): the walk's last frame
  // never ends on a line of his with no turn at work
  const end = frames.at(-1), tail = end?.items.at(-1);
  const his = (x) => !!x && /^(l[0-9a-z]|s[0-9a-z]|a:|c:|y:)/.test(x[0]);
  if (his(tail) && !end.working) say(end.t, `the chat ends on his line ${tail[0]} with nothing under it and nothing at work`);
  // ...nor on his press with a line of his right above it that no turn answered (recorded on a coding agent, 2026-11-11: two lines sent
  // into the turn, Stop - and they stood over "You stopped the agent" for good)
  if (tail && /^p:/.test(tail[0]) && his(end.items.at(-2)) && !end.working && !end.pend.length) say(end.t, `the chat ends on his press with his line ${end.items.at(-2)[0]} above it and no turn that answered it`);
  return bad;
}
const frames =(page) => page.evaluate(() => window.__frames);
const working = (page) => page.evaluate(() => !!document.querySelector("[data-tq-task-page] .tq-aui-viewport [data-tq-working]"));
// at rest by the SERVER's word and the page's both - the two disagreeing for long is a finding (said when it ends)
export async function rest(page, tid, timeout = 300000, settle = 4000) { const end = Date.now() + timeout; let calm = 0, split = 0, how = "";
  while (Date.now() < end) { const dom = await working(page), srv = (await api(`/api/tasks/${tid}/conversation`)).working;
    if (dom !== srv) { split += 400; how = `page ${dom ? "working" : "at rest"}, server ${srv ? "working" : "at rest"}`; }
    // ...and where the server says nothing works, nothing on the page spins: a turn left at work under a finished one is a finding at once
    if (!srv && dom && (split += 0) >= 0 && (rest.ghost = (rest.ghost || 0) + 400) === 3200) console.log("FINDING: the server says at rest and a working indicator still stands on the page");
    if (dom || srv) calm = 0; else if ((calm += 400) >= settle) { if (split > 2500) console.log(`FINDING: page and server disagreed on "working" for ${split} ms (${how})`); return true; }
    await sleep(400); } console.log("FINDING: never came to rest"); return false; }
async function untilWorking(page, timeout = 60000) { const end = Date.now() + timeout; while (Date.now() < end) { if (await working(page)) return true; await sleep(100); } return false; }

if (process.argv[1]?.endsWith("real-conv.mjs")) {
  const [name, road = "general", ...steps] = process.argv.slice(2);
  let tid;
  await api("/api/fixture/outbox", {});          // ...the mailbox that sends nowhere lives in the server's process: set again after a restart of it
  // ...`stranger`: a general task whose first mail is from someone the owner never trusted (no agent starts: the hold and its Trust action)
  const who = road === "stranger" ? { from_name: "Paula Vance", from_email: "paula@vendor.example" } : { from_name: "Gail Moreno", from_email: "gail@northwind.example" };
  // ...TID: carry on a task an earlier walk left (leave and come back; a timeline of several walks on one task)
  if (process.env.TID) tid = Number(process.env.TID);
  else if (road === "general" || road === "stranger") {
    // ...TOPIC_SUBJECT / TOPIC_BODY: another ask than the venue one - a second walk of one instance with the same words is read as the same mail again
    const got = await api("/api/ingest/push", { channel: "email", subject: process.env.TOPIC_SUBJECT || "Offsite venue", ...who, conversation_id: `conv-${name}`,
      body: (process.env.TOPIC_BODY || "Hi Alex,\n\nCan you suggest two venues for the March offsite, about 40 people, and tell me which one you would pick? A short answer is fine.\n\nThanks,\nGail").replace(/\\n/g, "\n") });
    console.log("push", JSON.stringify(got).slice(0, 200)); tid = got.task_id;
  // ...`new`: a task he made himself with New - no mail, no typed line: its ask is the task's own words, and its agent is started as the page starts it
  } else if (road === "new") { const got = await api("/api/tasks", { Title: process.env.TOPIC_BODY || "Suggest two venues for a 40-person offsite in March and tell me which one you would pick.", Kind: "general" });
    // ...by the page's own road (NewSheet: the task, then /dispatch) - Continue's road told a task that had never run "the owner chose Resume",
    // and its agent opened on "Nothing had been done before this resume" (the recorded walk, 2026-11-11)
    tid = got.taskId; console.log("new", JSON.stringify(got), JSON.stringify(await api(`/api/tasks/${tid}/dispatch`, { kind: "general" })).slice(0, 160));
  } else { const got = await api("/api/fixture/coding", { git: info.git, real: true, pty: road === "pty", conversation: `conv-${name}` }); tid = got.taskId; }
  const subject = road === "general" || road === "stranger" ? `Re: ${process.env.TOPIC_SUBJECT || "Offsite venue"}` : "Re: Ledger totals";
  const { browser, page } = await connect();
  await page.reload({ waitUntil: "domcontentloaded" }); await sleep(3000);
  await open(page, tid);
  await page.waitForSelector("[data-tq-task-page] .tq-aui-input", { visible: true, timeout: 120000 });
  await sleep(2500);                    // ...the task's own page, not the one a walk before this left open: its box took the first line and went away
  const rec = await record(page, path.join(out, "video", name));
  await page.evaluate(sampler, NAMES);
  const snap = async (n) => { await shot(page, `${name}-${n}`); const c = await api(`/api/tasks/${tid}/conversation`); await save(`${name}-${n}-list.json`, c);
    console.log(`[${n}]`, c.items.map((x) => `${x.kind}${x.state ? ":" + x.state : ""}${x.cards?.length ? "+" + x.cards.length + "c" : ""}`).join(" "), "| pending", c.pending.length, "| working", c.working); };
  for (const s of steps.length ? steps : ["rest", "say:Make it one paragraph shorter.", "rest"]) {
    const [k, ...r] = s.split(":"), arg = r.join(":");
    if (k === "rest") { await rest(page, tid); await snap(`rest${Date.now() % 100000}`); }
    else if (k === "say") { await type(page, arg); await sleep(300); }
    else if (k === "busy") await untilWorking(page);                     // wait until a turn is at work
    else if (k === "wait") await sleep(Number(arg));
    // ...a stranger writes on the thread: his words wait by the box, behind the Trust action
    else if (k === "strangermail") console.log("mail", JSON.stringify(await api("/api/ingest/push", { channel: "email", subject, from_name: "Omar Keller", from_email: "omar@other.example", conversation_id: `conv-${name}`, body: arg })).slice(0, 160));
    else if (k === "mail") console.log("mail", JSON.stringify(await api("/api/ingest/push", { channel: "email", subject, from_name: "Gail Moreno", from_email: "gail@northwind.example", conversation_id: `conv-${name}`, body: arg })).slice(0, 160));
    else if (k === "press") console.log(await press(page, new RegExp(arg), "[data-tq-task-page]"));
    // ...pressed twice in one breath (one send, one line), his own answer on the channel outside the app, a card's words changed before its press
    else if (k === "press2") console.log(await press(page, new RegExp(arg), "[data-tq-task-page]"), "|", await press(page, new RegExp(arg), "[data-tq-task-page]"));
    else if (k === "own") console.log("own", JSON.stringify(await api("/api/fixture/own-reply", { id: `own-${name}-${Date.now()}`, conversation: `conv-${name}`, subject, body: arg })));
    else if (k === "edit") { const ok = await page.evaluate(() => { const t = [...document.querySelectorAll("[data-tq-task-page] [data-tq-turn-cards] textarea")].filter((x) => !x.disabled && !x.readOnly).pop(); t?.focus(); return !!t; });
      if (ok) { await page.keyboard.down("Control"); await page.keyboard.press("End"); await page.keyboard.up("Control"); await page.keyboard.type(arg); } console.log("edit", ok); }
    else if (k === "chat") { const t = await chat(page); await save(`${name}-chat-${arg || "end"}.txt`, t); console.log(`--- chat (${arg || "end"})\n${t.slice(-(Number(process.env.CHAT_TAIL) || 900))}`); }
    else if (k === "flood") { const n = Number(arg) || 50;
      // ...three voices, mixed: the sender on the channel, his own replies on that channel, lines typed here
      for (let i = 0; i < n; i++) { const w = `flood line ${i + 1} of ${n}: note ${i + 1}`;
        if (i % 3 === 1) api("/api/fixture/own-reply", { id: `own-${name}-${i}`, conversation: `conv-${name}`, subject, body: w }).catch((e) => console.log("own", e.message));
        else if (i % 3 === 0) api("/api/ingest/push", { channel: "email", subject, from_name: "Gail Moreno", from_email: "gail@northwind.example", conversation_id: `conv-${name}`, body: w }).catch(() => {});      // a mail's triage takes its time: never waited for either
        else api(`/api/tasks/${tid}/assistant/messages`, { text: w, line_id: `lflood${name}${i}` }).catch(() => {});      // not waited for: typed as fast as he can
        await sleep(150); } }
    else if (k === "snap") await snap(arg || "snap");
    // ...the three ways a turn ends with his lines still waiting: his own stop (the x on the turn), its process dying under it, the app restarting
    else if (k === "stop") console.log("stop", await page.evaluate(() => { const b = document.querySelector("[data-tq-task-page] [data-tq-stop-run]"); b?.click(); return !!b; }));
    else if (k === "kill") console.log("kill", JSON.stringify(await api("/api/fixture/session", { taskId: tid, state: "killed" })));
    else if (k === "restart") { await writeFile(path.join(out, "restart"), ""); const end = Date.now() + 120000;
      while (existsSync(path.join(out, "restart")) && Date.now() < end) await sleep(500);
      console.log("restart", existsSync(path.join(out, "restart")) ? "NOT DONE" : "done"); await sleep(3000); await api("/api/fixture/outbox", {}).catch(() => {}); }
    else if (k === "count") { const c = await api(`/api/tasks/${tid}/conversation`); const w = (x) => String(x.text || x.words || "");
      const on = c.items.filter((x) => ["line", "arrival"].includes(x.kind)).map((x) => (w(x).match(/flood line (\d+) of/) || [])[1]).filter(Boolean).map(Number);
      const pe = c.pending.map((x) => (w(x).match(/flood line (\d+) of/) || [])[1]).filter(Boolean).map(Number);
      console.log(`COUNT on canvas ${new Set(on).size} (drawn twice ${on.length - new Set(on).size}) | by the box ${pe.length} | both ${pe.filter((n) => on.includes(n)).length} | in order ${on.every((n, i) => !i || on[i - 1] < n)} | order ${on.join(",")}`); }
  }
  const fr = await frames(page), bad = check(fr);
  await save(`${name}-frames.json`, fr); await save(`${name}-findings.txt`, bad.join("\n") || "no rule broken");
  await rec.stop({ sheet: 12 });
  console.log("FRAMES", fr.length, "RULES BROKEN", bad.length); console.log(bad.slice(0, 25).join("\n"));
  console.log("TASK", tid, "BUTTONS", (await buttons(page)).slice(0, 30));
  await browser.disconnect();
}
