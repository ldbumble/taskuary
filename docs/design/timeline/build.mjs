// Emits the .dc.html artboards for the Timeline redesign canvas.
//
// Every value here is lifted from the running app, not invented: the palette and roles from
// website/src/theme.jsx, the type stack (IBM Plex Sans/Mono), the 8px radius and the button
// rules from its createTheme block. An artboard is a self-contained file with no shared
// runtime, so the token block is repeated into each one.
//
//   node docs/design/timeline/build.mjs
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const DIR = dirname(fileURLToPath(import.meta.url));

/* ── the app's own tokens (theme.jsx) ─────────────────────────────────────── */
const TOKENS = `
  --bg:#f6f4f1; --panel:#fffdfb; --panel2:#e9e3d8; --bd:#e1dcd5; --bd2:#d8cfbe;
  --ink:#262521; --dim:#4d4a43; --faint:#6e685f;
  --accent:#55697a; --accent2:#6f8a6e;
  --alert:#8a3646; --alert-ink:#7a2f3c; --alert-tint:#f3e6e8; --alert-bd:#e0c6cb;
  --work:#55697a; --info:#8a7a5c; --done:#47654a; --mute:#a09787;
  --sans:'IBM Plex Sans','Segoe UI',system-ui,sans-serif;
  --mono:'IBM Plex Mono','Cascadia Code',Consolas,monospace;`;

/* Buttons are the app's MuiButton, to the pixel: radius 8, no text-transform, weight 600,
   12.5px, contained carries no shadow at rest. Nothing here invents a control. */
const BUTTONS = `
  .btn{border:1px solid var(--bd2);background:var(--panel);border-radius:8px;
    padding:6px 13px;font-family:var(--sans);font-size:12.5px;font-weight:600;color:var(--dim);
    display:inline-flex;align-items:center;gap:7px;line-height:1.5;white-space:nowrap}
  .btn.p{background:var(--accent);border-color:var(--accent);color:#fffdfb}
  .btn.q{border-color:var(--bd);color:var(--faint);font-weight:400}
  .btn.dg{color:var(--alert-ink);border-color:var(--alert-bd);background:transparent}
  .btn.sm{padding:4px 10px;font-size:11.5px}`;

const BASE = `
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:12.5px;line-height:1.5}
  .lbl{font-family:var(--mono);font-size:9.5px;font-weight:600;letter-spacing:.11em;
    text-transform:uppercase;color:var(--accent2);margin:0 0 8px}
  ${BUTTONS}`;

/* ── the state vocabulary ──────────────────────────────────────────────────
   Not chips. A small emoji, its word in quiet type, and the card's LEFT BORDER in the
   state's colour — so state is legible on a one-line row without a coloured pill on every
   card. Oxblood is still spent on nothing but "this is on you". */
const STATE = {
  waving:  { e: "👋", w: "agent waving",  bd: "var(--alert)", ink: "var(--alert-ink)", strong: 1 },
  working: { e: "🤖", w: "agent working", bd: "var(--work)",  ink: "var(--faint)" },
  reply:   { e: "✉️", w: "reply ready",   bd: "var(--alert)", ink: "var(--alert-ink)" },
  fyi:     { e: "👀", w: "fyi",           bd: "var(--bd2)",   ink: "var(--faint)" },
  held:    { e: "🔒", w: "new sender",    bd: "var(--mute)",  ink: "var(--faint)" },
  mine:    { e: "💡", w: "your note",     bd: "var(--info)",  ink: "var(--faint)" },
  done:    { e: "✅", w: "done",          bd: "var(--done)",  ink: "var(--faint)" },
};
const state = (k) => {
  const s = STATE[k];
  return `<span class="st"${s.strong ? ' data-strong="1"' : ""} style="color:${s.ink}">
    <span class="se">${s.e}</span>${s.w}</span>`;
};
const CH = { email: "✉️", teams: "💬", github: "🐙", report: "📊", whatsapp: "📱", self: "💡" };

/* ── the app frame ────────────────────────────────────────────────────────── */
const APP = `
  .app{width:1440px;height:900px;display:flex;flex-direction:column;background:var(--bg);overflow:hidden}

  /* top nav: brand hard left, status hard right, the tabs dead centre of the WINDOW —
     absolute, so a longer brand or a longer status line never nudges them off centre */
  .topnav{position:relative;height:49px;flex-shrink:0;background:var(--panel);
    border-bottom:1px solid var(--bd);display:flex;align-items:center;padding:0 16px}
  .brand{font-weight:700;font-size:13.5px;letter-spacing:-.2px}
  .tabs{position:absolute;left:50%;transform:translateX(-50%);display:flex;gap:2px}
  .tab{padding:5px 12px;border-radius:8px;font-size:12.5px;color:var(--faint)}
  .tab.on{background:var(--panel2);color:var(--ink);font-weight:600}
  .who{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--faint)}

  .split{flex:1;display:grid;grid-template-columns:368px minmax(0,1fr);gap:14px;padding:14px;min-height:0}

  /* ── rail ── */
  .rail{background:var(--panel);border:1px solid var(--bd);border-radius:8px;
    display:flex;flex-direction:column;overflow:hidden}
  .railhead{flex-shrink:0;border-bottom:1px solid var(--bd);padding:10px 12px}
  .railtop{display:flex;align-items:center;gap:10px;margin-bottom:9px}
  .daylabel{font-size:12.5px;font-weight:600;color:var(--ink);flex:1;min-width:0}
  .daylabel span{color:var(--faint);font-weight:400}

  /* filters: ONE segmented control for state, one quiet select for source. Five loose
     pills of two different kinds read as a settings panel, not a filter. */
  .seg{display:inline-flex;border:1px solid var(--bd);border-radius:8px;overflow:hidden;background:var(--panel)}
  .seg div{padding:4px 11px;font-size:11.5px;font-weight:600;color:var(--faint);
    border-right:1px solid var(--bd);display:flex;align-items:center;gap:6px}
  .seg div:last-child{border-right:0}
  .seg div.on{background:var(--panel2);color:var(--ink)}
  .seg .n{font-family:var(--mono);font-size:10px;font-weight:600;background:var(--alert);
    color:#fffdfb;border-radius:99px;padding:0 5px;line-height:15px}
  .filters{display:flex;align-items:center;gap:8px}
  .src{flex:1;min-width:0;display:flex;align-items:center;justify-content:space-between;gap:6px;
    border:1px solid var(--bd);border-radius:8px;padding:4px 9px;font-size:11.5px;color:var(--faint);
    background:var(--panel)}
  .src svg{flex-shrink:0}

  .raillist{flex:1;overflow:hidden;padding:6px 10px 0 4px}
  .daymark{font-family:var(--mono);font-size:9.5px;font-weight:600;letter-spacing:.11em;
    text-transform:uppercase;color:var(--faint);padding:12px 0 6px 66px}

  /* a row is ONE LINE until it is the one you are on. 62px of gutter with 14px of air
     between the clock and the rail, and 8px of air between the rail and the card. */
  .row{display:grid;grid-template-columns:62px 14px minmax(0,1fr);align-items:start;margin-bottom:2px}
  .row .t{font-family:var(--mono);font-size:10px;color:var(--faint);text-align:right;
    padding:6px 14px 0 0;white-space:nowrap;font-variant-numeric:tabular-nums;letter-spacing:-.2px}
  .spine{position:relative;height:100%}
  .spine::before{content:'';position:absolute;left:6px;top:-4px;bottom:-4px;width:1px;background:var(--bd)}
  .spine i{position:absolute;left:2.5px;top:9px;width:7px;height:7px;border-radius:50%;
    box-shadow:0 0 0 3px var(--panel)}
  .card{background:var(--panel);border:1px solid var(--bd);border-left:2px solid var(--bd);
    border-radius:8px;padding:3px 10px 4px;min-width:0;overflow:hidden;margin-left:8px}
  .card.open{border-color:var(--bd2);box-shadow:0 1px 3px rgba(30,50,38,.07);padding-bottom:7px}
  .l1{display:flex;align-items:center;gap:8px;min-width:0;height:22px}
  .ce{font-size:12px;line-height:1;flex-shrink:0;filter:saturate(.85)}
  .from{font-weight:600;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
    max-width:112px;flex-shrink:0}
  .subj{font-size:11.5px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
    flex:1;min-width:0}
  .st{display:inline-flex;align-items:center;gap:4px;font-size:10px;font-weight:600;
    white-space:nowrap;flex-shrink:0}
  .st[data-strong="1"]{font-weight:700}
  .se{font-size:11px;line-height:1;filter:saturate(.9)}
  .l2{font-size:11px;color:var(--faint);padding-left:20px;line-height:1.5;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .l2 b{color:var(--dim);font-weight:600}

  /* ── stage ── */
  .stage{background:var(--panel);border:1px solid var(--bd);border-radius:8px;
    display:flex;flex-direction:column;overflow:hidden}
  .stagehead{flex-shrink:0;padding:12px 18px 10px;display:flex;align-items:center;gap:11px}
  .tqref{font-family:var(--mono);font-size:10.5px;font-weight:600;color:var(--accent);
    background:var(--panel2);border-radius:5px;padding:2px 7px;flex-shrink:0}
  .stitle{flex:1;min-width:0}
  .stitle b{display:block;font-size:15px;font-weight:700;letter-spacing:-.25px;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .stitle small{display:block;font-size:11.5px;color:var(--faint);margin-top:2px}

  .stabs{display:flex;padding:0 18px;border-bottom:1px solid var(--bd);flex-shrink:0;gap:2px}
  .stabs div{padding:8px 14px 9px;font-size:12.5px;font-weight:600;color:var(--faint);
    border-bottom:2px solid transparent;display:flex;align-items:center;gap:7px;margin-bottom:-1px}
  .stabs div.on{color:var(--ink);border-bottom-color:var(--accent)}
  .stabs .bdg{font-size:11px;line-height:1}
  .sbody{flex:1;min-height:0;overflow:hidden;padding:16px 18px}
  .tray{flex-shrink:0;border-top:1px solid var(--bd);background:#fcfaf7;padding:11px 18px 13px}
  .acts{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
  .hint{font-size:11px;color:var(--faint);margin:9px 0 0}`;

/* ── shared stage pieces ──────────────────────────────────────────────────── */
const PANES = `
  .msgbox{border:1px solid var(--bd);border-radius:8px;padding:12px 14px;background:#fcfaf7}
  .msgmeta{display:flex;align-items:baseline;gap:8px;margin-bottom:8px}
  .msgmeta b{font-size:13px}
  .msgmeta span{font-family:var(--mono);font-size:10.5px;color:var(--faint)}
  .msgtext{font-size:13px;line-height:1.65;max-width:66ch;white-space:pre-line}
  .thread{margin-top:12px;border:1px solid var(--bd);border-radius:8px;overflow:hidden}
  .tmsg{display:flex;gap:10px;padding:9px 12px;border-bottom:1px solid var(--bd)}
  .tmsg:last-of-type{border-bottom:0}
  .tmsg.me{background:#fcfaf7}
  .av{width:21px;height:21px;border-radius:50%;flex-shrink:0;display:grid;place-items:center;
    font-family:var(--mono);font-size:9px;font-weight:600;color:#fffdfb;margin-top:1px}
  .tb{min-width:0;flex:1}
  .tb b{font-size:11.5px}
  .tb time{font-family:var(--mono);font-size:10px;color:var(--faint);margin-left:7px}
  .tb p{margin:3px 0 0;font-size:12px;color:var(--dim);line-height:1.55}
  .twhy{font-family:var(--mono);font-size:10px;color:var(--faint);padding:7px 12px;
    background:var(--panel2);border-top:1px solid var(--bd)}

  .roads{display:grid;grid-template-columns:repeat(4,1fr);gap:7px;margin-bottom:12px}
  .road{border:1px solid var(--bd);border-radius:8px;padding:8px 10px;background:#fcfaf7}
  .road.on{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent);background:var(--panel)}
  .road b{display:block;font-size:11.5px;font-weight:600;color:var(--faint)}
  .road.on b{color:var(--ink)}
  .road small{display:block;font-size:10px;color:var(--faint);margin-top:3px;line-height:1.4}
  .why{font-size:13px;border:1px solid var(--bd);border-radius:8px;padding:11px 13px;
    line-height:1.6;max-width:70ch;background:#fcfaf7}
  .why em{font-style:normal;font-family:var(--mono);font-size:10.5px;color:var(--accent);font-weight:600}

  .abar{display:flex;align-items:center;gap:10px;margin-bottom:11px}
  .abar b{font-size:13px}
  .abar .m{font-family:var(--mono);font-size:10.5px;color:var(--faint)}
  .live{width:7px;height:7px;border-radius:50%;background:var(--accent2);flex-shrink:0;
    box-shadow:0 0 0 3px rgba(111,138,110,.18)}
  .console{background:#1e2320;border-radius:8px;padding:11px 13px;font-family:var(--mono);
    font-size:11px;line-height:1.75;color:#c9d4c8;overflow:hidden}
  .cd{color:#7d8a7c} .ch{color:#a8c6d8} .co{color:#9dc49b}
  .files{display:flex;gap:6px;flex-wrap:wrap;margin-top:11px}
  .file{font-family:var(--mono);font-size:10px;background:var(--panel2);border-radius:5px;
    padding:3px 8px;color:var(--dim)}
  .askbox{border:1px solid var(--alert-bd);border-left:2px solid var(--alert);border-radius:8px;
    padding:12px 14px;background:#fcfaf7}
  .askbox .lbl{color:var(--alert-ink)}
  .askbox p{margin:0 0 11px;font-size:13px;line-height:1.6;max-width:62ch}
  .draft{border:1px solid var(--bd);border-radius:8px;padding:12px 14px;font-size:13px;
    line-height:1.65;max-width:66ch;white-space:pre-line;background:#fcfaf7}
  .pendline{display:flex;align-items:center;gap:9px;margin-bottom:11px;font-size:12px;color:var(--faint)}`;

const HEAD = `<div class="stagehead">
  <span class="tqref">TQ-0259</span>
  <div class="stitle"><b>Q3 census numbers for the board pack</b>
    <small>Marcus Bell · email · today 8:57 AM · closed itself 9:10 AM</small></div>
  ${state("reply")}
</div>`;

const stabs = (on) => `<div class="stabs">
  <div class="${on === "msg" ? "on" : ""}">Message</div>
  <div class="${on === "why" ? "on" : ""}">Triage</div>
  <div class="${on === "agent" ? "on" : ""}"><span class="bdg">🤖</span>Agent</div>
  <div class="${on === "reply" ? "on" : ""}"><span class="bdg">✉️</span>Reply</div>
</div>`;

const P_MSG = `<div class="msgbox">
    <div class="msgmeta"><b>Marcus Bell</b><span>today 8:57 AM · outlook</span></div>
    <div class="msgtext">Morning — board pack is due Thursday and I'm short the Q3 census by facility. Do you have those, or do I need to pull them myself?</div>
  </div>
  <div class="thread">
    <div class="tmsg"><span class="av" style="background:#55697a">MB</span>
      <div class="tb"><b>Marcus Bell</b><time>Aug 24, 2:10 PM</time>
      <p>Starting the board pack this week — I'll shout if I'm missing anything.</p></div></div>
    <div class="tmsg me"><span class="av" style="background:#6f8a6e">You</span>
      <div class="tb"><b>You</b><time>Aug 24, 2:22 PM</time><p>Sounds good.</p></div></div>
    <div class="twhy">3 messages · matched by conversation id</div>
  </div>`;

const P_WHY = `<div class="roads">
    <div class="road"><b>fyi</b><small>nothing to do</small></div>
    <div class="road"><b>reply</b><small>a sentence settles it</small></div>
    <div class="road on"><b>coding</b><small>an agent on a keyboard</small></div>
    <div class="road"><b>general</b><small>only you can do it</small></div>
  </div>
  <div class="why"><em>triage:</em> A number to look up in a system we are already connected to. A capable person could do this from a keyboard, so it went to the coding agent rather than onto your own list.</div>`;

const P_AGENT = `<div class="abar"><b>claude finished and closed itself</b><span class="m">8:59 → 9:10 AM · 11 min</span></div>
  <div class="console">
    <span class="cd">›</span> Bash <span class="ch">census --by-facility --q3</span><br>
    <span class="co">&nbsp;&nbsp;14 facilities, Jul–Sep → census-q3.xlsx</span><br>
    <span class="cd">›</span> Read <span class="ch">reports/census-q3.xlsx</span><br>
    <span class="cd">&nbsp;&nbsp;Site 3 −4.2, Site 7 +5.1 — both outside the usual band</span><br>
    <span class="cd">›</span> Bash <span class="ch">taskuary --done "pulled Q3 census for all 14 sites"</span>
  </div>
  <div class="files"><span class="file">reports/census-q3.xlsx</span></div>`;

const P_REPLY = `<div class="pendline">${state("reply")}<span>Written by the agent from what it found. Nothing has been sent.</span></div>
  <div class="draft">Marcus — attached, Q3 census by facility for all 14 sites (Jul–Sep). Site 3 and Site 7 both moved more than four points, so I flagged those two rows. Shout if the board pack wants the monthly split instead of the quarter.</div>`;

const TRAYS = {
  msg: `<div class="acts"><div class="btn p">Send it to an agent</div><div class="btn">Reply to this</div>
        <div class="btn q">Dismiss just this one</div><div class="btn dg">Nothing to do here</div></div>
        <p class="hint">Dismiss hides this row and teaches nothing. “Nothing to do here” is a verdict — the next message like it is filed automatically.</p>`,
  why: `<div class="acts"><div class="btn">It's a reply, not a task</div><div class="btn">It's for me, not an agent</div>
        <div class="btn">It's just information</div><div class="btn q">Tell triage why</div></div>
        <p class="hint">Correcting the verdict here is what teaches it — the reason you type lands in TRIAGE.md, not in a one-off rule about this sender.</p>`,
  agent: `<div class="acts"><div class="btn p">Open the session</div><div class="btn">Tell it something</div>
        <div class="btn">Read the transcript</div><div class="btn dg">Reopen and rerun</div></div>
        <p class="hint">The session closed itself when it said it was done. Reopening starts a fresh one with the handover note.</p>`,
  reply: `<div class="acts"><div class="btn p">Send as me</div><div class="btn">Edit first</div>
        <div class="btn">Draft it again</div><div class="btn q">No reply needed</div></div>
        <p class="hint">Nothing leaves until you press Send — the agent wrote it, you own it.</p>`,
};

/* ── the rail ─────────────────────────────────────────────────────────────── */
const DOT = { waving: "#8a3646", working: "#55697a", reply: "#8a3646",
              fyi: "#8a7a5c", held: "#a09787", mine: "#8a7a5c", done: "#47654a" };

const ROWS = [
  { day: "Today", t: "9:42 AM", ch: "teams", from: "Dana Whitfield", s: "working",
    subj: "resident refund still on the ledger", blurb: "<b>TQ-0261</b> · claude, 6 min in · taskuary/intacct.py" },
  { day: "Today", t: "9:31 AM", ch: "self", from: "You", s: "mine",
    subj: "chase the Payworth AP replacement Tuesday", blurb: "<b>your own note</b> · nothing is working it, and nothing will" },
  { day: "Today", t: "9:18 AM", ch: "github", from: "taskuary/taskuary", s: "waving",
    subj: "CI failed on master — test_terminal", blurb: "<b>TQ-0260</b> · it asked you something 4 minutes ago" },
  { day: "Today", t: "9:04 AM", ch: "self", from: "Board", s: "working",
    subj: "Migrate the census export off the old view", blurb: "<b>TQ-0262</b> · you started this from the Board · codex, 38 min in", open: true,
    openState: "working" },
  { day: "Today", t: "8:57 AM", ch: "email", from: "Marcus Bell", s: "reply",
    subj: "Q3 census for the board pack", blurb: "<b>TQ-0259</b> · agent closed itself · reply drafted 9:10 AM", sel: true },
  { day: "Today", t: "8:40 AM", ch: "report", from: "Intacct — bills", s: "fyi",
    subj: "14 bills posted, 2 over threshold", blurb: "watch-for line matched nothing" },
  { day: "Today", t: "8:12 AM", ch: "email", from: "ap@vendorco.io", s: "held",
    subj: "Invoice 4471 — payment details changed", blurb: "first mail from this address · nothing started" },
  { day: "Yesterday", t: "6:04 PM", ch: "whatsapp", from: "Priya Raman", s: "done",
    subj: "Site 7 wifi dropping east wing", blurb: "<b>TQ-0257</b> · closed · reply sent 6:39 PM" },
];

const caret = `<svg width="11" height="11" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6l4 4 4-4"/></svg>`;
const pencil = `<svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M11.2 2.3 13.7 4.8 5.5 13H3v-2.5z"/></svg>`;

const railRows = () => {
  let out = "", last = "";
  for (const r of ROWS) {
    if (r.day !== last) {
      out += `<div class="daymark">${r.day === "Today" ? "Today · Monday, Sep 1" : "Yesterday · Sunday, Aug 31"}</div>`;
      last = r.day;
    }
    const open = r.sel || r.open;
    out += `<div class="row">
      <div class="t">${r.t}</div>
      <div class="spine"><i style="background:${DOT[r.s]}"></i></div>
      <div class="card${open ? " open" : ""}" style="border-left-color:${STATE[r.s].bd}">
        <div class="l1"><span class="ce">${CH[r.ch]}</span><span class="from">${r.from}</span>
          <span class="subj">${r.subj}</span>${state(r.s)}</div>
        ${open ? `<div class="l2">${r.blurb}</div>` : ""}
      </div></div>`;
  }
  return out;
};

const rail = () => `<div class="rail">
  <div class="railhead">
    <div class="railtop">
      <div class="daylabel">Today <span>· Monday, Sep 1</span></div>
      <div class="btn p sm">${pencil}New</div>
    </div>
    <div class="filters">
      <div class="seg"><div class="on">Everything</div><div>Needs me<span class="n">3</span></div></div>
      <div class="src"><span>All sources</span>${caret}</div>
    </div>
  </div>
  <div class="raillist">${railRows()}</div>
</div>`;

const topnav = `<div class="topnav">
  <span class="brand">Taskuary</span>
  <div class="tabs"><span class="tab on">Timeline</span><span class="tab">Board</span><span class="tab">Tasks</span>
    <span class="tab">Wall</span><span class="tab">Reports</span><span class="tab">Connectors</span></div>
  <span class="who">4 sessions live · synced 3 min ago</span>
</div>`;

/* ── file shell ───────────────────────────────────────────────────────────── */
const FONTS = `<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">`;
const page = (css, body) => `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  ${FONTS}
  <style>
  :root{${TOKENS}}
  ${BASE}
  a{color:var(--accent)} a:hover{color:var(--ink)}
  ${css}
  </style>
</helmet>
${body}
</x-dc>
</body>
</html>
`;

/* ── Main: the whole page, Reply tab open ─────────────────────────────────── */
writeFileSync(join(DIR, "Main.dc.html"), page(`${APP}${PANES}`,
`<div class="app">
  ${topnav}
  <div class="split">
    ${rail()}
    <div class="stage">
      ${HEAD}
      ${stabs("reply")}
      <div class="sbody">${P_REPLY}</div>
      <div class="tray">${TRAYS.reply}</div>
    </div>
  </div>
</div>`));

/* ── the four tabs, side by side ──────────────────────────────────────────── */
const paneCard = (on, title, body, tray) => `<div class="pane">
  <div class="ptitle">${title}</div>
  <div class="stage">
    ${HEAD}
    ${stabs(on)}
    <div class="sbody">${body}</div>
    <div class="tray">${tray}</div>
  </div>
</div>`;

writeFileSync(join(DIR, "Tabs.dc.html"), page(`${APP}${PANES}
  .wrap{width:1500px;padding:26px 28px;background:var(--bg)}
  h2{font-size:18px;font-weight:700;letter-spacing:-.3px;margin:0 0 4px}
  .sub{color:var(--dim);font-size:13px;margin:0 0 22px;max-width:76ch;line-height:1.6}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:22px}
  .pane .stage{height:430px}
  .ptitle{font-family:var(--mono);font-size:9.5px;font-weight:600;letter-spacing:.11em;
    text-transform:uppercase;color:var(--faint);margin-bottom:8px}`,
`<div class="wrap">
  <h2>One task, four tabs</h2>
  <p class="sub">Each tab carries the buttons that belong to it, so the tray under the stage is
    always short and always about what you are looking at. The badge on a tab is the only thing
    that pulls you across: 🤖 while an agent is on it, 👋 when it has stopped and asked you
    something, ✉️ when a reply is waiting to go.</p>
  <div class="grid">
    ${paneCard("msg", "Message — what actually arrived", P_MSG, TRAYS.msg)}
    ${paneCard("why", "Triage — which road it took, and why", P_WHY, TRAYS.why)}
    ${paneCard("agent", "Agent — what it did, live or finished", P_AGENT, TRAYS.agent)}
    ${paneCard("reply", "Reply — the draft, waiting on you", P_REPLY, TRAYS.reply)}
  </div>
</div>`));

/* ── the rail on its own, at rest and expanded ────────────────────────────── */
const LEGEND = [
  ["waving", "The agent stopped and asked you something. The card's left edge goes oxblood — the only colour on this screen that ever shouts."],
  ["working", "A session is open on it right now. Started by triage, or by you from the Board — either way it shows here, at the minute it started."],
  ["reply", "The agent finished, closed itself, and drafted the answer. One click sends it."],
  ["fyi", "A report or a notice. Read it or don't; nothing was started and nothing is owed."],
  ["held", "First message from this address. Triaged and shown, but no agent — an unvetted prompt does not get to open a terminal."],
  ["mine", "A note you wrote yourself: a reminder, an idea, something to come back to. Nothing is working it, and nothing will."],
  ["done", "Closed out, reply sent. It stays for the record and fades with age."],
];
writeFileSync(join(DIR, "Rail.dc.html"), page(`${APP}
  .wrap{width:1080px;padding:26px 28px;background:var(--bg);display:grid;
    grid-template-columns:380px minmax(0,1fr);gap:28px;align-items:start}
  .rail{height:600px}
  h2{font-size:18px;font-weight:700;letter-spacing:-.3px;margin:0 0 4px}
  .sub{color:var(--dim);font-size:13px;margin:0 0 18px;line-height:1.6}
  .leg{display:flex;flex-direction:column;gap:9px}
  .li{display:grid;grid-template-columns:118px minmax(0,1fr);gap:14px;align-items:start;
    border:1px solid var(--bd);border-left:2px solid var(--bd);border-radius:8px;
    padding:10px 13px;background:var(--panel)}
  .li p{margin:0;font-size:12px;color:var(--dim);line-height:1.55}
  .foot{margin-top:16px;font-size:12.5px;color:var(--dim);line-height:1.65}
  .foot b{color:var(--ink);font-weight:600}`,
`<div class="wrap">
  <div>${rail()}</div>
  <div>
    <h2>The rail</h2>
    <p class="sub">One line per item at rest — the clock, the channel, who, what, and where it
      stands. Hovering or clicking a row unfolds a second line and opens it on the stage; two
      rows are unfolded here so you can see both. Nothing else moves.</p>
    <div class="leg">
      ${LEGEND.map(([k, why]) => `<div class="li" style="border-left-color:${STATE[k].bd}">
        <div>${state(k)}</div><p>${why}</p></div>`).join("")}
    </div>
    <p class="foot"><b>Why words and not chips.</b> A coloured pill on every row makes the whole
      column loud and the one row that matters invisible. A small mark, its word in quiet type,
      and the card's left edge in the state's colour say the same thing and leave the paper alone.</p>
  </div>
</div>`));

/* ── the New sheet ────────────────────────────────────────────────────────── */
writeFileSync(join(DIR, "New.dc.html"), page(`
  .wrap{width:700px;padding:26px 28px;background:var(--bg)}
  h2{font-size:18px;font-weight:700;letter-spacing:-.3px;margin:0 0 4px}
  .sub{color:var(--dim);font-size:13px;margin:0 0 20px;max-width:62ch;line-height:1.6}
  .sheet{background:var(--panel);border:1px solid var(--bd);border-radius:16px;overflow:hidden;
    box-shadow:0 24px 60px rgba(30,50,38,.18)}
  .sheet header{padding:15px 18px 4px}
  .sheet header b{font-size:15px;font-weight:700}
  .kinds{display:flex;gap:2px;padding:10px 18px 0;border-bottom:1px solid var(--bd)}
  .kinds div{padding:8px 13px 9px;font-size:12.5px;font-weight:600;color:var(--faint);
    border-bottom:2px solid transparent;margin-bottom:-1px;display:flex;align-items:center;gap:7px}
  .kinds div.on{color:var(--ink);border-bottom-color:var(--accent)}
  .body{padding:16px 18px;display:flex;flex-direction:column;gap:15px}
  .field label{display:block;font-family:var(--mono);font-size:9.5px;font-weight:600;
    letter-spacing:.11em;text-transform:uppercase;color:var(--accent2);margin-bottom:7px}
  .chans{display:flex;gap:7px}
  .chan{border:1px solid var(--bd);border-radius:8px;padding:6px 12px;font-size:12.5px;
    font-weight:600;color:var(--faint);display:flex;align-items:center;gap:7px;background:var(--panel)}
  .chan.on{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent);color:var(--ink)}
  .inp{border:1px solid var(--bd);border-radius:8px;padding:9px 12px;font-size:13px;
    background:#fcfaf7;color:var(--ink);line-height:1.6}
  .inp.ph{color:var(--faint)}
  .forks{display:grid;grid-template-columns:1fr 1fr;gap:9px}
  .fork{border:1px solid var(--bd);border-radius:8px;padding:11px 13px;background:#fcfaf7}
  .fork.on{border-color:var(--accent);box-shadow:inset 0 0 0 1px var(--accent);background:var(--panel)}
  .fork b{display:block;font-size:12.5px;margin-bottom:4px}
  .fork small{display:block;font-size:11px;color:var(--faint);line-height:1.5}
  .sheet footer{padding:12px 18px;border-top:1px solid var(--bd);background:#fcfaf7;
    display:flex;gap:8px;justify-content:flex-end}
  .foot{margin-top:18px;font-size:12.5px;color:var(--dim);line-height:1.65;max-width:64ch}
  .foot b{color:var(--ink);font-weight:600}`,
`<div class="wrap">
  <h2>＋ New</h2>
  <p class="sub">One button on the rail, four things it can start — and all four land on the
    timeline at the minute you pressed it.</p>
  <div class="sheet">
    <header><b>What are we starting?</b></header>
    <div class="kinds">
      <div class="on"><span>✉️</span>Send something</div>
      <div><span>🤖</span>Give an agent a job</div>
      <div><span>💡</span>Note to self</div>
      <div><span>📊</span>Ask for a report</div>
    </div>
    <div class="body">
      <div class="field"><label>Channel</label>
        <div class="chans"><div class="chan on"><span>✉️</span>Email</div>
          <div class="chan"><span>💬</span>Teams</div><div class="chan"><span>📱</span>WhatsApp</div></div>
      </div>
      <div class="field"><label>To</label><div class="inp">Marcus Bell &lt;m.bell@…&gt;</div></div>
      <div class="field"><label>What's this about</label>
        <div class="inp">the census numbers he asked for, plus why Site 7 moved</div></div>
      <div class="field"><label>And then</label>
        <div class="forks">
          <div class="fork on"><b>Draft it and show me</b>
            <small>The AI writes it in your voice from the thread. It lands on the timeline as ✉️ reply ready.</small></div>
          <div class="fork"><b>Make it a task first</b>
            <small>An agent researches it, comes back with the answer, then drafts the message — the same lifecycle as anything inbound.</small></div>
        </div>
      </div>
    </div>
    <footer><div class="btn q">Cancel</div><div class="btn p">Draft it</div></footer>
  </div>
  <p class="foot"><b>Note to self</b> is the one that has never existed: a reminder or an idea,
    filed as your own 💡 row with a date to come back on. No agent, no reply, no verdict — it is
    on the timeline because that is where you look, and it is the only kind of row that is
    yours rather than something that happened to you.</p>
</div>`));

/* ── lifecycle ────────────────────────────────────────────────────────────── */
const STEPS = [
  ["Arrives", "mail · chat · report · repo · ＋ New", "the row appears at the minute it happened, before anything is decided"],
  ["Triaged", "fyi / reply / coding / general", "one verdict, one sentence of why, on the Triage tab"],
  ["🤖 Working", "a live session, one per task", "started by triage or by you, from anywhere in the app"],
  ["👋 Waving", "it asked a question", "the rail's left edge goes oxblood; nothing else does"],
  ["✉️ Reply ready", "the agent closed itself", "it wrapped up, filed its report and drafted the answer"],
  ["✅ Sent", "you approved it", "the thread, the report and the transcript stay on the task"],
];
writeFileSync(join(DIR, "Lifecycle.dc.html"), page(`
  .wrap{width:1240px;padding:26px 28px;background:var(--bg)}
  h2{font-size:18px;font-weight:700;letter-spacing:-.3px;margin:0 0 4px}
  .sub{color:var(--dim);font-size:13px;margin:0 0 22px;max-width:80ch;line-height:1.6}
  .flow{display:grid;grid-template-columns:repeat(6,1fr);gap:11px}
  .step{background:var(--panel);border:1px solid var(--bd);border-radius:8px;padding:13px 14px;
    display:flex;flex-direction:column;gap:5px;position:relative}
  .step::after{content:'';position:absolute;right:-12px;top:50%;width:13px;height:1px;background:var(--bd2)}
  .step:last-child::after{display:none}
  .step b{font-size:13px;font-weight:600}
  .step .k{font-family:var(--mono);font-size:9.5px;color:var(--faint)}
  .step p{margin:3px 0 0;font-size:11.5px;color:var(--dim);line-height:1.55}
  .foot{margin-top:20px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:13px}
  .fc{background:var(--panel);border:1px solid var(--bd);border-radius:8px;padding:13px 15px}
  .fc b{display:block;font-size:13px;font-weight:600;margin-bottom:5px}
  .fc p{margin:0;font-size:12px;color:var(--dim);line-height:1.6}`,
`<div class="wrap">
  <h2>One lifecycle, wherever the work came from</h2>
  <p class="sub">Mail, chat, a repository, a scheduled report, or the ＋ New button — the same
    six steps, the same row on the same rail.</p>
  <div class="flow">
    ${STEPS.map(([b, k, p]) => `<div class="step"><b>${b}</b><span class="k">${k}</span><p>${p}</p></div>`).join("")}
  </div>
  <div class="foot">
    <div class="fc"><b>🤖 Work started anywhere shows here</b>
      <p>A task you start from the Board or the Tasks tab gets a timeline row at the minute the
        session opened — with 👋 the moment it stops and needs you. The timeline stops being an
        inbox and becomes the record of the day.</p></div>
    <div class="fc"><b>✉️ The agent closes itself</b>
      <p>Step five used to need you to click Done. The CLI's own stop hook decides now: an agent
        that says it is finished wraps up, files its report and drafts the reply — the row arrives
        already saying reply ready.</p></div>
    <div class="fc"><b>🔒 A stranger's first message waits</b>
      <p>Before step three, a sender nobody here has written to is held. Triaged and shown, but
        no session — one button releases it, and that address is never asked about again.</p></div>
  </div>
</div>`));

/* ── canvas ───────────────────────────────────────────────────────────────── */
writeFileSync(join(DIR, "canvas.json"), JSON.stringify({
  pages: [{ id: "page-1", name: "The page" }, { id: "page-2", name: "Parts" }],
  artboards: [
    { file: "Main.dc.html", page: "page-1", x: 0, y: 0, w: 1440, h: 900, title: "Timeline" },
    { file: "Tabs.dc.html", page: "page-1", x: 1560, y: 0, w: 1500, h: 1080, title: "The four tabs" },
    { file: "Rail.dc.html",      page: "page-2", x: 0,    y: 0,   w: 1080, h: 660 },
    { file: "New.dc.html",       page: "page-2", x: 1200, y: 0,   w: 700,  h: 880 },
    { file: "Lifecycle.dc.html", page: "page-2", x: 0,    y: 1010, w: 1240, h: 460 },
  ],
  annotations: [
    { id: "changes", x: 0, y: -230, w: 460,
      text: "Second pass.\n· Tabs on the stage — Message / Triage / Agent / Reply, each carrying only its own buttons.\n· Rail rows are one line until hovered or clicked.\n· No sync button; the nav tabs are centred on the window.\n· State is an emoji, its word, and the card's left edge — no coloured pills.\n· Buttons are the app's real MuiButton: 8px radius, 12.5px, weight 600." },
    { id: "new-kinds", x: 1560, y: -230, w: 420,
      text: "＋ New now starts four things, not one: send something, give an agent a job, leave yourself a 💡 note, or ask for a report. All four appear on the rail at the minute you pressed it." },
  ],
  launch: { view: "canvas", page: "page-1" },
}, null, 2));

console.log("wrote 5 artboards + canvas.json");
