// THE OWNER'S THUMB ON HIS PHONE (not a test: nothing here runs in CI). real-run.mjs started with REAL_FAKE_WA=<port> keeps a stand-in WhatsApp
// bridge (fake_wa_bridge.py) on the walk app's WhatsApp card; this types in his own chat, taps the polls the app sends and sends it files -
// and every command waits for the app to answer, then prints what reached the phone, bubble by bubble, as he would read it.
//   node phone.mjs say "<words>"          a line in his chat ("@file" is that file's words)
//   node phone.mjs tap <n|words> [poll]   a tap on the newest poll (or that poll's id, from `read`): its n-th choice, or the one starting so
//   node phone.mjs send <file> ["words"]  a picture, a PDF or a voice note, with words under it
//   node phone.mjs read                   what arrived since the last read, without doing anything (`read all`: the whole chat)
//   node phone.mjs wait <seconds>         let time pass, then read - for what comes later, or to prove nothing comes
//   node phone.mjs restart                the bridge restarted (new boot, its polls forgotten)  |  drop / back: WhatsApp's link down / up
// PHONE_WAIT (s, default 300): how long to wait for the first answer; PHONE_SETTLE (s, default 12): the quiet that says it is done.
import path from "node:path";
import os from "node:os";
import { existsSync, readFileSync, writeFileSync } from "node:fs";

const out = process.env.REAL_OUT || path.join(os.tmpdir(), "claude", "real");
const info = existsSync(path.join(out, "info.json")) ? JSON.parse(readFileSync(path.join(out, "info.json"), "utf8")) : {};
const URL_ = process.env.PHONE_URL || info.fakeWa;
if (!URL_) { console.log("no phone: start real-run.mjs with REAL_FAKE_WA=<port> (or set PHONE_URL)"); process.exit(1); }
const WAIT = 1000 * Number(process.env.PHONE_WAIT || 300), SETTLE = 1000 * Number(process.env.PHONE_SETTLE || 12);
const cur = path.join(out, "phone-cursor.json");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const call = (p, body) => fetch(`${URL_}${p}`, { method: body ? "POST" : "GET", headers: { "content-type": "application/json" }, body: body && JSON.stringify(body) })
  .then(async (r) => ({ status: r.status, ...(await r.json()) }));
const [cmd = "read", ...args] = process.argv.slice(2).map((a) => (a.startsWith("@") && existsSync(a.slice(1)) ? readFileSync(a.slice(1), "utf8") : a));
const seen = () => { try { return JSON.parse(readFileSync(cur, "utf8")).n || 0; } catch { return 0; } };
const mark = (n) => writeFileSync(cur, JSON.stringify({ n }));
const hhmmss = (t) => new Date(t * 1000).toTimeString().slice(0, 8);

// what a person would stumble on in a chat bubble - flagged for whoever plays him to judge, never judged here
const ODD = [[/\*\*|__|^#{1,6} |```|^\s*[-*] \[[ x]\]/m, "markdown"], [/https?:\/\/\S+/, "a raw link"], [/[{[]\s*"\w+"\s*:/, "raw JSON"],
  [/\b\w+\.(md|py|json|jsx?|mjs|log)\b/i, "a file name"], [/\b(CALL:|ACP|JOB\.md|SOUL\.md|triage|review_id|connector_id|tool_use)\b/, "builder words"],
  [/@s\.whatsapp\.net|@g\.us|\b[\w.]+@[\w.-]+\.\w+\b/, "an address"]];

function show(bs, t0) {
  for (const b of bs) {
    const at = `[${hhmmss(b.at)}${t0 ? ` +${(b.at - t0).toFixed(1)}s` : ""}]`;
    if (b.from === "owner") { console.log(`${at} YOU${b.kind === "vote" ? ` tapped "${b.text}"${b.stale ? " (an older poll)" : b.spent ? " (a poll already answered)" : ""}` : b.kind !== "text" ? ` sent a ${b.kind} ${b.name}${b.text ? `: ${b.text}` : ""}` : `: ${b.text}`}`); continue; }
    const flags = [b.unasked && "UNASKED - no line of yours in the 30 minutes before it", ...ODD.filter(([re]) => re.test(b.text || "")).map(([, w]) => w)].filter(Boolean);
    if (b.kind === "poll") console.log(`${at} POLL (${b.id}) "${b.text}":\n${b.poll.map((v, i) => `   ${i + 1}) ${v}`).join("\n")}`);
    else if (b.kind === "doc") console.log(`${at} FILE ${b.name} (${b.mime}, ${b.bytes} bytes) saved at ${b.file}${b.text ? `\n${b.text}` : ""}`);
    else console.log(`${at} TASKUARY${b.quote ? ` (a reply to ${JSON.stringify(b.quote).slice(0, 80)})` : ""}:\n${b.text}`);
    if (flags.length) console.log(`   LOOK: ${flags.join("; ")}`);
  }
}

// the app's answer: the first bubble within WAIT, then until SETTLE passes with nothing new; a thumb on his line is said too
async function answer(t0, id) {
  const from = seen(), end = Date.now() + WAIT; let last = Date.now(), n = from, got = [], thumb = false;
  while (Date.now() < end) {
    const r = await call(`/bubbles?after=${n}&all=1`);
    if (r.bubbles.length) { got.push(...r.bubbles); n = r.n; if (r.bubbles.some((b) => b.from === "app")) last = Date.now(); }
    if (id && !thumb) thumb = (await call("/reacts")).reacts.some((x) => x.id === id);
    const app = got.some((b) => b.from === "app");
    if (app && Date.now() - last >= SETTLE) break;
    await sleep(700);
  }
  if (id) console.log(thumb ? "(a thumb went up on your line)" : "(no thumb on your line)");
  if (!got.some((b) => b.from === "app")) console.log(`NOTHING came back in ${WAIT / 1000}s`);
  show(got, t0); mark(n);
}

const now = () => Date.now() / 1000;
if (cmd === "say") { const t0 = now(), r = await call("/owner", { text: args.join(" ") }); await answer(t0, r.id); }
else if (cmd === "tap") {
  const t0 = now(), r = await call("/vote", { option: args[0], ...(args[1] ? { poll: args[1] } : {}) });
  if (r.status >= 300) console.log(`could not tap: ${r.error}`); else { console.log(`tapped "${r.picked}"${r.stale ? " - on a poll already used or replaced" : ""}`); await answer(t0, r.id); }
}
else if (cmd === "send") {
  const t0 = now(), r = await call("/media", { path: path.resolve(args[0]), caption: args.slice(1).join(" ") });
  if (r.status >= 300) console.log(`could not send: ${r.error}`); else await answer(t0, r.id);
}
else if (cmd === "read") { const r = await call(`/bubbles?after=${args[0] === "all" ? 0 : seen()}&all=1`); show(r.bubbles); mark(r.n); if (!r.bubbles.length) console.log("nothing new"); }
else if (cmd === "wait") { await sleep(1000 * Number(args[0] || 30)); const r = await call(`/bubbles?after=${seen()}&all=1`); show(r.bubbles); mark(r.n); if (!r.bubbles.length) console.log(`nothing in ${args[0] || 30}s`); }
else if (cmd === "restart") console.log(JSON.stringify(await call("/restart", {})));
else if (cmd === "drop" || cmd === "back") console.log(JSON.stringify(await call("/connected", { on: cmd === "back" })));
else console.log("commands: say <words> | tap <n|words> [poll] | send <file> [words] | read [all] | wait <s> | restart | drop | back");
