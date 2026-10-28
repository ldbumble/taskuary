// Does the walk ever leave the owner alone? Clicks through a fresh world, presses EVERY button the one list names, makes things
// fail on purpose, and fails on a dead end.
//
// Tests read the source; a dead end only shows on the screen. The 2026-10-17 click-through found five that every test passed, and
// then this walk itself went hollow: it pressed "Send", "End" and "Done" by their words - two of them no longer existed - with the
// demo's refusals switched off, so no send, close, fix or cancel was ever walked (the re-audit, 2026-10-18). Now every press is
// chosen by its VERB from buttons.js, a button nobody pressed fails the walk (COVER), and failures are forced at the boundary - the
// mailbox, the coding tool, the AI (taskuary/faults.py) - never by turning a refusal off. Four passes:
//
//   walk      the demo, refusals ON: Next through the day, doing what each card's first button invites
//   sweep     the demo, refusals ON: every button every row shows, in its row and its More menus, pressed once
//   faults    a seeded world with a mocked mailbox: each failure failures.classify knows, forced, then its way out pressed
//   cards     a row press that must run at once, with no card to confirm it; a task folded by its X, then opened again from its line and the rail
//   links     the demo: links to a connector and a setting, from a fresh page and over their open page, Back, and Next's address
//   search    the demo: Enter typed over an earlier answer and before any, the count past the cap, a connection by name, a phone
//   table     the demo, its brain linking a task it is asked to show: a task opened by the rail, Next, the Board, a deep link, search,
//             a typed ref, a link in a reply and the walk's end chip - each, and each reloaded
//
// The rules, checked at every step:
//   DARK      the bar is dark only when the Advisor spoke, and then on one button (the owner, 2026-10-17: "keep it ai") - save a running
//             agent's own Stop and save, which the row darkens itself (the owner, 2026-10-20)
//   SEEN      the card on the table shows more than its header
//   FIX       an error on screen has a way out on the row - a verb that is not Next
//   RECEIPT   an item that leaves the rail is named in the chat - its card, folded with the badge of what was pressed
//   OPENS     a chip that says "Open TQ-x" puts TQ-x on the table
//   WORDS     no developer word and no raw error on the card, the row, the Advisor's line or an error (words.json's jargon)
//   NAMES     every button on the row and in its menus is a named button - a label in buttons.json
//   CALLS     no /api request fails while the walk runs - a refusal the demo says AS the demo is not a failure
//   NOTHING   a press that changes nothing on the screen
//   COVER     a button on the list that the walk never pressed and WALK_SKIP does not explain
//   WAYOUT    a forced failure whose screen has no button from the list that gets past it, or whose way out does nothing
//   LIVE      a cancelled or failed proposal card that still offers its buttons
//   FOLD      a task folded by its X that its folded line or its rail row cannot open again
//   UNDO      a Take it back or Undo anywhere - the row, the chat, the card - or a line saying "Undo:" or "confirm below" (the owner,
//             2026-10-19: "no take it back button. hate that" - a wrong Mark done is put right with Reopen task)
//   ONCE      one act, two receipt lines: Remind me's receipt printed by the page and again by the server (2026-10-19 UI walk) - and two
//             rail rows picked in turn leave every line once, not a "Show me" line per pick (verify, 2026-10-19)
//   STILL     the Advisor's line landing moved a button on the row - the advice only tints (2026-10-19: Send pushed in, Attach into ▾)
//   STRIP     the Advisor's strip under the item on the table says nothing AND nothing is lit - an obvious move is an empty strip
//             with its one button lit (the owner, 2026-10-23), never an empty strip over an unlit row - save a decision that lights
//             nothing on purpose ([data-tq-unlit]: an agent asking is answered in its pane)
//   REREAD    a press on the row and no fresh read of the advice after it (2026-10-19: "waiting on you" stood over a sent reply)
//   LIT       the Advisor's lit button is off the screen or covered, a screen away from the line that names it
//   AGAIN     a lit press refused or failed, and the line read again still lights it (2026-10-19: Send lit over "Not sent" and the demo's no)
//   PLACE     a link's card or setting is not on the screen - followed on a fresh page, and again with its page already open (the
//             2026-10-19 UI walk: #connector= did nothing over an open Connections, a search hit opened its group at the top)
//   BACK      the browser's Back after two opens is not the first, or leaves the app (it left it: no step was ever written)
//   ADDRESS   the address names a task the table has moved past - a reload would open it again
//   RING      a task opened by any road and not the one rail row ringed for it, or the box not asking about it - and a reload that
//             puts another on the table (the 2026-10-19 UI walk, G1: a Board, link or typed open left the rail ringing the item before)
//   SWAP      a frame that shows a wrong state on the way to the next one (the 2026-10-19 UI walk, G8): after a press, the rail's ring on one
//             item and the task view on another, a task view standing empty (its task not drawn) past a second, two rail rows drawn
//             over each other that are not trading places, or a goal's "no steps yet" over steps that then arrive - and a rail heading
//             lanes.json does not name, or a working agent's ring under any section but Tasks (or For later, put away with Remind me):
//             a task does not move between sections when its agent starts, asks or stops (the owner, 2026-10-21)
//   SEARCH    Enter opened another query's hit, or nothing; focus left elsewhere than what opened; "N of N" over a cut list; a
//             connection its name did not find or open; no search at a phone's width (the 2026-10-19 UI walk, G9)
//   OVER      a New ... entry that asks in a dialog drew another document under it, or its Cancel left one open (2026-10-19 UI walk:
//             + New playbook put SOUL.md under its dialog, and Cancel left the owner editing it)
//   BASED     an idea's "Based on <name>'s message" (or a #msg= link) left anything but that message's own card on the table, named
//             the Advisor for the person, or drew the old row panel ("CLEAR FROM TIMELINE", "Talk it through", "undefined in chat")
//   HEAD      the task view's header takes more than one row - at 1366 on every road a task opens by, and at 390 (2026-10-21)
//   PHONE     at 390px the page scrolls sideways (a tooltip ran 200px off it), or a word stands a letter a line (the FYI subjects)
//   STOPSAVE  Stop and save on a live session (a plain shell, a slow brain - stopsave) drew no pending Close out within 500 ms, or the
//             draft did not replace that block in the same card (the owner, 2026-10-21: "it looks frozen")
//
//   node website/deadend_check.mjs [--port 7799] [--keep] [--no-build] [--json] [--throttle 4] [--only walk,sweep,faults,cards,links,search,table,based,stopsave]
//
// It builds the page from THIS checkout's source into a scratch folder (--no-build: the committed bundle) and starts its own servers
// on throwaway homes (never the owner's 7787).
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:net";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { launch } from "./browser.mjs";
import { JARGON_RES } from "./src/words.js";
import { VERBS, ALL_LABELS, CHOICES, label, verbOfRow, choice } from "./src/buttons.js";
import { LEVEL_ORDER as SECTION_KEYS } from "./src/lanes.js";

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d; };
// no --port: every server takes a port the system says is free - two walks on one box (or a walk beside the browser suite) collided
// on the fixed 7799..7802 and one of them "never came up" (2026-10-18). --port N pins N, N+1, ... N+5 (stopsave), as before.
const throttle = Number(arg("--throttle", 1));
const fixed = process.argv.includes("--port"), port = Number(arg("--port", 7799)), keep = process.argv.includes("--keep"), build = !process.argv.includes("--no-build");
const only = new Set(String(arg("--only", "walk,sweep,faults,cards,links,search,table,based,stopsave")).split(","));
const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

// THE BUTTONS THE WALK CANNOT PRESS, and why - every other verb (and each of its states) is pressed at least once, or COVER says so.
// A new button with neither fails the walk: that is what keeps it from going hollow again.
const WALK_SKIP = {
  "walk": "the end of the walk's own button: pressing it starts the walk the check just finished - the walk step checks it is on the end row",
  "unsubscribe": "the demo's mail carries no List-Unsubscribe header, and a press would post to a real list",
  "sync_now": "fetches mail - the demo refuses ingest and the faults world has no mailbox",
  "sync_now:unknown": "as Sync now: no mailbox to check",
  "fix:card": "New report's 'Open the card' shows only when its source is not connected; the walk does not open New report",
  "strong_again": "offered only on a failed or unsure agent run when a brain has a strong model - the demo's cards carry none, and its agents are recordings that start nothing new",
  "pick_repo": "offered only when triage could not tell the repository - the demo world names one for every coding task",
  "approve:action": "an agent's proposal: the demo's agents are recordings and never propose an act",
  "redraft": "redrafting asks the AI - the demo's canned brain writes no drafts, and the faults world has no AI",
  "redraft:none": "as Redraft: writing a draft is the AI's",
  "not_ours_sender": "From now on: the chip under Not ours' receipt (proposalCard.followUps), not a row of its own",
  "block_sender": "a rule in Settings: the card's third answer, now a page of its own, not a chip under Not ours",
  "not_ours_kind": "No more ideas like this: the chip under an idea's Not ours receipt (proposalCard.followUps)",
  "coding_agent": "an answer inside Send to agent's question; the faults pass starts one through it",
  "stop_agent": "Stop and save ends a live session - the demo's agents are recordings with no session to save",
  "answer_agent": "no button on any row (the owner, 2026-10-20: \"we don't need that button\") - an agent's question is answered in its own pane",
  "continue": "Continue resumes a stopped agent's session - none in the demo world has one",
  "make_report": "offered only on a workflow whose steps all read - every demo workflow acts, and describing a new one asks the AI, which neither world has",
  "rerun": "runs a report - the demo refuses it (\"running reports are switched off\"), the faults world has no report source",
  "chase": "shows only on a person who has gone quiet past their usual time - the seeded world is hours old",
  "let_go": "as Chase them: a slipped follow-up's answer",
  "elsewhere": "as Chase them: a slipped follow-up's answer",
  "test_connection": "on a connection's own card, not an item's row - the connection cards are walked by the browser setup tests",
  "next:batch": "shows only on a run of notices read together - the demo's fyi fold away under 'more fyi' instead",
  "next:read": "the badge a Next press leaves on a report, a dashboard or an fyi it walked past (✓ Read) - a word on the card, not a button; the press is Next's own",
  "split": "opens the split-or-merge drawer; its own press is walked, the reshape itself is the task tests'",
  "review_changes": "opens the agent's diff drawer - walked when an agent row carries it",
  "run_another": "starts a second agent - the demo refuses starts and the faults pass starts one through Send to agent",
  "prepare": "starts a research agent on a meeting (the owner, 2026-10-25) - the demo refuses every start; its road is tests/test_meeting_prepare.py",
  "decline_invite": "folded behind the meeting row's ▾ since Prepare joined the row (2026-10-25); Accept, walked, takes the same calendar road (tests/test_calendar_write.py)",
  "retriage": "asks the AI to sort it again - no AI in either world",
  "share": "Email a summary - one of Share's ways since 2026-10-23, no row button of its own; mailing someone is refused in the demo",
  "share_result": "opens the result's Share menu - the demo shares nothing (sharing.ways greys every way), and no demo report or Result is shared by the walk",
  "try_again": "repeats a failed press - pressed in the faults pass only where the failure says a retry could work",
  "walk_here": "brings the walk back from a phone chat - neither world hands the walk to one",
  "new_task": "the idle chips' New task opens the New sheet - walked by the browser New tests",
  "new_task:fix": "offered by the Advisor on a failure nothing fixes - the walk has no AI to offer it",
  "report_bug": "opens the bug report draft - the faults pass checks it is offered, never sends one",
  "approve:unknown": "Send anyway on a send nobody can confirm - the faults pass checks it is offered",
  "approve:check": "Check delivery on a send nobody can confirm - the faults pass checks it is offered",
  "trust_start": "a chip only under a start refused for a stranger on a tool with no reviewer - the demo world never refuses one (tests/test_*stranger* press it)",
  "pick_repo:set": "shows once a task names its folder - the faults pass takes a task that names none, to press Choose where the code is",
  "split:split": "the plain split's own name for the same drawer Split or merge opens - the drawer's press is walked as split",
  "attach:more": "shows once a file is attached - the walk attaches none: the file picker is the system's own window",
  "copy": "under a draft its channel cannot send (Teams) - neither world drafts one; test/unsendableReply.test.mjs holds it to copy and close nothing",
  "copy:done": "as Copy: the badge its own press leaves",
};

// --cover a.json,b.json: COVER over the presses of a walk run in parts (CI runs its passes as four jobs, 2026-10-20) - no browser,
// the same rule as below over every part's `pressed`
if (process.argv.includes("--cover")) {
  const pressedAll = new Set(arg("--cover", "").split(",").filter(Boolean).flatMap((f) => JSON.parse(readFileSync(f, "utf8")).pressed || []));
  const miss = Object.entries(VERBS).flatMap(([v, d]) => [v, ...Object.keys(d.states || {}).map((s) => `${v}:${s}`)]).filter((k) => !pressedAll.has(k) && !WALK_SKIP[k]);
  const found = miss.map((k) => `COVER   ${k}: "${label(...k.split(":"))}" was never pressed, and WALK_SKIP gives no reason`);
  console.log(JSON.stringify({ counts: found.length ? { COVER: found.length } : {}, found })); process.exit(0);
}

// words the owner should never have to read: the one list the server's sentences are held to (taskuary/words.json) - and what only a
// crash or a raw provider error leaves on a screen, which is no word anyone chose
const JARGON = [...JARGON_RES, /\bnull\b/, /\bundefined\b/, /Traceback/, /\b[45]\d\d(?= \()/, /\[Errno \d+\]/, /\bb'[^']{3,}'/, /\(\d{3}, b['"]/,
  /\w+Error: /];
const NAMED = new Set(ALL_LABELS.map((l) => l.trim()));
// a failed send's fix ('<rid>:fix') and a failure's own fix wear the fix's own words ("Connect a mailbox") - buttons.json says so of `fix`
// ...and so does a failure's fix chip in the chat: concierge.recover makes `go` chips only of a failure's fix, with the fix's own words
const isFix = (id = "") => /:fix$|^chat:(.+:)?go$/.test(id);
// ...and a receipt's further button, lent to the next item's row (Not ours' "From now on", funnelPile.furtherIndex, 4cb3e165): a chat
// chip wearing the card question's answer for its OWN verb (buttons.json `choices`) - the same words under another verb are still unknown
const CHOICE_WORDS = new Map(Object.values(CHOICES).flat().filter((c) => Array.isArray(c)).map(([v, w]) => [`${v}|${w}`, true]));
const isFurther = (w, id = "") => /^chat:/.test(id) && CHOICE_WORDS.has(`${String(id).split(":").pop()}|${w}`);
const named = (w, id = "") => !w || NAMED.has(w) || /…$/.test(w) || w === "▾" || /^Open TQ-\d+/.test(w) || /:fix$|^chat:(.+:)?go$/.test(id) || isFurther(w, id);
// the cover key of a button: its verb, and the state its words are ("approve:unknown" for Send anyway)
const coverOf = (verb, word) => {
  const v = VERBS[verb]; if (!v) return null;
  if (!word || word === v.label) return verb;
  const st = Object.entries(v.states || {}).find(([, w]) => w === word);
  return st ? `${verb}:${st[0]}` : verb;
};
// a row id -> its verb: the task page's own ids (buttons.json `row`), a chip's verb (`w:mine`), a draft's (`2:approve`)
const verbOfId = (id) => { const last = String(id || "").split(":").pop(); return verbOfRow(id) || (VERBS[last] ? last : null); };
const byLabel = Object.fromEntries(Object.entries(VERBS).flatMap(([k, v]) => [[v.label, k], ...Object.values(v.states || {}).map((w) => [w, k])]));

const web = build && only.size ? mkdtempSync(join(tmpdir(), "tq-deadend-web-")) : "";
if (web && spawnSync("npx", ["vite", "build", "--outDir", web, "--emptyOutDir"], { cwd: join(root, "website"), shell: true, stdio: "ignore" }).status) {
  console.error("the page did not build"); process.exit(2);
}

const found = [], pressed = new Map(), walked = [];          // walked: the paths that ran, so a quiet pass is not an empty one
const note = (rule, at, what) => found.push(`${rule.padEnd(7)} ${at}: ${what}`);
const mark = (key, at) => { if (key && !pressed.has(key)) pressed.set(key, at); };

// ── a server: the demo (refusals ON), or a seeded world whose mailbox, coding tool and AI are the faults module's ────────────
const freePort = () => new Promise((res, rej) => { const s = createServer(); s.unref(); s.on("error", rej);
  s.listen(0, "127.0.0.1", () => { const { port: p } = s.address(); s.close(() => res(p)); }); });
async function serve(n, opts = {}) {
  // a free port can be taken between asking and binding: once more on a fresh one before saying it failed
  for (let tries = 0; ; tries++) {
    const p = fixed ? port + n : await freePort();
    try { return await serveOn(p, opts); }
    catch (e) { if (fixed || tries >= 1) throw e; }
  }
}
async function serveOn(p, { faults = false, linking = false, plant = false, stopsave = false } = {}) {
  const home = mkdtempSync(join(tmpdir(), "tq-deadend-"));
  const launchPy = `
import sys, pathlib
from taskuary import server, cli
from fastapi.staticfiles import StaticFiles
web = ${JSON.stringify(web)}
if web:
    server._web_root = pathlib.Path(web)
    for r in server.app.routes:
        if getattr(r, 'name', '') in ('assets', 'walk'): r.app = StaticFiles(directory=str(server._web_root / r.name), check_dir=False)
if ${faults ? "True" : "False"}:
    from taskuary import faults, demo, firstrun
    assert faults.install(server.app), 'the faults module refused to install'
    demo.seed(server.store); server.store.set_setting(firstrun.DISMISSED, '1', 'walk')
if ${linking ? "True" : "False"}:
    # a brain that links the task it is asked to show, as the prompt's evidence tells it to (concierge.named_now) - else the demo's own
    import re
    from taskuary import demo
    _canned = demo.brain
    def _linking(seed=0, store=None):
        f = _canned(seed, store)
        def llm(system, user, **kw):
            m = re.search(r'TO SHOW IT: link it in your answer as (\\[TQ-\\d+\\]\\(#task=\\d+\\))', str(user or ''))
            return f'Here it is: {m.group(1)}.' if m else f(system, user, **kw)
        return llm
    demo.brain = _linking
if ${plant ? "True" : "False"}:
    # AN AGED ASK, the way the daily sweep raises one (sweep.aged_asks): a person's mail with no task, its line on the rail as an idea
    # whose "Based on" names that mail - planted once the demo has seeded, on the server's own store
    import threading, time
    from datetime import datetime
    def _plant():
        from taskuary import sweep, funnel
        st = server.store
        for _ in range(120):
            m = st._one("SELECT MessageId, FromName, Subject FROM message WHERE TaskId IS NULL AND Channel='email' AND COALESCE(FromName,'')<>'' "
                        "AND COALESCE(Direction,'in')<>'out' ORDER BY MessageId LIMIT 1")
            if m: break
            time.sleep(0.5)
        if not m: return
        stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        sweep._say_once(st, [{'key': f"{sweep.ASK}:plant{m['MessageId']}", 'kind': sweep.ASK, 'sig': stamp,
                              'text': sweep.SAY['unanswered'].format(who=m['FromName'], gist=m['Subject'] or 'a question', ago='15 days ago'),
                              'action': {'type': 'message', 'mid': m['MessageId'], 'tid': None, 'who': m['FromName'], 'by': 'sweep',
                                         'why': sweep.SAY['unanswered_why'].format(days=5)}}], stamp)
        funnel.invalidate()
        st.set_setting('deadend_planted_mid', str(m['MessageId']), 'walk')
    threading.Thread(target=_plant, daemon=True).start()
if ${stopsave ? "True" : "False"}:
    # STOP AND SAVE'S WORLD: one task a colleague wrote in about, a brain that takes its time (the write-up must still be running
    # when Close out's pending block is checked), and a plain shell as its session - opened by the pass, never a coding CLI
    import json, time
    from taskuary import llm, terminal, firstrun
    def _brain(system, user, **kw):
        time.sleep(1.5)
        if 'determination' in str(system): return json.dumps({'determination': 'Posted the charge.', 'actions': 'Created bill 1043',
                                                              'summary': 'Matched the charge and posted the bill.', 'outcome': 'did_work'})
        if 'playbook' in str(system).lower() or 'entries' in str(system): return json.dumps({'entries': [], 'playbook': None})
        return 'Hi Gail,\\n\\nThe hardware store charge is posted as bill 1043.\\n\\nAlex'
    llm.build_llm = lambda *a, **k: _brain
    _transcript_for = terminal.transcript_for
    def _transcript(store, tid):
        text, agent, sid = _transcript_for(store, tid)
        return (text if text.strip() else 'matched the hardware store charge to vendor 87 and posted bill 1043'), agent, sid
    terminal.transcript_for = _transcript
    st = server.store; st.set_setting(firstrun.DISMISSED, '1', 'walk')
    _tid = st.create_task({'Title': ${JSON.stringify(STOPSAVE_TITLE)}, 'Kind': 'coding', 'Status': 'open'}, 'owner')
    st.add_message({'TaskId': _tid, 'ExternalId': 'stopsave-1', 'Channel': 'email', 'Subject': 'The hardware store charge',
                    'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'BodyText': 'Could you post the hardware store charge?',
                    'SentAt': '2026-10-21 09:00:00'})
    # ...and one whose result cannot be saved: the write-up fails, and Close out must say so with its ways on
    from taskuary import session_artifacts
    _coding = session_artifacts.coding
    def _save(store, tid, *a, **k):
        if (store.get_task(tid) or {}).get('Title') == ${JSON.stringify(STOPSAVE_FAILS)}: raise OSError('the disk is full')
        return _coding(store, tid, *a, **k)
    session_artifacts.coding = _save
    _bad = st.create_task({'Title': ${JSON.stringify(STOPSAVE_FAILS)}, 'Kind': 'coding', 'Status': 'open'}, 'owner')
    st.add_message({'TaskId': _bad, 'ExternalId': 'stopsave-2', 'Channel': 'email', 'Subject': 'The fuel card statement',
                    'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'BodyText': 'And the fuel card statement?',
                    'SentAt': '2026-10-21 09:05:00'})
sys.argv =['taskuary'${faults || stopsave ? "" : ", '--demo'"}, '--no-browser', '--port', '${p}']; cli.main()`;
  const env = { ...process.env, TASKUARY_HOME: home, TASKUARY_ALLOW_TEST_HOME: "1", ...(faults ? { TASKUARY_FAULTS: "1" } : stopsave ? {} : { TASKUARY_DEMO: "1" }) };
  if (!faults) delete env.TASKUARY_FAULTS;
  if (faults || stopsave) delete env.TASKUARY_DEMO;
  const srv = spawn("python", ["-c", launchPy], { cwd: root, env, stdio: ["ignore", "ignore", "pipe"] });
  let errTail = ""; srv.stderr.on("data", (d) => { errTail = (errTail + d).slice(-6000); });
  const base = `http://127.0.0.1:${p}`;
  let token = "";
  for (let i = 0; i < 90 && !token; i++) {
    await wait(1000);
    if (srv.exitCode !== null) break;                               // it died: say why now, not after 90 seconds
    try { token = (readFileSync(join(home, "config.toml"), "utf8").match(/^token = "([^"]+)"/m) || [])[1] || ""; } catch { /* not written yet */ }
    if (token && !(await fetch(`${base}/api/funnel/pile`, { headers: { "X-Taskuary-Token": token } }).then((r) => r.ok).catch(() => false))) token = "";
  }
  if (!token) {
    srv.kill();
    const why = srv.exitCode !== null ? `it exited (${srv.exitCode})` : "no answer in 90 s";
    const last = errTail.trim().split(/\r?\n/).slice(-4).join(" | ");
    throw new Error(`the ${faults ? "faults" : "demo"} server never came up on port ${p}: ${why}${last ? ` - its last words: ${last}` : ""}`);
  }
  const H = { "X-Taskuary-Token": token, "Content-Type": "application/json" };
  const api = async (method, path, body) => { const r = await fetch(`${base}${path}`, { method, headers: H, body: body ? JSON.stringify(body) : undefined }); return r.json().catch(() => ({})); };
  if (faults || stopsave) await api("POST", "/api/setup/dismiss", { dismissed: true });
  // ...and where the server's own last traceback stands, for a CALLS 500 to say where it broke (CI keeps no server log)
  const where = () => errTail.split(/\r?\n/).filter((l) => /^\s*File "|Error\b|Exception\b/.test(l)).slice(-5).map((l) => l.trim()).join(" | ");
  return { base, token, api, where, stop: () => { if (!keep) srv.kill(); } };
}

// ── a page on it: the owner's token put where a launch key would (the demo refuses minting one), the rules' listeners attached ──
let browser;
async function pageOn(srv, phase) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1366, height: 768 });            // a laptop: where "the card is off the screen" happens
  if (throttle > 1) await page.emulateCPUThrottling(throttle);      // CI's runner, on a dev box: what a glide does a few times slower
  await page.evaluateOnNewDocument((t) => { try { localStorage.setItem("taskuary_token", t); } catch { /* none */ } }, srv.token);
  await page.evaluateOnNewDocument((keys) => { window.__sections = keys; }, SECTION_KEYS);
  await page.evaluateOnNewDocument(swapWatch);
  page.step = phase;
  page.on("pageerror", (e) => note("CRASH", page.step, e.message));
  page.expect = new Set();                                           // an /api path whose failure the step forced on purpose
  page.adviceReads = [];                                             // when each read of the Advisor's line went out (REREAD)
  page.posts = [];                                                   // when each act went to the server, and where (a press that landed)
  page.on("request", (r) => { const u = new URL(r.url()).pathname; if (u === "/api/advice") page.adviceReads.push(Date.now());
    else if (r.method() === "POST") page.posts.push([Date.now(), u]); });
  page.on("response", async (r) => {
    const u = new URL(r.url());
    if (!u.pathname.startsWith("/api/") || r.status() < 400 || u.pathname === "/api/test/fault") return;
    if (r.request().method() !== "GET") page.failedAt = Date.now();     // an act refused or failed, the demo's no included (AGAIN)
    const body = await r.json().catch(() => ({}));
    if (r.status() === 403 && body?.demo) return;                    // the demo saying no, as the demo: an ordinary line
    if ([...page.expect].some((x) => u.pathname.includes(x))) return;
    if (r.status() >= 500) await wait(300);                           // the traceback reaches stderr just after the answer
    note("CALLS", page.step, `${r.request().method()} ${u.pathname} answered ${r.status()}${body?.detail ? ` - "${String(body.detail).slice(0, 80)}"` : ""}`
      + (r.status() >= 500 && srv.where?.() ? ` - server: ${srv.where().slice(-600)}` : ""));
  });
  await page.goto(`${srv.base}/`, { waitUntil: "load" });
  await wait(6000);
  await clickText(page, "Walk me through my tasks");
  await wait(5000);
  return page;
}
const clickText = async (page, t, scope = "") => {
  for (const b of await page.$$(`${scope} button`)) if (await b.evaluate((e, t) => e.innerText.trim() === t && e.getBoundingClientRect().width > 0, t)) { await b.click(); return true; }
  return false;
};

// SWAP: every frame of the page, watched in the page itself - a screenshot every few hundred ms missed what lasts five frames. The
// ring and the empty view are judged from a press (a click, Enter or Space) until it settles, as the report asked - a reload landing
// on the server's word is not a transition. Each wrong frame is kept once per kind and item; look() hands them to the running step.
function swapWatch() {
  const seen = new Set(), out = window.__swap = [], since = new Map(), rest = new Map(), said = new Set();
  const add = (kind, what) => { if (!seen.has(`${kind} ${what}`)) { seen.add(`${kind} ${what}`); out.push(`${kind}: ${what}`); } };
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  let pressAt = -1e9;
  const pressed = (e) => { if (e.type !== "keydown" || ["Enter", " "].includes(e.key)) pressAt = performance.now(); };
  addEventListener("pointerdown", pressed, true); addEventListener("keydown", pressed, true);
  const tick = () => {
    const now = performance.now(), afterPress = now - pressAt < 4000;
    const ring = [...document.querySelectorAll("[data-tq-rail] .tq-pile-row.current")].map((r) => r.getAttribute("data-tq-key"));
    const views = [...document.querySelectorAll("[data-tq-canvas-item]")].filter(vis);
    const view = views[views.length - 1], key = view?.getAttribute("data-tq-canvas-item") || "";
    // THE RING AND ITS VIEW MOVE TOGETHER: after a press the ring names the view on the table in every frame - the view drawn ahead
    // with it (AssistantView surface), or both at the answer. A history read that put an older line back on the table under the ring
    // is caught here too (2026-10-20: about 1.7 s after a Next, until the next press - assistantTurns keeps the aliases now)
    if (afterPress && ring.length === 1 && key && ring[0] !== key) add("ring", `the rail rings ${ring[0]} while the table shows ${key}`);
    // a view mounted before its task: one read ahead draws it on its first frame (taskDetail.js); a cold one may wait for its read,
    // never past a second - a view that stands empty that long is a read that is not coming
    const shell = view?.querySelector("[data-tq-task-loading]");
    if (shell) { if (!since.has(key)) since.set(key, now); else if (afterPress && now - since.get(key) > 1000) add("shell", `${key}'s task view stood empty past a second`); }
    else since.delete(key);
    const steps = view?.querySelector("[data-tq-steps]")?.getAttribute("data-tq-steps");
    if (steps === "0") said.add(key); else if (steps && steps !== "reading" && said.has(key)) add("steps", `${key} said "no steps yet" and then drew ${steps}`);
    // rows that keep their order must never be drawn over each other on the way; rows trading places cross, which is the reorder.
    // Where a row comes FROM is where it last stood still.
    const here = new Set();
    for (const st of document.querySelectorAll("[data-tq-rail] .tq-pile-stack")) {
      const top0 = st.getBoundingClientRect().top;
      const rs = [...st.querySelectorAll(":scope > .tq-pile-row")].filter((r) => vis(r) && +getComputedStyle(r).opacity > 0.05).map((r) => {
        const b = r.getBoundingClientRect(), k = r.getAttribute("data-tq-key"), to = parseFloat(r.style.top), at = b.top - top0;
        if (Math.abs(at - to) <= 0.5 || !rest.has(k)) rest.set(k, at);
        here.add(k);
        return { k, top: b.top, bottom: b.bottom, to, from: rest.get(k) };
      }).sort((a, b) => a.top - b.top);
      for (let i = 1; i < rs.length; i++) {
        const a = rs[i - 1], b = rs[i];
        if (a.bottom - b.top > 1.5 && (a.from < b.from) === (a.to < b.to)) add("rows", `${a.k} drawn over ${b.k}`);
      }
    }
    for (const k of rest.keys()) if (!here.has(k)) rest.delete(k);           // a row that comes back comes from where it is drawn then
    // ONE TASKS SECTION (the owner, 2026-10-21): the rail's headings are lanes.json's, and a task an agent is working is ringed where
    // it is - under Tasks, or For later when Remind me put it away - never a section of its own
    for (const h of document.querySelectorAll("[data-tq-rail] [data-tq-section-head]")) {
      const s = h.getAttribute("data-tq-section-head");
      if (!(window.__sections || []).includes(s)) add("section", `a "${s}" heading lanes.json does not name`);
    }
    for (const r of document.querySelectorAll("[data-tq-rail] [data-tq-working]")) {
      const run = r.closest("[data-tq-run]")?.getAttribute("data-tq-run");
      if (run && run !== "task" && run !== "later") add("section", `${r.closest("[data-tq-key]")?.getAttribute("data-tq-key")} spins under ${run}`);
    }
    requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}
// one read of everything the rules look at - and the wrong frames since the last read, said for the step that drew them
const look = async (page) => { const s = await readPage(page); for (const w of s.swap) note("SWAP", page.step, w); return s; };
const readPage = (page) => page.evaluate(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const row = document.querySelector("[data-tq-row]"), chat = document.querySelector(".tq-chat-body");
  const verbs = row ? [...row.querySelectorAll("button")].filter(vis).map((b) => ({ word: b.innerText.trim(), id: b.getAttribute("data-tq-verb") || "", dark: b.classList.contains("p"), own: b.hasAttribute("data-tq-own"), next: b.hasAttribute("data-tq-next") || b.hasAttribute("data-tq-walk-back"), off: b.disabled })) : [];
  const cards = [...document.querySelectorAll("[data-tq-task-page]")].filter(vis), card = cards[cards.length - 1];
  const cardBtns = card ? [...card.querySelectorAll("button")].filter(vis).map((b) => ({ word: b.innerText.trim(), off: b.disabled })).filter((b) => b.word) : [];
  const cr = card?.getBoundingClientRect(), hr = chat?.getBoundingClientRect(), rr = row?.getBoundingClientRect();
  const errs = [...document.querySelectorAll('[role="alert"], .MuiAlert-standardError, .tq-next-err')].filter(vis).map((e) => e.innerText.trim()).filter(Boolean);
  const rail = [...document.querySelectorAll("[data-tq-rail] [data-tq-key]")].map((e) => ({ key: e.getAttribute("data-tq-key"),
    text: e.innerText.replace(/\s+/g, " ").trim(), title: (e.querySelector(".card b")?.innerText || "").trim(), current: e.classList.contains("current"),
    // a row's state is its logo's (StatusMark.jsx) with no emoji in its text, so it is read from the mark's own key
    status: e.querySelector(".tq-mark")?.getAttribute("data-tq-status") || "" }));
  const table = [...document.querySelectorAll("[data-tq-rail] *")].find((e) => e.children.length === 0 && e.innerText?.trim() === "ON THE TABLE");
  const ref = (table?.closest("[data-tq-key]")?.innerText.match(/TQ-\d+/) || [])[0] || ((card?.innerText || "").match(/TQ-\d+/) || [])[0] || "";
  const adviceEl = document.querySelector('[data-tq-advice]:not([data-tq-advice="no_ai"])');
  // ...the Advisor DECIDED: a line, a silent decision's mark (an obvious move lit and said by nothing), or no AI with its Connect lit
  const decided = !!document.querySelector("[data-tq-advice]");
  // THE ADVISOR'S STRIP AND ITS LIT BUTTON: the strip is empty only if nothing in it speaks; the lit button must be on the screen
  // and the thing under its own centre
  // ...the dock's strip takes no room while it is silent (2026-10-26), so a silent one is read where it is, unseen
  const strip = [...document.querySelectorAll("[data-tq-strip]")].find(vis) || document.querySelector(".tq-dock [data-tq-strip]");
  // ...the row's filled button, or the draft card's own lit one (ReviewDecision marks it [data-tq-lit]): a draft's Send, Copy or
  // Redraft is lit under the draft, never on the bar (the owner, 2026-10-22) - the silent strip over it is the obvious move, not a gap
  const litEl = (row && [...row.querySelectorAll(".tq-arow-verbs .tq-ab.p")].find(vis)) || [...document.querySelectorAll("[data-tq-lit]")].find(vis);
  const lr = litEl?.getBoundingClientRect(), hit = lr && document.elementFromPoint(lr.left + lr.width / 2, lr.top + lr.height / 2);
  const lit = litEl ? { word: litEl.innerText.trim(), inView: lr.top >= 0 && lr.left >= 0 && lr.bottom <= innerHeight && lr.right <= innerWidth,
    covered: !(hit && (hit === litEl || litEl.contains(hit))) } : null;
  // From is the sender's own words, quoted (the two-column page, 0.3.9.21): a mail that says "Traceback ... null" is the ask, not
  // our jargon - so the words check reads the card without it, and everything Taskuary writes stays held to the list
  // ...and a closed section's tab (the three sections, 2026-10-27) quotes the latest message and the draft in its lines, marked “...”
  const quoted = card ? [...card.querySelectorAll("[data-tq-from], [data-tq-from-line], [data-tq-quoted], [data-tq-tab-line]")]
    .filter((el) => !el.hasAttribute("data-tq-tab-line") || el.innerText.includes("“")).map((el) => el.innerText).filter(Boolean) : [];
  const own = quoted.reduce((t, q) => t.split(q).join(" "), card?.innerText || "");
  const read = [own, row?.innerText || "", adviceEl?.innerText || "", ...errs].join("\n");
  const pops = [...document.querySelectorAll('.MuiPopover-paper, [role="dialog"], .MuiDrawer-paper')].filter(vis).map((p) => p.innerText.replace(/\s+/g, " ").slice(0, 80));
  const msgs = chat ? [...chat.querySelectorAll(".tq-msg")] : [];
  const tail = msgs.slice(-8);                       // a receipt stays a few lines up once the walk has brought the next item
  return { verbs, cardBtns, advice: !!adviceEl, decided, adv: adviceEl?.innerText || "", errs, rail, ref, read, chat: chat?.innerText || "", pops, lit,
    swap: (window.__swap || []).splice(0),
    strip: strip ? { empty: !strip.querySelector(".tq-next"), busy: strip.getAttribute("data-tq-strip") === "busy", unlit: !!strip.querySelector("[data-tq-unlit]") } : null,
    undoSaid: tail.some((m) => /Undo: |confirm below/i.test(m.innerText || "")),
    // ...but a REMOVE's own "Removed <it> - Undo" (Removed.jsx, [data-tq-undo]) is the approved exception: a Remove acts at once and is
    // taken back there, never behind "are you sure" (the owner, 2026-10-21 - Remove - not a task's included, 2026-10-22)
    undoBtns: [...document.querySelectorAll("button")].filter((b) => vis(b) && !b.closest("[data-tq-undo]")).map((b) => b.innerText.trim()).filter((w) => /^(take it back|undo\b)/i.test(w)),
    // Remind me's receipt is the badge on its card now ("✓ Remind me", 0.3.9.28), the "Away until" line only where one is left
    away: tail.filter((m) => /Away until /.test(m.innerText || "") || /^Remind/.test(m.querySelector("[data-tq-pressed]")?.getAttribute("data-tq-pressed") || "")).length,
    chatBtns: tail.flatMap((m) => [...m.querySelectorAll("button")].filter(vis).map((b) => b.innerText.trim())),
    nmsg: msgs.length, last: (msgs[msgs.length - 1]?.innerText || "").slice(0, 200), url: location.href, focus: document.activeElement?.tagName || "",
    folded: [...document.querySelectorAll("[data-tq-folded]")].filter(vis).map((e) => e.getAttribute("data-tq-folded")),
    card: card ? { top: cr.top, shown: Math.min(cr.bottom, rr ? rr.top : hr.bottom) - Math.max(cr.top, hr.top), text: card.innerText.length } : null };
});
// what a press may change: if none of it did, the owner pressed and nothing happened
const sig = (s) => JSON.stringify([s.verbs.map((v) => v.id + v.word + v.off), s.cardBtns.map((b) => b.word + b.off), s.rail.map((r) => r.key), s.nmsg, s.last,
  s.errs, s.pops, s.url, s.focus, s.ref, s.card?.text || 0, s.folded]);

const darkOwn = (v) => !!v?.own && v.id === "save-end";
const judge = (s, at) => {
  // ...but for ONE button the row darkens itself (the owner, 2026-10-20): a running agent's own Stop and save, the Advisor quiet over it
  const dark = s.verbs.filter((v) => v.dark && !darkOwn(v));
  if (s.card || s.ref) {
    if (!s.decided && dark.length) note("DARK", at, `"${dark.map((v) => v.word).join('", "')}" dark with no Advisor decision over it`);
    if (s.advice && dark.length > 1) note("DARK", at, `the Advisor spoke and ${dark.length} buttons are dark - ${JSON.stringify(s.verbs.map((v) => v.word))} / "${s.adv.slice(0, 80)}"`);
  }
  if (s.strip?.empty && !s.strip.busy && !s.strip.unlit && !s.lit) note("STRIP", at, "the Advisor's strip under the item says nothing and nothing on the row is lit");
  if (s.advice && s.lit && !s.pops.length && (!s.lit.inView || s.lit.covered)) note("LIT", at, `the Advisor's lit "${s.lit.word}" is ${s.lit.inView ? "covered" : "off the screen"}`);
  if (s.card && s.card.shown < 120) note("SEEN", at, `only ${Math.round(s.card.shown)}px of the card on the table is in view`);
  if (s.errs.length && !s.verbs.some((v) => !v.next && !v.off) && !s.cardBtns.some((b) => !b.off && NAMED.has(b.word)))
    note("FIX", at, `"${s.errs[0].slice(0, 90)}" and nothing on the row but Next`);
  for (const w of JARGON) { const m = s.read.match(w); if (m) note("WORDS", at, `"${m[0]}" in "${s.read.slice(Math.max(0, m.index - 40), m.index + 60).replace(/\s+/g, " ")}"`); }
  if (s.undoBtns.length) note("UNDO", at, `"${s.undoBtns[0]}" is on the screen - nothing offers to take an act back`);
  if (s.undoSaid) note("UNDO", at, "a line says an act can be undone, or to confirm below");
  const odd = [...new Set(s.verbs.filter((v) => !named(v.word, v.id)).map((v) => v.word))];
  if (odd.length) note("NAMES", at, `on the row but on no list of buttons: ${JSON.stringify(odd)}`);
};
const receipts = (before, after, at) => {
  const keys = new Set(after.rail.map((r) => r.key));
  for (const r of before.rail.filter((r) => !keys.has(r.key))) {
    const ref = (r.text.match(/TQ-\d+/) || [])[0], name = ref || r.title.replace(/…$/, "").slice(0, 30);
    // a batch's rows are said by its card, folded with the badge of what was pressed ("4 fyi  ✓ Read") - the "Read - 4 fyi let go."
    // line it replaced is gone (the owner, 2026-10-22: "put a little animation on the corner ... not free text")
    if (name && !after.chat.includes(name) && !(r.key.startsWith("processing:") && !ref && /\d+ fyi[\s\S]{0,40}✓/.test(after.chat)))
      note("RECEIPT", at, `${name} left the rail with no line saying where it went`);
  }
};
// ...and a draft's `approve` only by a Send word (on a channel that cannot send it once read Mark done - pressed as "Send", it closed
// the task, 2026-10-19). A draft's Send lives UNDER THE DRAFT only (the owner, 2026-10-22): the bar keeps an empty slot, so the walk
// presses the card's own button - its first visible, live one that starts with a Send word
const sendWords = [label("approve"), ...Object.values(VERBS.approve?.states || {})];
// ...pressed from inside the page, as pressVerb does, and stamped when it is pressed (REREAD and AGAIN count from the press, not the search)
const pressCardSend = async (page) => {
  const h = (await page.evaluateHandle((words) => [...document.querySelectorAll("[data-tq-task-page] button")].find((b) => !b.disabled
    && b.getBoundingClientRect().width > 0 && words.some((w) => b.innerText.trim().startsWith(w))) || null, sendWords)).asElement();
  if (!h || !(await tap(page, h))) return false;
  mark("approve", page.step); return true;
};
// a press from inside the page: a node gone by then is not pressed, never a crash; `pressedAt` is when the click ran
const tap = (page, e) => e.evaluate((x) => x.isConnected && (x.scrollIntoView({ block: "nearest" }), x.click(), true)).catch(() => false)
  .then((ok) => { if (ok) page.pressedAt = Date.now(); return ok; });
// ...and a ▾ menu waited on, open and shut: on CI's slower runner the menu was not drawn 400 ms after its ▾, the Escape went to the page,
// and the menu opened after it - its backdrop then took the draft's Send, so no send went out and the failure was never drawn (0.3.9.50)
const menuUp = (page) => page.evaluate(() => [...document.querySelectorAll('[role="menu"]')].some((m) => m.getBoundingClientRect().width > 0));
const until = async (f, ms = 3000) => { for (const t = Date.now(); Date.now() - t < ms; await wait(100)) if (await f()) return true; return false; };
const cardSends = (s) => s.cardBtns.some((b) => !b.off && sendWords.some((w) => b.word.startsWith(w)));
// ...a greyed button is not one to press (the owner, 2026-10-22: a button that cannot work is greyed, its reason in the hover) - a click
// on it does nothing, and the walk took that for a start and judged the screen it never left
const rowHandle = (page, verb) => page.evaluateHandle((verb, ids, words) => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && !e.disabled; };
  return [...document.querySelectorAll("[data-tq-row] button[data-tq-verb]")].filter(vis).find((b) => ids.includes(b.getAttribute("data-tq-verb").split(":").pop())
    && (!words.length || words.some((w) => b.innerText.trim().startsWith(w)))) || null;
}, verb, [verb, ...(VERBS[verb]?.row || [])], verb === "approve" ? sendWords : []);
// ...and one folded behind a ▾ is pressed from its menu (walkdriver.doVerb): the one-row bar's pill takes the row's width, so Send to agent
// folded on a laptop and the faults pass found "no task with Send to agent to start" (0.3.9.49) - a press the owner makes in two clicks
const menuHandle = (page, verb) => page.evaluateHandle((ids, words) => [...document.querySelectorAll('[role="menu"] [role="menuitem"][data-tq-verb]')]
  .find((i) => i.getAttribute("aria-disabled") !== "true" && ids.includes(i.getAttribute("data-tq-verb").split(":").pop())
    && (!words.length || words.some((w) => i.innerText.trim().startsWith(w)))) || null, [verb, ...(VERBS[verb]?.row || [])], verb === "approve" ? sendWords : []);
const pressVerb = async (page, verb) => {
  const h = (await rowHandle(page, verb)).asElement();
  // ...pressed from inside the page, as walkdriver does: a menu redrawn between the find and a remote click threw "Node is either not
  // clickable or not an Element" and ended the faults pass on CI (0.3.9.50) - a node gone by then is looked for again, not a crash
  if (h && (await tap(page, h))) { mark(verb, page.step); return true; }
  for (const m of await page.$$eval("[data-tq-row] [data-tq-more]", (e) => e.map((x) => x.dataset.tqMore))) {
    await page.evaluate((m) => document.querySelector(`[data-tq-row] [data-tq-more="${m}"]`)?.click(), m);
    if (!(await until(() => menuUp(page)))) continue;
    const i = (await menuHandle(page, verb)).asElement();
    if (i && (await tap(page, i))) { mark(verb, page.step); walked.push(`${page.step}: ${verb} pressed from the ${m} ▾`); return true; }
    await page.keyboard.press("Escape");
    if (!(await until(async () => !(await menuUp(page))))) note("STUCK", page.step, `the ${m} ▾ menu did not close on Escape`);
  }
  if (await menuUp(page)) { await page.keyboard.press("Escape"); await until(async () => !(await menuUp(page))); }   // one drawn late
  return false;
};
const pressNext = async (page) => { const h = await page.$("[data-tq-row] [data-tq-next]"); if (!h) return false; await h.click(); mark("next", page.step); return true; };
// the walk's Back, Next's other half in the Nav pill (the owner, 2026-10-27): up the line to the row above
const pressBack = async (page) => { const h = await page.$("[data-tq-row] [data-tq-walk-back]"); if (!h) return false; await h.click(); mark("back", page.step); return true; };
const openItem = async (page, pick) => {                        // a rail row by its key, or the first whose words match
  const s = await look(page);
  const r = s.rail.find((x) => (typeof pick === "string" ? x.key === pick || x.text.includes(pick) : pick(x)));
  if (!r) return null;
  const h = await page.$(`[data-tq-rail] [data-tq-key="${r.key}"]`); if (!h) return null;
  await h.click(); await wait(3500); return r;
};
const closePops = async (page) => { for (let i = 0; i < 2; i++) { await page.keyboard.press("Escape"); await wait(300); } };

// STILL: the row sampled while the item settles - every button's place by its id, and whether the Advisor's line is up. A button that
// moved when the line landed is a row reshuffled under the owner's hand; the advice only tints (2026-10-19)
const rowAt = (page) => page.evaluate(() => {
  // a row held for its first decision (aria-busy, hidden) is not drawn yet: the owner sees no button on it to move
  const row = document.querySelector("[data-tq-row]:not([aria-busy])");
  const at = row ? Object.fromEntries([...row.querySelectorAll("button[data-tq-verb], button[data-tq-next]")].filter((b) => b.getBoundingClientRect().width > 0)
    // a button is known by its act, not the card that registered it: a chat's `chat:mine` and the walk's `w:mine` are one button
    .map((b) => [String(b.getAttribute("data-tq-verb") || "next").split(":").pop(), Math.round(b.getBoundingClientRect().left)])) : {};
  return { item: document.querySelector("[data-tq-canvas-item]")?.getAttribute("data-tq-canvas-item") || "", advice: !!document.querySelector('[data-tq-advice=""]'), at };
});
async function settle(page, at, ms = 5000) {
  let quiet = null;
  for (let t = 0; t < ms; t += 250) {
    const r = await rowAt(page);
    if (!r.advice) quiet = Object.keys(r.at).length > 1 ? r : null;    // a row still loading (only Next) is not one the advice moved
    else if (quiet && quiet.item === r.item) {
      const moved = Object.keys(r.at).filter((id) => id in quiet.at && Math.abs(r.at[id] - quiet.at[id]) > 2);
      const came = Object.keys(r.at).filter((id) => !(id in quiet.at)), went = Object.keys(quiet.at).filter((id) => !(id in r.at));
      if (moved.length || came.length || went.length)
        note("STILL", at, `the Advisor's line landed and the row changed - moved ${JSON.stringify(moved)}, came ${JSON.stringify(came)}, went ${JSON.stringify(went)}`);
      quiet = null;
    }
    await wait(250);
  }
}
// REREAD: after a press on the row the advice is read again for the item as the act left it - a GET /api/advice within 2.5 s of the press
// ...counted from the click itself (page.pressedAt): from before the ▾ menus were searched for Send, the search ate the 2.5 s on CI (0.3.9.50)
const reread = (page, t0, at) => { if (!page.adviceReads.some((t) => t > t0 && t - t0 < 2500)) note("REREAD", at, "a press on the row and no fresh read of the Advisor's line after it"); };

// AGAIN: a press of the lit button that was refused or failed - the advice is read again, and its new line must light the way past it,
// never the press that just failed. Up to 8 s for the line to change; whatever it lights then is what the owner is sent to.
const again = async (page, before, t0, words, at) => {
  if (!before?.lit || !words.includes(before.lit.word)) return;
  let s = null;
  for (let t = 0; t < 8000; t += 500) { await wait(500); s = await look(page); if (s.advice && s.adv !== before.adv) break; }
  if ((page.failedAt > t0 || s?.errs.length) && s?.advice && s.lit?.word === before.lit.word)
    note("AGAIN", at, `"${before.lit.word}" was pressed and refused, and the Advisor's line still lights it: "${s.adv.slice(0, 80)}"`);
};

// ── WALK: Next through the day, doing what each card's first button invites, so the paths behind it run too ─────────────────
async function walk() {
  const srv = await serve(0), page = await pageOn(srv, "walk");
  let s = await look(page);
  const did = new Set(), seen = new Map();
  for (let n = 0; n < 40; n++) {
    const at = page.step = `walk ${n} ${s.ref || "(no item)"}`;
    judge(s, at);
    if (s.verbs.some((v) => v.word.startsWith("Open TQ"))) break;
    const before = s, has = (verb) => s.verbs.some((v) => verbOfId(v.id) === verb), t0 = Date.now();
    if (!did.has("approve") && (has("approve") || cardSends(s)) && ((await pressVerb(page, "approve")) || (await pressCardSend(page)))) {
      did.add("approve"); await wait(2600); reread(page, page.pressedAt || t0, at); await again(page, before, page.pressedAt || t0, sendWords, at);
    }
    else if (!did.has("close") && has("close")) {
      did.add("close"); await pressVerb(page, "close"); await wait(1200);
      await clickText(page, label("close"), '[role="dialog"]');
    }
    else if (s.verbs.some((v) => v.word === label("next", "batch"))) await clickText(page, label("next", "batch"), "[data-tq-row]");
    // ...once, Back: up to the row above and down again with Next - the walk goes on from where it was
    else if (!did.has("back") && (await page.$("[data-tq-row] [data-tq-walk-back]")) && (await page.$("[data-tq-row] [data-tq-next]"))) {
      did.add("back"); await pressBack(page); await wait(3500); s = await look(page); judge(s, `${at} (back)`); await pressNext(page);
    }
    // ...and the last one has no Next by design (Nav: "no Next on the last one") - its Back and its own moves are the row; the walk ends
    else if (!(await page.$("[data-tq-row] [data-tq-next]")) && (await page.$("[data-tq-row] [data-tq-walk-back]"))) break;
    else if (!(await pressNext(page))) {
      const inline = await page.$$(".tq-chat-body .tq-msg button, .tq-chat-body .tq-proposal button");
      const words = await Promise.all(inline.map((h) => h.evaluate((b) => b.innerText.trim())));
      if (!inline.length) { note("FIX", at, `no Next on the row and nothing in the chat - the row: ${JSON.stringify(s.verbs.map((v) => v.word))}`); break; }
      note("INLINE", at, `the way on is in the chat, not on the row: ${JSON.stringify(words.filter(Boolean))}`);
      await inline[0].click();
    }
    await settle(page, at);
    s = await look(page);
    judge(s, `${at} after`);
    receipts(before, s, at);
    const k = JSON.stringify([s.ref, s.verbs.map((v) => v.word), s.chat.length]);
    seen.set(k, (seen.get(k) || 0) + 1);
    if (seen.get(k) >= 3) { note("STUCK", at, `three presses left the same screen - the row: ${JSON.stringify(s.verbs.map((v) => v.word))}`); break; }
  }
  // ...and the end row offers the walk again beside them - the day card's own button, not a card or a line (the owner, 2026-10-22)
  if (s.verbs.some((v) => v.word.startsWith("Open TQ")) && !s.verbs.some((v) => v.word === label("walk"))) note("OPENS", page.step, `the walk's end has no ${label("walk")} on the row: ${JSON.stringify(s.verbs.map((v) => v.word))}`);
  // OPENS: the end line's first chip must put its own TQ on the table
  const w = s.verbs.map((v) => v.word).find((x) => x.startsWith("Open TQ"));
  if (w && await clickText(page, w, "[data-tq-row]")) {
    await wait(5000);
    const got = await look(page), want = w.match(/TQ-\d+/)[0];
    if (got.ref !== want) note("OPENS", w, `put ${got.ref || "nothing"} on the table`);
    judge(got, w);
  }
  await page.close(); srv.stop();
}

// ── SWEEP: every button every row shows, in the row and its More menus, pressed once each ──────────────────────────────────
async function sweep() {
  const srv = await serve(1), page = await pageOn(srv, "sweep");
  const done = new Set(), unnamed = new Set();
  for (let round = 0; round < 3; round++) {
    for (const r of (await look(page)).rail) {
      if (done.has(r.key)) continue;
      if (!(await openItem(page, r.key))) continue;
      // what the row offers: its buttons, and each More menu's items
      const offers = [];
      const s0 = await look(page);
      for (const v of s0.verbs) if (!v.next && v.word !== "▾") offers.push({ id: v.id, word: v.word, menu: -1 });
      const mores = await page.$$("[data-tq-row] button");
      let mi = 0;
      for (const m of mores) {
        if ((await m.evaluate((b) => b.innerText.trim())) !== "▾") continue;
        await m.click(); await wait(600);
        const items = await page.evaluate(() => [...document.querySelectorAll('[role="menuitem"]')].filter((e) => e.getBoundingClientRect().width > 0)
          .map((e) => ({ id: e.getAttribute("data-tq-verb") || "", word: e.innerText.trim() })));
        for (const it of items) {
          offers.push({ ...it, menu: mi });
          if (!named(it.word, it.id) && !unnamed.has(it.word)) { unnamed.add(it.word); note("NAMES", `sweep ${r.text.slice(0, 30)} menu`, `"${it.word}" in the row's More menu is on no list of buttons`); }
        }
        await closePops(page); mi++;
      }
      let left = false;
      for (const o of offers) {
        const verb = verbOfId(o.id) || byLabel[o.word], key = verb && coverOf(verb, o.word);
        if (!key || pressed.has(key)) continue;
        if (!(await openItem(page, r.key))) { left = true; break; }
        const at = page.step = `sweep ${key} on ${r.text.slice(0, 40)}`;
        const before = await look(page);
        if (o.menu >= 0) {
          const ms = []; for (const m of await page.$$("[data-tq-row] button")) if ((await m.evaluate((b) => b.innerText.trim())) === "▾") ms.push(m);
          if (!ms[o.menu]) continue;
          await ms[o.menu].click(); await wait(600);
          const it = await page.evaluateHandle((id, word) => [...document.querySelectorAll('[role="menuitem"]')].find((e) => (id && e.getAttribute("data-tq-verb") === id) || e.innerText.trim() === word) || null, o.id, o.word);
          if (!it.asElement()) { await closePops(page); continue; }
          await it.asElement().click();
        } else {
          let h = await page.$(`[data-tq-row] [data-tq-verb="${o.id}"]`);
          // ...a press before it can move a button into ▾ (a drafted answer's Send takes a slot): it is found there, by its id
          if (!h) for (const m of await page.$$("[data-tq-row] [data-tq-more]")) {
            await m.click(); await wait(600);
            h = await page.$(`[role="menuitem"][data-tq-verb="${o.id}"]`);
            if (h) break;
            await closePops(page);
          }
          if (!h) continue;
          await h.click();
        }
        mark(key, at);
        await wait(4500);
        const after = await look(page);
        if (sig(after) === sig(before)) note("NOTHING", at, `pressed "${o.word}" and nothing on the screen changed`);
        judge(after, at);
        receipts(before, after, at);
        await closePops(page);
        if (!after.rail.some((x) => x.key === r.key)) { left = true; break; }
      }
      if (!left) done.add(r.key);
    }
  }
  await page.close(); srv.stop();
}

// ── FAULTS: each failure the app knows, forced at the boundary, and its way out pressed ─────────────────────────────────────
async function faults() {
  const srv = await serve(2, { faults: true }), page = await pageOn(srv, "faults");
  const fault = (f) => srv.api("POST", "/api/test/fault", { fault: f });
  // each scenario from the chat as it opens: a fix that opened a place leaves the canvas on it
  const fresh = async () => { await page.goto(`${srv.base}/`, { waitUntil: "load" }); await wait(5000); await clickText(page, "Walk me through my tasks"); await wait(4000); };
  const outs = (s) => [...s.verbs.filter((v) => !v.next && !v.off).map((v) => ({ word: v.word, id: v.id, row: true })), ...s.cardBtns.filter((b) => !b.off).map((b) => ({ word: b.word }))];
  // press the draft's Send: the card's own, under the draft (a proposal's row verb first, where one is on the bar)
  // ...and see it reach the server: on CI a Send pressed while the card was still settling sent nothing, and the pass judged the untouched
  // draft as a failure with no way out (0.3.9.50). A press that sent nothing is pressed again; three that send nothing are the finding.
  const send = async () => {
    for (let i = 0; i < 3; i++) {
      const t = Date.now();
      if (!((await pressVerb(page, "approve")) || (await pressCardSend(page)))) return i ? "lost" : false;
      if (await until(async () => page.posts.some(([at, u]) => at >= t && /^\/api\/reviews\/\d+\/decide$/.test(u)), 5000)) return true;
      walked.push(`${page.step}: Send pressed and nothing went to the server - pressed again`);
    }
    return "lost";
  };
  // after a forced failure: the screen must carry a way out from the list, and pressing it must do something
  // ...looked for until it is drawn, up to 15 s: CI's slower machine still showed the draft ("Answering ...") 6 s after the failed send,
  // and the faults pass judged that screen as one with no way out (0.3.9.50)
  const wayOut = async (at, want, { press = true } = {}) => {
    const find = (s) => { const ways = outs(s); return want.map((w) => ways.find((x) => (typeof w === "string" ? x.word === w : w(x)))).find(Boolean); };
    let s = await look(page);
    for (let t = Date.now(); !find(s) && Date.now() - t < 15000; s = await look(page)) await wait(1000);
    judge(s, at);
    const ways = outs(s), hit = find(s);
    if (!hit) { note("WAYOUT", at, `expected ${want.map((w) => (typeof w === "string" ? `"${w}"` : w.name || "a fix")).join(" or ")} - the screen offers ${JSON.stringify(ways.map((w) => w.word))}${s.errs[0] ? ` under "${s.errs[0].slice(0, 80)}"` : ""}`); return null; }
    walked.push(`${at}: offered "${hit.word}"`);
    if (!press) return hit;
    const before = s;
    if (hit.id) { const h = await page.$(`[data-tq-row] [data-tq-verb="${hit.id}"]`); if (h) await h.click(); }
    else await clickText(page, hit.word);
    const v = hit.id ? verbOfId(hit.id) : byLabel[hit.word]; mark(v && coverOf(v, hit.word), at);
    await wait(4500);
    const after = await look(page);
    if (sig(after) === sig(before)) note("WAYOUT", at, `"${hit.word}" was offered as the way out and pressing it changed nothing`);
    judge(after, `${at} after "${hit.word}"`);
    await closePops(page);
    return hit;
  };
  const aFix = (x) => isFix(x.id);
  // a refused recipient is fixed by changing the draft, not by sending it again - Redraft is its way, or the bug report
  const plan = [["auth", [aFix, "Sign in again"]], ["reject", [aFix, label("redraft"), label("report_bug")]],
                ["nomailbox", [aFix, "Connect a mailbox"]], ["unknown", [label("approve", "unknown")]]];
  for (const [f, want] of plan) {
    await fault(f); page.step = `faults ${f}`; await fresh();
    // a draft that can send (a chat's draft is answered where it came from, and shows no Send) and has not failed yet
    let sent = false, before = null, t0 = 0;
    for (const r of (await look(page)).rail.filter((x) => x.status === "approve")) {
      if (!(await openItem(page, r.key))) continue;
      before = await look(page); t0 = Date.now();
      const went = await send();
      if (went === "lost") note("WAYOUT", page.step, "Send was pressed three times and no send went to the server");
      if (went) { sent = true; break; }
    }
    if (!sent) { note("WAYOUT", page.step, "no draft in the seeded world shows a Send to press"); await fault(""); continue; }
    await again(page, before, t0, sendWords, page.step);
    await wait(6000);
    await wayOut(page.step, want, { press: !["unknown", "reject"].includes(f) });
    if (f === "unknown") {
      const s = await look(page);
      if (!outs(s).some((x) => x.word === label("close"))) note("WAYOUT", page.step, `a send nobody can confirm offers no ${label("close")}`);
      if (outs(s).some((x) => x.word === label("try_again"))) note("WAYOUT", page.step, `${label("try_again")} on a send that may have gone - it would only say "nothing was sent again"`);
    }
    await fault("");
  }
  // the coding tool not installed, and a folder that is not there: Send to agent on a task, the coding agent chosen
  for (const f of ["nocli", "badrepo"]) {
    await fault(f); page.step = `faults ${f}`; await fresh();
    page.expect.add("/dispatch");                                      // its status is the subject here, judged by WAYOUT and WORDS
    // every task row in turn until one offers Send to agent: the rail's order follows the clock, so the first "on you" row was a task with
    // no Send to agent when CI ran just after midnight (2026-10-19) - and a coding issue whose folder the task already names when CI ran
    // after midnight UTC (2026-10-21). The rows are taken in the order of their keys: the same task at any hour
    let started = false;
    const rows = (await look(page)).rail.filter((x) => x.status === "yours").sort((a, b) => a.key.localeCompare(b.key, "en", { numeric: true }));
    // ...and for the folder that is not there, a task that names no folder first: one that names one answers "Change where the code
    // is", and CI took such a task (2026-10-22), so "Choose where the code is" was pressed nowhere and COVER failed
    if (f === "badrepo") {
      const tid = Object.fromEntries(((await srv.api("GET", "/api/funnel/pile?force=1")).items || []).filter((i) => i.tid).map((i) => [i.key, i.tid]));
      const named = new Set();
      for (const r of rows) if (tid[r.key]) { const d = await srv.api("GET", `/api/tasks/${tid[r.key]}`); if (/(^|[\s,])repo:\S/.test(String((d.task || d).Tags || ""))) named.add(r.key); }
      rows.sort((a, b) => named.has(a.key) - named.has(b.key));
    }
    for (const r of rows) {
      if (!(await openItem(page, r.key))) continue;
      // the coding agent by its own button where the row splits Send to agent in two, else Send to agent and the card's question
      if (await pressVerb(page, "coding_agent")) { started = "coding"; break; }
      if (await pressVerb(page, "regular_agent")) { started = true; break; }
    }
    if (!started) { note("WAYOUT", page.step, "no task with Send to agent to start"); page.expect.delete("/dispatch"); await fault(""); continue; }
    await wait(3000);
    // THE AGENT BOX opens first (the owner, 2026-10-23: every start asks what): the coding agent chosen in it - its answer's words -
    // where it opened on the regular agent, then the box's own Start. Nothing has started before that press.
    if (!(await page.$('[data-tq-agent-start="coding"]'))) await clickText(page, choice("agent", "coding_agent"));
    await wait(1000);
    const go = await page.$('[data-tq-agent-start="coding"]');
    if (go) await go.click(); else note("WAYOUT", page.step, "the agent box offers no coding agent to start");
    await wait(5000);
    // ...a folder that is not there is answered by where the code is - in whichever words that button says: "Change where the code is"
    // once the task names a folder, the one that was not there (CI, 2026-10-21: the census issue led the rail after midnight UTC)
    const whereCode = (x) => byLabel[x.word] === "pick_repo";
    await wayOut(page.step, [aFix, f === "nocli" ? "Connect a coding tool" : whereCode, (x) => /coding tool/i.test(x.word)]);
    page.expect.delete("/dispatch"); await fault("");
  }
  // no AI at all: a way forward that connects one. The strip that asked is gone, and the row gets no Connect an AI (the owner, 2026-10-26:
  // "if you don't get through ai setup the whole thing doesn't work"): a failed run's Result points at Connections, and the box - the
  // pill - answers anything typed with where to connect one. The rail's rows are opened in turn for the first; the box is the second
  page.step = "faults noai"; await fresh();
  const toAi = '[data-tq-run-fix], [data-tq-chat-pop]:not([hidden]) a[href^="#c"], [data-tq-chat-pop]:not([hidden]) button, .tq-chat-body a[href^="#c"], .tq-chat-body button';
  const aiWay = () => page.evaluateHandle((sel) => [...document.querySelectorAll(sel)].find((e) => e.getBoundingClientRect().width > 0
    && /connect an ai|connections/i.test(e.innerText) && (!e.matches("[data-tq-run-fix]") || /\bAI\b/.test(e.innerText))) || null, toAi);
  for (const r of (await look(page)).rail.slice(0, 16)) {
    if ((await aiWay()).asElement()) break;
    await openItem(page, r.key); await wait(1500);
  }
  if (!(await aiWay()).asElement()) {
    const box = await page.$(".tq-compose-box textarea:not([disabled])");
    if (box) { await box.click(); await box.type("what should I do with this one?"); await page.keyboard.press("Enter"); await wait(6000); }
  }
  const way = (await aiWay()).asElement();
  if (!way) note("WAYOUT", page.step, `with no AI neither a failed run's Result nor the box's answer offers a way to connect one - it said "${
    await page.evaluate(() => (document.querySelector("[data-tq-chat-pop]")?.innerText || [...document.querySelectorAll(".tq-chat-body .tq-msg")].pop()?.innerText || "nothing").replace(/\s+/g, " ").slice(0, 160))}"`);
  else { const before = await look(page), word = (await way.evaluate((e) => e.innerText.trim())).slice(0, 40),
    from = (await way.evaluate((e) => e.matches("[data-tq-run-fix]"))) ? " on a failed run's Result" : " in the box's answer"; await way.click(); await wait(3000);
    if (sig(await look(page)) === sig(before)) note("WAYOUT", page.step, `"${word}" with no AI changed nothing`);
    else walked.push(`${page.step}: offered "${word}"${from}`);
    await closePops(page); }
  // an act on a task closed behind its open card: the act is refused - with the way to reopen it, never only "reopen it first"
  page.step = "faults closed"; await fresh();
  const t = await openItem(page, (x) => x.status === "yours"), ref = t && ((await look(page)).ref.match(/TQ-(\d+)/) || [])[1];
  if (!ref) note("WAYOUT", page.step, "no task on the rail to close behind its card");
  else {
    const op = await srv.api("POST", "/api/operations", { kind: "task.complete", target: Number(ref), params: {} });
    if (op?.id) await srv.api("POST", `/api/operations/${op.id}/execute`, { version: op.version });
    page.expect.add("/remind"); page.expect.add("/execute");
    // wait for the close to reach the screen before pressing: pressed at once, Remind me was clicked as the row swapped it for
    // Reopen task, so no day picker opened - a race in this check, and which task it raced on turned on the date (CI, 2026-10-20)
    for (let i = 0; i < 20 && !(await outs(await look(page))).some((x) => /reopen/i.test(x.word)); i++) await wait(500);
    if (!(await rowHandle(page, "defer")).asElement()) await wayOut(page.step, [aFix, (x) => /reopen/i.test(x.word)]);
    else if (await pressVerb(page, "defer")) {
      await wait(1500);
      const day = (await page.$$(".MuiPopover-paper button"))[0];
      if (day) { await day.click(); await wait(4500); await wayOut(page.step, [aFix, (x) => /reopen/i.test(x.word)]); }
      else note("WAYOUT", page.step, "Remind me opened no day to pick");
    } else note("WAYOUT", page.step, `the closed task's card shows no ${label("defer")}`);
    page.expect.delete("/remind"); page.expect.delete("/execute");
  }
  // one act, one receipt: Remind me on an open task leaves ONE mark saying where it went (its card's badge) - after the chat's own read too - and no Take it
  // back anywhere (judge's UNDO); a day picked wrong is picked again
  page.step = "faults once"; await fresh();
  if (await openItem(page, (x) => x.status === "yours") && (await pressVerb(page, "defer"))) {
    await wait(1500);
    const day = (await page.$$(".MuiPopover-paper button"))[0];
    if (day) {
      await day.click(); await wait(4500);
      judge(await look(page), page.step);
      await page.evaluate(() => window.dispatchEvent(new Event("focus"))); await wait(3000);     // the chat reads the server's lines again
      const s = await look(page); judge(s, page.step);
      if (s.away !== 1) note("ONCE", page.step, `${label("defer")} left ${s.away} receipt lines in the chat, not one`);
    }
  }
  await page.close(); srv.stop();
}

// ── CARDS: a proposal cancelled then pressed; a task folded by its X then opened again ────────────────────────────────────────
async function cards() {
  const srv = await serve(3), page = await pageOn(srv, "cards");
  // A PRESS IS THE DECISION: no row button draws a card to confirm it any more (Not ours since 2026-10-21; Put it on my list, Chase them
  // and every other desk press since the 2026-10-25 sweep - assistant-is-a-router: "no confirm cards"), so the cancel path is gone. Put it
  // on my list is pressed and must run at once; a card standing after it is a confirm card, which is the dead end now
  page.step = "cards cancel";
  let card = null, pressed = false;
  for (const r of (await look(page)).rail) {
    if (!(await openItem(page, r.key)) || !(await pressVerb(page, "mine"))) continue;
    pressed = true; await wait(4000);
    card = await page.$(".tq-proposal");
    judge(await look(page), `${page.step} Put it on my list`);
    break;
  }
  if (pressed && !card) walked.push("press: Put it on my list ran at once - no card to confirm it");
  if (!pressed) note("COVER", page.step, "no item on the rail had Put it on my list to press");
  else if (card) {
    note("INLINE", page.step, "a press drew a card to confirm it - the row's button is the confirmation");
    const btns = await card.$$("button");
    const words = await Promise.all(btns.map((b) => b.evaluate((e) => e.innerText.trim())));
    const ci = words.findIndex((w) => /^(cancel|not now|no|never mind)/i.test(w));
    if (ci < 0) note("LIVE", page.step, `the proposal card has no way to cancel it: ${JSON.stringify(words)}`);
    else {
      page.expect.add("/execute");
      await btns[ci].click(); await wait(3000); walked.push(`cancel: "${words[ci]}" on a proposal card`);
      const live = await card.evaluate((c) => [...c.querySelectorAll("button")].filter((b) => !b.disabled && b.getBoundingClientRect().width > 0).map((b) => b.innerText.trim()));
      if (live.length) {
        note("LIVE", page.step, `cancelled, the card still offers ${JSON.stringify(live)}`);
        const before = await look(page); await (await card.$("button"))?.click(); await wait(3000);
        judge(await look(page), `${page.step} pressed after cancel`); void before;
      }
      page.expect.delete("/execute");
    }
  }
  // fold the task on the table by its X, then open it again from its folded line, then from its rail row
  page.step = "cards fold";
  await page.goto(`${srv.base}/`, { waitUntil: "load" }); await wait(5000); await clickText(page, "Walk me through my tasks"); await wait(5000);
  const t = await openItem(page, (x) => x.status === "yours");
  const x = t && await page.$('[data-tq-task-page] [aria-label="Close task"]');
  if (!x) note("FOLD", page.step, `no task on the table with an X to fold it - X buttons on screen: ${JSON.stringify(await page.evaluate(() => [...document.querySelectorAll("[aria-label]")].filter((e) => e.getBoundingClientRect().width > 0).map((e) => e.getAttribute("aria-label")).filter((a) => /close|fold|put/i.test(a))))}, card: ${!!(await look(page)).card}`);
  else {
    await x.click(); await wait(2500);
    let s = await look(page);
    const line = await page.$("[data-tq-folded][role='button']");
    if (!line) note("FOLD", page.step, `folded, the task left no line to open it again (${JSON.stringify(s.folded)})`);
    else {
      await line.click(); await wait(3000); s = await look(page); walked.push("fold: reopened from its folded line");
      if (!s.card) note("FOLD", page.step, "its folded line did not open the task again");
    }
    const x2 = await page.$('[data-tq-task-page] [aria-label="Close task"]');
    if (x2) {
      await x2.click(); await wait(2500);
      // folded by its X it is put away: no row ringed "on the table", no #task in the address (UX walk, 2026-10-22) - its row opens it again
      if (await page.$("[data-tq-rail] [data-tq-key].current")) note("FOLD", page.step, "folded by its X, its rail row is still marked on the table");
      if (/#task=/.test(await page.evaluate(() => window.location.hash))) note("FOLD", page.step, "folded by its X, the address still names the task");
      const row = await page.$(`[data-tq-rail] [data-tq-key="${t.key}"]`);
      if (row) { await row.click(); await wait(3000); walked.push("fold: reopened from its rail row"); if (!(await look(page)).card) note("FOLD", page.step, "its rail row did not open the folded task again"); }
    }
  }
  // ONE COPY: two rail rows picked in turn, twice - every line in the chat once; picking between them added another "Show me" line per
  // pick, the same title twice and more (verify, 2026-10-19)
  page.step = "cards picks";
  await page.goto(`${srv.base}/`, { waitUntil: "load" }); await wait(5000); await clickText(page, "Walk me through my tasks"); await wait(5000);
  const two = (await look(page)).rail.filter((r) => !r.current).slice(0, 2);
  if (two.length < 2) note("ONCE", page.step, "fewer than two rows on the rail to pick between - the one-copy path was not walked");
  else {
    for (const r of [...two, ...two]) await openItem(page, r.key);
    walked.push("picks: two rail rows, twice each");
    const said = await page.evaluate(() => [...document.querySelectorAll(".tq-chat-body .tq-msg")].map((m) => m.innerText.replace(/\s+/g, " ").trim()).filter(Boolean));
    const twice = said.filter((t, i) => said.indexOf(t) !== i);
    if (twice.length) note("ONCE", page.step, `picked again, a line stands twice: "${twice[0].slice(0, 80)}"`);
    judge(await look(page), page.step);
  }
  await page.close(); srv.stop();
}

// ── LINKS: one router (the 2026-10-19 UI walk, G2) - a link lands on the thing it names wherever the owner is, every place the canvas
// shows is an address Back can return to, and the address follows the walk ─────────────────────────────────────────────────────────
async function links() {
  const srv = await serve(0), page = await pageOn(srv, "links");
  const open = (h) => page.evaluate((h) => { window.location.hash = h; }, h);
  // the open card of a page, and whether it is on the screen, with its words
  const one = () => page.evaluate(() => {
    const e = [...document.querySelectorAll("[data-tq-browse-one]")].find((x) => x.getBoundingClientRect().height > 0);
    const r = e?.getBoundingClientRect();
    return e ? { text: e.innerText.replace(/\s+/g, " ").slice(0, 400), inView: r.top < innerHeight - 40 && r.bottom > 40 } : null;
  });
  const knobAt = (k) => page.evaluate((k) => {
    const e = document.querySelector(`[data-tq-knob~="${k}"]`), r = e?.getBoundingClientRect();
    return e ? { inView: r.top >= 0 && r.bottom <= innerHeight } : null;
  }, k);
  // two connections the catalogue draws as cards
  const conns = ((await srv.api("GET", "/api/connectors")).data || []).filter((c) => ["gmail", "outlook", "imap", "github", "slack", "teams", "jira", "linear"].includes(c.Type));
  if (conns.length < 2) note("PLACE", page.step, `the demo has ${conns.length} connection cards to link to - the link paths were not walked`);
  else {
    const [a, b] = conns;
    page.step = "links fresh";
    await page.goto(`${srv.base}/#connector=${a.ConnectorId}`, { waitUntil: "load" }); await wait(7000);
    let o = await one();
    if (!o?.inView || !o.text.includes(a.Name)) note("PLACE", page.step, `#connector=${a.ConnectorId} opened ${o ? `"${o.text.slice(0, 60)}"${o.inView ? "" : " off the screen"}` : "no card"}, not ${a.Name}`);
    page.step = "links over Connections";
    await open(`#connector=${b.ConnectorId}`); await wait(3500);
    o = await one();
    if (!o?.inView || !o.text.includes(b.Name)) note("PLACE", page.step, `with Connections open, #connector=${b.ConnectorId} left ${o ? `"${o.text.slice(0, 60)}"` : "no card"}, not ${b.Name}`);
    walked.push("links: a connector from a fresh page and over its open page");
    page.step = "links back";
    await page.goBack(); await wait(3500);
    o = await one();
    const url = await page.evaluate(() => location.href);
    if (!url.startsWith(srv.base)) note("BACK", page.step, `Back left the app for ${url}`);
    else if (!o?.text.includes(a.Name)) note("BACK", page.step, `Back after two opens shows ${o ? `"${o.text.slice(0, 60)}"` : "no card"}, not the first (${a.Name}) - ${url}`);
    walked.push("links: Back after two opens");
  }
  // a setting by its key: the group opened over the owner's page, the knob two screens down in view - then the same from a fresh page.
  // Two groups: Assistant, and How mail is sorted, whose AI panel stands up from a spinner ABOVE its rows after they are drawn - one
  // scroll on arrival was undone by it, the "Fallback AI programs" hit landing 1,700px over its setting (verify, 2026-10-19)
  for (const grp of ["Assistant", "How mail is sorted"]) {
    const g = encodeURIComponent(grp);
    page.step = `links knob ${grp}`;
    await open(`#settings=config&group=${g}`); await wait(4000);
    const knobs = await page.evaluate(() => [...document.querySelectorAll("[data-tq-knob]")].map((e) => e.getAttribute("data-tq-knob")));
    const k = knobs[knobs.length - 1];
    if (!k) { note("PLACE", page.step, `Settings' ${grp} group drew no settings to link to`); continue; }
    await page.evaluate(() => window.scrollTo(0, 0));
    await open(`#settings=config&group=${g}&key=${k}`); await wait(3000);
    if (!(await knobAt(k))?.inView) note("PLACE", page.step, `with Settings open, a link to ${k} left it off the screen`);
    // ...and a setting the group's panel card stands for, with no row of its own ("General agent model" landed on nothing)
    const card = knobs.find((x) => x.includes(" "));
    if (card) {
      const ck = card.split(" ").pop();
      await page.evaluate(() => window.scrollTo(0, 0));
      await open(`#settings=config&group=${g}&key=${ck}`); await wait(3000);
      if (!(await knobAt(ck))?.inView) note("PLACE", page.step, `with Settings open, a link to ${ck} (a panel card's setting) left it off the screen`);
    }
    await page.goto(`${srv.base}/#settings=config&group=${g}&key=${k}`, { waitUntil: "load" }); await wait(7000);
    if (!(await knobAt(k))?.inView) note("PLACE", `${page.step} fresh`, `a link to ${k} on a fresh page left it off the screen`);
    // ...and found by Settings' own search: the hit opens its group AT the setting - on a fresh page, so the group's loads come after
    page.step = `links search ${grp}`;
    const label = await page.evaluate((k) => document.querySelector(`[data-tq-knob="${k}"] p`)?.innerText || "", k);
    await page.goto(`${srv.base}/#settings=config`, { waitUntil: "load" }); await wait(5000);
    const box = await page.$("[data-tq-browse='settings'] [data-tq-browse-search]");
    if (!box || !label.trim()) { note("PLACE", page.step, `Settings' search was not reached (box: ${!!box}, label of ${k}: "${label}")`); continue; }
    await page.evaluate(() => window.scrollTo(0, 0));
    await box.type(label.trim()); await wait(1200);
    const hit = await page.$("[data-tq-browse='settings'] [data-tq-browse-card]");
    if (!hit) note("PLACE", page.step, `searching "${label.trim()}" found nothing`);
    else { await hit.click(); await wait(3500); if (!(await knobAt(k))?.inView) note("PLACE", page.step, `the search hit for "${label.trim()}" opened its group with ${k} off the screen`); }
    walked.push(`links: a ${grp} setting by link, fresh and over Settings, and by search`);
  }
  // NOTHING: a link the How mail is sorted panel draws in its own words ("still Connections") opens its place
  page.step = "links panel";
  await page.goto(`${srv.base}/#settings=config&group=${encodeURIComponent("How mail is sorted")}`, { waitUntil: "load" }); await wait(6000);
  const before = await page.evaluate(() => location.hash);
  const pressed = await page.evaluate(() => {
    const b = [...document.querySelectorAll("[data-tq-browse='settings'] p button")].find((x) => x.innerText.trim() === "Connections");
    b?.click(); return !!b;
  });
  if (!pressed) note("PLACE", page.step, "How mail is sorted drew no Connections link in its description - the panel link was not walked");
  else { await wait(3000); const after = await page.evaluate(() => location.hash);
    if (after === before || !(await page.$("[data-tq-browse='connections']"))) note("NOTHING", page.step, `the panel's Connections link left ${after} and no Connections page`);
    walked.push("links: the How mail is sorted panel's own Connections link"); }
  // ADDRESS: Next moves the table on, and the address goes with it
  page.step = "links address";
  await page.goto(`${srv.base}/`, { waitUntil: "load" }); await wait(5000); await clickText(page, "Walk me through my tasks"); await wait(5000);
  for (let n = 0; n < 4; n++) {
    const s = await look(page), hash = await page.evaluate(() => location.hash);
    const named = (/^#task=(\d+)$/.exec(hash) || [])[1], shown = (/TQ-0*(\d+)/.exec(s.ref || "") || [])[1];
    if (named && shown && named !== shown) note("ADDRESS", page.step, `the table shows TQ-${shown} and the address still names task ${named}`);
    if (!(await pressNext(page))) break;
    await wait(4500);
  }
  walked.push("links: the address through four Nexts");
  // OVER: + New playbook asks over the list it was pressed on, and Cancel leaves that list - never SOUL.md, open under the dialog
  page.step = "links new playbook";
  // ...Playbooks left Settings for the Reports page (Reports / Workflows / Playbooks, 0.3.9.16): the shelf's own New playbook
  await page.goto(`${srv.base}/#report=playbooks`, { waitUntil: "load" }); await wait(5000);
  const pb = await page.evaluate(() => { const e = [...document.querySelectorAll("[data-tq-browse='reports'] button")].find((x) => /^\+?\s*New playbook/.test(x.innerText.trim()));
    e?.click(); return !!e; });
  if (!pb) note("OVER", page.step, "Reports → Playbooks drew no New playbook to press");
  else {
    await wait(1500);
    // ...a document the owner could type into: not MUI's measuring twin of a multiline field (TextareaAutosize keeps an aria-hidden,
    // invisible copy holding "x" to size one row - it has a box, so it read as a document open under the dialog on CI, 2026-10-21)
    const under = () => page.evaluate(() => [...document.querySelectorAll("textarea")].some((t) => t.getBoundingClientRect().width > 0 && !t.closest("[role=dialog]")
      && t.getAttribute("aria-hidden") !== "true" && getComputedStyle(t).visibility !== "hidden" && t.value.trim()));
    if (!(await page.$("[role=dialog]"))) note("NOTHING", page.step, "+ New playbook opened no dialog");
    if (await under()) note("OVER", page.step, "+ New playbook drew a document under its dialog");
    await clickText(page, "Cancel"); await wait(1500);
    if (await under()) note("OVER", page.step, "Cancel on + New playbook left a document open to edit");
    walked.push("links: + New playbook asked over its list, and cancelled back to it");
  }
  await page.close(); srv.stop();
}

// PHONE: nothing runs off a 390px screen and no word stands a letter a line - read on whatever the page shows now
const phoneLook = (page) => page.evaluate(() => ({ wide: document.scrollingElement.scrollWidth - innerWidth,
  stacked: [...document.querySelectorAll("body *")].filter((e) => {
    if (![...e.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 6)) return false;
    const r = e.getBoundingClientRect(), cs = getComputedStyle(e), fs = parseFloat(cs.fontSize) || 13, lh = parseFloat(cs.lineHeight) || fs * 1.4;
    // ...measured along its own lines: a label set sideways (writing-mode vertical, a drawer's tab - TaskPage DRAWER_TAB) is one line
    // running down the screen, narrow and tall by design; it stands a letter a line only where ITS lines are that short
    const side = /^vertical/.test(cs.writingMode), along = side ? r.height : r.width, across = side ? r.width : r.height;
    return along > 0 && along < 4 * fs && across >= 2.5 * lh; }).map((e) => `"${e.textContent.trim().slice(0, 24)}" ${Math.round(e.getBoundingClientRect().width)}px wide`) }));
const phoneNote = async (page, where) => { const l = await phoneLook(page);
  if (l.wide > 0) note("PHONE", page.step, `${where}: the page runs ${l.wide}px off a 390px screen`);
  for (const x of l.stacked.slice(0, 3)) note("PHONE", page.step, `${where}: ${x} - a letter a line`); };
// ── TABLE: one task, one identity (the 2026-10-19 UI walk, G1) - however a task is opened, its one rail row is ringed, the box asks
// about it, and a reload keeps it ─────────────────────────────────────────────────────────────────────────────────────────────────
const tqOf = (tid) => `TQ-${String(tid).padStart(4, "0")}`;
const ringOf = (page) => page.evaluate(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const cards = [...document.querySelectorAll("[data-tq-canvas-item] [data-tq-task-page]")].filter(vis);
  return { tid: cards.length ? cards[cards.length - 1].getAttribute("data-tq-task-page") : "",
    rows: [...document.querySelectorAll("[data-tq-rail] .tq-pile-row.current")].map((e) => ({ key: e.getAttribute("data-tq-key"), ref: (e.innerText.match(/TQ-\d+/) || [])[0] || "" })),
    box: document.querySelector(".tq-compose-box textarea")?.getAttribute("placeholder") || "",
    // ...the one-row bar's pill says "Ask…" of no task: its name, and the answer pop-up's head, say which (2026-10-27)
    name: document.querySelector(".tq-compose-box textarea")?.getAttribute("aria-label") || "",
    pop: [...document.querySelectorAll("[data-tq-chat-pop]:not([hidden]) .tq-chat-pop-head")].map((e) => e.innerText).join(" "),
    seen: [...document.querySelectorAll("[data-tq-task-page]")].map((e) => e.getAttribute("data-tq-task-page") + (vis(e) ? "" : "-")).join(",") };
});
// RING: the task opened (or whatever task landed) on the table, exactly one row ringed and it is that task's, the box about it - its
// words "Ask about this one", or the pill's name or the open pop-up's head naming that task (the one-row bar, 0.3.9.49) - up to
// 8 s, as the card lands when its pull answers
async function ringed(page, at, tid = "") {
  let r = null;
  for (let t = 0; t < 8000; t += 500) { r = await ringOf(page); if (r.tid && (!tid || r.tid === String(tid)) && r.rows.length === 1) break; await wait(500); }
  if (!r.tid) { note("RING", at, `nothing on the table${tid ? ` - ${tqOf(tid)} was opened` : ""}`); return ""; }
  if (tid && r.tid !== String(tid)) note("RING", at, `${tqOf(tid)} was opened and the table shows ${tqOf(r.tid)} (task views drawn: ${r.seen})`);
  if (r.rows.length !== 1) note("RING", at, `${r.rows.length} rail rows ringed with ${tqOf(r.tid)} on the table: ${JSON.stringify(r.rows.map((x) => x.ref || x.key))}`);
  else if (r.rows[0].ref !== tqOf(r.tid)) note("RING", at, `the ringed row is ${r.rows[0].ref || r.rows[0].key}, the card ${tqOf(r.tid)} (task views drawn: ${r.seen})`);
  if (!/^Ask about this one/.test(r.box) && !`${r.name} ${r.pop}`.includes(tqOf(r.tid)))
    note("RING", at, `${tqOf(r.tid)} is on the table and the box says "${r.box}", named "${r.name}"${r.pop ? `, its answer headed "${r.pop}"` : ""}`);
  return r.tid;
}
// HEAD: the task view's header is ONE row (the owner, 2026-10-21) - id, title, the triage pills, state and the X on one line, never
// a "Sorted as" line under it. Every child of its row on the same line, and the strip no taller than that line and its padding.
const headRows = (page) => page.evaluate(() => {
  const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const heads = [...document.querySelectorAll("[data-tq-task-head]")].filter(vis), head = heads[heads.length - 1];
  if (!head) return null;
  const row = head.firstElementChild, kids = [...row.children].filter(vis), mid = (e) => { const r = e.getBoundingClientRect(); return r.top + r.height / 2; };
  const mids = kids.map(mid);
  return { lines: mids.length && Math.max(...mids) - Math.min(...mids) > 10 ? 2 : 1, extra: head.childElementCount - 1, h: Math.round(head.getBoundingClientRect().height), row: Math.round(row.getBoundingClientRect().height),
    pills: head.querySelectorAll("[data-tq-fact], .MuiChip-root").length, status: !!head.querySelector("[data-tq-status-pill]"),
    session: !!head.querySelector('[aria-label="Back to task"]') };
});
async function headNote(page, at) {
  const h = await headRows(page);
  if (!h) return;
  if (h.extra || h.lines > 1 || h.h > h.row + 24) note("HEAD", at, `the task header is ${h.h}px - ${h.lines} line(s) on its row and ${h.extra} line(s) under it, where one row is ${h.row}px`);
}
async function table() {
  const srv = await serve(4, { linking: true }), page = await pageOn(srv, "table");
  const tasks = ((await srv.api("GET", "/api/search?q=status:open")).hits || []).filter((h) => h.tid && h.ref);
  const onNow = async () => (await ringOf(page)).tid;
  const used = [];
  // a task not on the table, and not one an earlier road opened
  const other = async () => { const cur = await onNow(); return tasks.find((t) => String(t.tid) !== cur && !used.includes(t.tid)) || null; };
  const road = async (name, open) => {
    page.step = `table ${name}`;
    const tid = await open();
    if (tid === null) return;                                  // the road was not there to walk: open() said why
    const got = await ringed(page, page.step, tid);
    await headNote(page, page.step);
    // ...and a reload keeps it - once the open has landed: a row drawn ahead of the server's answer (a rail pick whose task is read
    // ahead) is ringed at the press, and a reload in that first tenth of a second never told the server. The address is written when
    // the answer lands, so the reload waits for it - and an open that never writes it is a RING of its own
    if (got) {
      let at = "";
      for (let t = 0; t < 8000 && at !== `#task=${got}`; t += 250) { at = await page.evaluate(() => location.hash); if (at !== `#task=${got}`) await wait(250); }
      if (at !== `#task=${got}`) note("RING", page.step, `${tqOf(got)} is on the table and the address says "${at}" 8 s on - a reload would not keep it`);
    }
    if (got) { used.push(Number(got)); await page.reload({ waitUntil: "load" }); await wait(6000); await ringed(page, `${page.step} reload`, got); }
    walked.push(`table: ${name}, and reloaded`);
  };
  const railKey = (n) => page.evaluate((n) => [...document.querySelectorAll("[data-tq-rail] .tq-pile-row")]
    .find((e) => (e.querySelector(".card")?.title.match(/TQ-0*(\d+)/) || [])[1] === n)?.getAttribute("data-tq-key") || "", String(n));
  await road("rail", async () => {
    const cur = await onNow();
    const n = await page.evaluate((cur) => [...document.querySelectorAll("[data-tq-rail] .tq-pile-row:not(.current)")]
      .map((e) => (e.querySelector(".card")?.title.match(/TQ-0*(\d+)/) || [])[1]).find((n) => n && n !== cur) || "", cur);
    if (!n) { note("RING", page.step, "no task row on the rail to open - the rail road was not walked"); return null; }
    await page.click(`[data-tq-rail] .tq-pile-row[data-tq-key="${await railKey(n)}"] .card`);
    return Number(n);
  });
  await road("Next", async () => {
    // Next lands what the walk has next: the first task it lands is checked
    for (let n = 0; n < 4; n++) { const was = await onNow(); if (!(await pressNext(page))) break; await wait(4500); const now = await onNow(); if (now && now !== was) return Number(now); }
    note("RING", page.step, "four Nexts put no task on the table - the Next road was not walked"); return null;
  });
  await road("Board open", async () => {
    await page.click('[data-tq-view="board"]'); await wait(3500);
    const n = await page.evaluate((cur) => [...document.querySelectorAll("[data-tq-board-task]")].map((e) => e.getAttribute("data-tq-board-task"))
      .find((n) => n !== cur) || "", await onNow());
    if (!n) { note("RING", page.step, "the Board drew no task to open - the Board road was not walked"); await page.click('[data-tq-view="chat"]'); return null; }
    await page.click(`[data-tq-board-task="${n}"]`);
    return Number(n);
  });
  await road("deep link", async () => {
    const t = await other(); if (!t) return null;
    await page.goto(`${srv.base}/#task=${t.tid}`, { waitUntil: "load" }); await wait(6000);
    return t.tid;
  });
  await road("search", async () => {
    const t = await other(); if (!t) return null;
    await page.click("[data-tq-search-open]"); await page.waitForSelector("[data-tq-search-input]"); await wait(300);
    await page.keyboard.type(t.ref);
    await page.waitForSelector("[data-tq-search-settled='true']", { timeout: 8000 }).catch(() => {});
    await page.keyboard.press("Enter");
    return t.tid;
  });
  let typed = null;
  await road("typed ref", async () => {
    typed = await other(); if (!typed) return null;
    const box = await page.$(".tq-compose-box textarea");
    if (!box) { note("RING", page.step, "no box to type in - the typed road was not walked"); return null; }
    await box.type(`show me ${typed.ref}`); await page.keyboard.press("Enter"); await wait(6000);
    return typed.tid;
  });
  await road("reply link", async () => {
    // the link the answer above drew, pressed once the table has moved on
    if (!typed) return null;
    await pressNext(page); await wait(4500);
    const a = await page.$(`.tq-chat-body a[href="#task=${typed.tid}"]`);
    if (!a) { note("RING", page.step, `the answer to "show me ${typed.ref}" drew no link to it - the reply-link road was not walked`); return null; }
    await a.click();
    return typed.tid;
  });
  await road("end chip", async () => {
    for (let n = 0; n < 40; n++) {
      const words = (await look(page)).verbs.map((v) => v.word), w = words.find((x) => x.startsWith("Open TQ"));
      if (w) { await clickText(page, w, "[data-tq-row]"); return Number(w.match(/TQ-0*(\d+)/)[1]); }
      // ...a run of notices read together moves on by its own word, as the walk pass presses it
      if (words.includes(label("next", "batch"))) await clickText(page, label("next", "batch"), "[data-tq-row]");
      else if (!(await pressNext(page))) break;
      await wait(3500);
    }
    note("RING", page.step, "Next never reached the walk's end chips - the end-chip road was not walked"); return null;
  });
  // ...and the header on a phone: still one row - the title and the status pill, no chips (the redesign, owner-approved 2026-10-21: what
  // triage made of it is the last line of From, and the one pill is the rail's own status)
  page.step = "table phone header";
  await page.setViewport({ width: 390, height: 844 });
  for (const t of tasks.slice(0, 3)) {
    await page.goto(`${srv.base}/#task=${t.tid}`, { waitUntil: "load" }); await wait(6000);
    const h = await headRows(page);
    if (!h) { note("HEAD", page.step, `${t.ref} opened at 390px and no task header was drawn`); continue; }
    if (!h.status) note("HEAD", page.step, `${t.ref} at 390px: the header carries no status`);
    if (h.pills) note("HEAD", page.step, `${t.ref} at 390px: the header carries ${h.pills} chip(s) beside its title`);
    await headNote(page, `${page.step} ${t.ref}`); await phoneNote(page, `${t.ref}'s task header`);
    walked.push(`table: ${t.ref}'s header at 390px`);
  }
  await page.close(); srv.stop();
}

// THE ONE SEARCH (the 2026-10-19 UI walk, G9): what Enter opens is what was typed, the count is the whole count, a setting or a
// connection is found and opened, focus goes to what opened, and a phone has the box
async function searchPass() {
  const srv = await serve(0), page = await pageOn(srv, "search");
  const find = async (q) => (await srv.api("GET", `/api/search?q=${encodeURIComponent(q)}`)) || {};
  const tasks = ((await find("status:open")).hits || []).concat((await find("status:done")).hits || []);
  const box = async () => { await page.click("[data-tq-search-open]"); await page.waitForSelector("[data-tq-search-input]"); return wait(300); };
  const settledOn = () => page.waitForSelector("[data-tq-search-settled='true']", { timeout: 8000 }).then(() => true, () => false);
  // the task on the table, and focus in its box (its terminal's own box counts) - not on the search bar, nor on the box before
  const opened = (tid, ms = 8000) => page.waitForFunction((t) => {
    const e = document.querySelector(`[data-tq-canvas-item] [data-tq-task-page="${t}"]`)?.closest("[data-tq-canvas-item]");
    return e && !document.querySelector("[data-tq-search-input]") && e.contains(document.activeElement);
  }, { timeout: ms }, tid).then(() => held(`task ${tid}'s box`, (t) => document.querySelector(`[data-tq-canvas-item] [data-tq-task-page="${t}"]`)
    ?.closest("[data-tq-canvas-item]"), tid), async () => page.evaluate((t) => {
    const e = document.querySelector(`[data-tq-canvas-item] [data-tq-task-page="${t}"]`), a = document.activeElement;
    return document.querySelector("[data-tq-search-input]") ? "the search stayed open" : !e ? `nothing put task ${t} on the table`
      : `focus is on ${a?.getAttribute("aria-label") || a?.className || a?.tagName}, not in task ${t}'s box`;
  }, tid));
  // ...and still there once the page has finished drawing it (verify, 2026-10-20): a task already on the table was focused on the
  // first frame, its card drew again, and focus fell to the page
  const where = () => page.evaluate(() => { const a = document.activeElement;
    return a === document.body || !a ? "the page itself" : a.getAttribute("aria-label") || a.getAttribute("placeholder") || a.tagName; });
  const held = async (what, fn, arg) => { await wait(2500); return (await page.evaluate((f, x) => { const e = new Function(`return (${f})`)()(x);
    return !!e && e.contains(document.activeElement); }, fn.toString(), arg)) ? "" : `focus left ${what} for ${await where()} as the page drew`; };
  // a cancel gives focus back: Esc over the search, from the chat's composer, and the words typed next land in the composer
  page.step = "search esc";
  // ...the composer by its place, not its words: the one-row bar's pill says "Ask…" (0.3.9.49)
  const comp = await page.$(".tq-compose-box textarea:not([disabled])");
  if (!comp) note("SEARCH", page.step, "no chat composer to type in");
  else {
    await comp.focus(); await page.keyboard.down("Control"); await page.keyboard.press("k"); await page.keyboard.up("Control");
    await page.waitForSelector("[data-tq-search-input]", { timeout: 4000 }).catch(() => {});
    await wait(300); await page.keyboard.press("Escape"); await wait(600);
    const back = await page.evaluate(() => document.activeElement?.matches?.(".tq-compose-box textarea"));
    if (!back) note("SEARCH", page.step, `Esc from the search left focus on ${await where()}, not the composer it was in`);
    walked.push("search: Esc gives focus back");
  }
  // the race: one word typed and answered, then another task's id typed over it and Enter at once - its task opens, not the first's
  const [a, b, c] = tasks.filter((t) => /\w{4,}/.test(t.title)).slice(-3);
  if (!c) note("SEARCH", page.step, `the demo has ${tasks.length} tasks to search for - the Enter race was not walked`);
  else {
    page.step = "search enter race";
    await box();
    await page.type("[data-tq-search-input]", a.title.match(/\w{4,}/)[0]);
    if (!(await settledOn())) note("SEARCH", page.step, `"${a.title}" was never answered`);
    await page.keyboard.down("Control"); await page.keyboard.press("a"); await page.keyboard.up("Control");     // a triple click selects nothing here
    await page.keyboard.type(b.ref); await page.keyboard.press("Enter");
    const why = await opened(b.tid);
    if (why) note("SEARCH", page.step, `${b.ref} typed over an answered word and Enter pressed at once: ${why}`);
    // ...and Enter before any answer came back at all: held, then spent on the answer
    page.step = "search enter early";
    await box();
    await page.keyboard.type(c.ref); await page.keyboard.press("Enter");
    const early = await opened(c.tid);
    if (early) note("SEARCH", page.step, `${c.ref} typed and Enter pressed before any answer: ${early}`);
    // ...and a task that is already on the table: its box takes focus, and keeps it
    page.step = "search same task";
    await box();
    await page.keyboard.type(b.ref); await settledOn(); await page.keyboard.press("Enter");
    const same = await opened(b.tid);
    if (same) note("SEARCH", page.step, `${b.ref} picked while it was on the table: ${same}`);
    walked.push("search: Enter over an earlier answer and before any, and on a task already open");
  }
  // the count: a word on more tasks than the list holds says how many there were, never "8 of 8"
  page.step = "search totals";
  const words = [...new Set(tasks.flatMap((t) => t.title.toLowerCase().match(/[a-z]{3,}/g) || []))];
  let big = null;
  for (const w of words) { const r = await find(w); if ((r.totals?.task || 0) > r.hits.filter((h) => h.type === "task").length) { big = { w, r }; break; } }
  if (!big) walked.push("search: no word in the demo is on more tasks than the list holds - the count past the cap is the unit tests'");
  else {
    await page.keyboard.press("Escape"); await wait(300); await box();
    await page.type("[data-tq-search-input]", big.w); await settledOn();
    const foot = await page.$eval("[data-tq-search-count]", (e) => e.innerText).catch(() => "");
    const [shown, of] = (foot.match(/(\d+) of (\d+)/) || []).slice(1).map(Number);
    if (!(of > shown)) note("SEARCH", page.step, `"${big.w}" is on ${big.r.totals.task} tasks and the list says "${foot}"`);
    walked.push("search: the count past the cap");
  }
  // a connection by its name: found, and Enter opens its card on the canvas
  page.step = "search connection";
  await page.keyboard.press("Escape"); await wait(300); await box();
  await page.type("[data-tq-search-input]", "Gmail"); await settledOn();
  if (!(await page.$("[data-tq-search-hit='con:gmail']"))) note("SEARCH", page.step, `"Gmail" did not find the Gmail connection`);
  else {
    await page.keyboard.press("Enter"); await wait(4000);
    const card = await page.evaluate(() => {
      const e = [...document.querySelectorAll("[data-tq-browse-one]")].find((x) => x.getBoundingClientRect().height > 0), r = e?.getBoundingClientRect();
      return e ? { text: e.innerText.slice(0, 200), inView: r.top < innerHeight - 40 && r.bottom > 40 } : null;
    });
    if (!card?.inView || !/gmail/i.test(card.text)) note("SEARCH", page.step, `Enter on the Gmail hit left ${card ? `"${card.text.slice(0, 60)}"` : "no card"} on the canvas`);
    const why = await held("the Gmail card", () => document.querySelector("[data-tq-browse-one]"));
    if (why) note("SEARCH", page.step, `Enter on the Gmail hit: ${why}`);
    walked.push("search: a connection found by name and opened");
  }
  // a setting: its knob is in view and has focus
  page.step = "search setting";
  await box();
  await page.type("[data-tq-search-input]", "model"); await settledOn();
  const set = await page.$eval("[data-tq-search-hit^='set:']", (e) => e.getAttribute("data-tq-search-hit")).catch(() => "");
  if (!set) note("SEARCH", page.step, `"model" found no setting`);
  else {
    await page.click(`[data-tq-search-hit='${set}']`); await wait(1500);
    const why = await held(`the ${set.slice(4)} setting`, (k) => document.querySelector(`[data-tq-knob~="${k}"]`), set.slice(4));
    if (why) note("SEARCH", page.step, `the ${set} hit opened: ${why}`);
    walked.push("search: a setting found and focused");
  }
  // a page's own box, nothing found: the one line the search says, naming the page (verify, 2026-10-20: Settings said "Nothing here.")
  page.step = "search empty settings";
  await page.evaluate(() => { window.location.hash = "settings"; }); await wait(2500);
  const sb = (await page.$$("[data-tq-browse-search][aria-label='Search settings']")).pop();
  if (!sb) note("SEARCH", page.step, "#settings drew no Settings box");
  else {
    await sb.type("zzqxv"); await wait(800);
    const line = await page.$$eval("[data-tq-browse-empty]", (es) => es.map((e) => e.innerText).pop() || "");
    if (!line.startsWith("Nothing matches “zzqxv” in Settings")) note("SEARCH", page.step, `the Settings box found nothing and said "${line}"`);
    walked.push("search: a page's box says nothing matched the one way");
  }
  // a phone: the box is there, as its icon, and opens
  page.step = "search phone";
  await page.setViewport({ width: 390, height: 844 }); await wait(1500);
  const trig = await page.evaluate(() => { const e = [...document.querySelectorAll("[data-tq-search-open]")].find((x) => x.getBoundingClientRect().width > 0), r = e?.getBoundingClientRect();
    return e ? r.right <= innerWidth && r.bottom > 0 : false; });
  if (!trig) note("SEARCH", page.step, "at 390px wide there is no search to press");
  else {
    await box();
    if (!(await page.$("[data-tq-search-input]"))) note("SEARCH", page.step, "at 390px the search did not open");
    else if (b) {
      // ...and a pick there lands focus on what it opened, as on a desktop (verify, 2026-10-20: it fell to the page at 390px)
      await page.keyboard.type(b.ref); await settledOn(); await page.keyboard.press("Enter");
      const why = await opened(b.tid);
      if (why) note("SEARCH", page.step, `${b.ref} picked at 390px: ${why}`);
    }
    walked.push("search: at a phone's width");
  }
  // ...the walk's FYI card, its subjects beside each sender (they stood a letter a line), and the Your work drawer with its tooltip
  page.step = "phone";
  await page.goto(`${srv.base}/`, { waitUntil: "load" }); await wait(5000); await clickText(page, "Walk me through my tasks"); await wait(4000);
  // ...and the row at a phone's width: Next, the one move and ONE ▾ for the rest - two groups, never a band per type (the owner, 2026-10-22)
  const groups = await page.evaluate(() => [...document.querySelectorAll("[data-tq-row] .tq-arow-verbs > .tq-cl")].filter((e) => e.getBoundingClientRect().width > 0).length);
  if (groups > 2) note("PHONE", page.step, `the row at 390px has ${groups} groups - Next, the one move and its ▾ are two`);
  else walked.push("phone: the row is Next, one move and its ▾");
  for (let n = 0; n < 14 && !(await page.$(".tq-fyi-line")); n++) { if (!(await pressNext(page))) break; await wait(2500); }
  if (await page.$(".tq-fyi-line")) { await phoneNote(page, "the FYI card"); walked.push("phone: the FYI card at 390px"); }
  const rail = await page.$("[data-testid=ViewSidebarIcon]");
  if (rail) { await rail.hover(); await wait(900); await rail.click(); await wait(1500); await phoneNote(page, "Your work"); await closePops(page); walked.push("phone: Your work at 390px"); }
  await page.close(); srv.stop();
}

// BASED: an Advisor idea's "Based on <name>'s message ↗" opens THAT person's mail as its own card on the canvas - the card the walk
// shows for it - and never the old row panel (Summary / Message / Triage / Agent, "CLEAR FROM TIMELINE", "Talk it through", titled
// "undefined in chat"), which the owner had taken for gone (2026-10-20: "it should not take you there regardless"). And no road draws
// that panel: a #msg= link, fresh and over the walk, lands the same card.
const LEGACY = ["CLEAR FROM TIMELINE", "Talk it through", "undefined in chat", "No message preview available", "Dismiss once", "WORK ON IT"];
async function based() {
  const srv = await serve(0, { plant: true });
  let idea = null;
  for (let i = 0; i < 40 && !idea; i++) {
    const items = (await srv.api("GET", "/api/funnel/pile")).items || [];
    idea = items.find((x) => x.kind === "idea" && x.idea_kind === "unanswered" && x.mid);
    if (!idea) await wait(1000);
  }
  if (!idea) { note("BASED", "based", "the planted aged ask never reached the rail - the Based on link was not walked"); srv.stop(); return; }
  const mid = idea.mid, page = await pageOn(srv, "based");
  const legacy = () => page.evaluate((words) => {
    const text = document.body.innerText;
    return [...words.filter((w) => text.includes(w)), ...(document.querySelector("[data-processing-generic-detail]") ? ["the item pane"] : [])];
  }, LEGACY);
  // the card on the table, and whether it is the source mail's - its key, or a link in it back to that message
  const table = () => page.evaluate(() => {
    const vis = (e) => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
    // the newest card the chat drew: an item's live card, a task's view when the mail has a task, or an FYI or report in a task's three
    // sections (ItemSections, 2026-10-28)
    const v = [...document.querySelectorAll(".tq-chat-body .tq-msg.tq-live-card .tq-card, .tq-chat-body [data-tq-task-page], .tq-chat-body .tq-msg.tq-live-card [data-tq-item-sections]")].filter(vis).pop();
    const ring = document.querySelector("[data-tq-rail] .tq-pile-row.current")?.getAttribute("data-tq-key") || "";
    return v ? { key: ring, text: v.innerText.replace(/\s+/g, " ").slice(0, 600) } : null;
  });
  // that person's own mail: their name on it, and not the idea's line about it
  const who = idea.action?.who || "";
  const isSource = (t) => !!t && !!who && t.text.includes(who) && t.key !== idea.key && !/no answer yet/i.test(t.text);
  page.step = "based rail";
  const row = await openItem(page, idea.key);
  if (!row) note("BASED", page.step, `the aged ask ${idea.key} has no rail row to open`);
  else {
    const link = await page.evaluateHandle((mid) => [...document.querySelectorAll(`a.tq-card-link[href="#msg=${mid}"]`)]
      .filter((a) => a.getBoundingClientRect().width > 0).pop() || null, mid);
    const words = link.asElement() ? await link.evaluate((a) => a.innerText.trim()) : "";
    if (!link.asElement()) note("BASED", page.step, `the idea's card drew no "Based on" link to message ${mid}`);
    else {
      if (/^Advisor's/.test(words)) note("BASED", page.step, `the link names the Advisor ("${words}"), not the person who asked`);
      page.step = "based link";
      await link.asElement().click(); await wait(4500);
      const t = await table(), old = await legacy();
      if (old.length) note("BASED", page.step, `the Based on link drew the old row panel: ${old.join(", ")}`);
      if (!isSource(t)) note("BASED", page.step, `the Based on link left ${t ? `${t.key}: "${t.text.slice(0, 80)}"` : "nothing"} on the table, not message ${mid}'s card`);
      walked.push("based: an idea's Based on link, to the source mail's card");
    }
  }
  // ...and the same message by its address: over the walk, then on a fresh page
  for (const [step, go] of [["based hash", () => page.evaluate((h) => { window.location.hash = h; }, `#msg=${mid}`)],
    ["based fresh", () => page.goto(`${srv.base}/#msg=${mid}`, { waitUntil: "load" })]]) {
    page.step = step;
    if (step === "based hash") { await clickText(page, "Walk me through my tasks"); await wait(2000); await pressNext(page); await wait(3500); }
    await go(); await wait(step === "based fresh" ? 8000 : 4500);
    const t = await table(), old = await legacy();
    if (old.length) note("BASED", page.step, `#msg=${mid} drew the old row panel: ${old.join(", ")}`);
    if (!isSource(t)) note("BASED", page.step, `#msg=${mid} left ${t ? `${t.key}: "${t.text.slice(0, 80)}"` : "nothing"} on the table, not that message's card`);
  }
  walked.push("based: #msg= over the walk and on a fresh page");
  await page.close(); srv.stop();
}

// STOPSAVE: Stop and save on a live session opens Close out AT THE PRESS with the write-up's pending block - the server job's own stage
// - and the draft replaces that block in place, in the same card, no reload (the owner, 2026-10-21: "it looks frozen"). A world of
// its own: a plain shell as the task's session (never a real coding CLI) and a brain that takes its time, so the job is still writing
// when the block must already be up.
const PENDING_BY = 500, STOPSAVE_TITLE = "Post the hardware store charge", STOPSAVE_FAILS = "Post the fuel card statement";
async function stopsave() {
  const srv = await serve(5, { stopsave: true });
  let tid = "";
  for (let i = 0; i < 40 && !tid; i++) {
    tid = ((await srv.api("GET", "/api/tasks")).data || []).find((t) => t.Title === STOPSAVE_TITLE)?.TaskId || "";
    if (!tid) await wait(500);
  }
  if (!tid) { note("STOPSAVE", "stopsave", "the task to stop and save was never seeded"); srv.stop(); return; }
  const term = await srv.api("POST", "/api/terminals", { task_id: Number(tid) });
  if (!term?.sid) { note("STOPSAVE", "stopsave", `no shell session opened on the task: ${JSON.stringify(term).slice(0, 160)}`); srv.stop(); return; }
  const page = await pageOn(srv, "stopsave");
  await page.goto(`${srv.base}/#task=${tid}`, { waitUntil: "load" });
  let btn = null;
  for (let t = 0; t < 20000 && !btn; t += 500) { btn = (await rowHandle(page, "stop_agent")).asElement(); if (!btn) await wait(500); }
  if (!btn) { note("STOPSAVE", page.step, "the live session's task page offers no Stop and save"); await page.close(); srv.stop(); return; }
  // the press, and the clock from it: the pending block in Close out, on screen - then the draft standing where it stood
  await page.evaluate(() => { window.__tqPress = 0; window.__tqPending = 0; window.__tqDraft = 0; });
  await page.evaluate(() => {
    const vis = (e) => { const r = e?.getBoundingClientRect(); return !!r && r.width > 0 && r.height > 0 && r.top < innerHeight && r.bottom > 0; };
    const tick = () => {
      const now = performance.now(), block = document.querySelector("[data-tq-closeout] [data-tq-writeup]");
      if (!window.__tqPending && vis(block) && block.getAttribute("data-tq-writeup") === "pending") { window.__tqPending = now; window.__tqCard = block.closest("[data-tq-closeout]"); }
      const card = document.querySelector("[data-tq-closeout]");
      if (window.__tqPending && !window.__tqDraft && card && !card.querySelector("[data-tq-writeup]")
        && /Hi Gail/.test(card.innerText + [...card.querySelectorAll("textarea")].map((t) => t.value).join(" "))) {
        window.__tqDraft = now; window.__tqSame = card === window.__tqCard;
      }
      if (!window.__tqDraft) requestAnimationFrame(tick);
    };
    document.addEventListener("click", () => { if (!window.__tqPress) { window.__tqPress = performance.now(); requestAnimationFrame(tick); } }, { capture: true, once: true });
  });
  const href = await page.evaluate(() => location.href);
  await btn.click(); mark("stop_agent", page.step);
  let r = {};
  for (let t = 0; t < 40000; t += 250) { r = await page.evaluate(() => ({ press: window.__tqPress, pending: window.__tqPending, draft: window.__tqDraft, same: window.__tqSame,
    stage: document.querySelector("[data-tq-writeup]")?.getAttribute("data-tq-writeup-stage") || "", failed: !!document.querySelector('[data-tq-writeup="failed"]') }));
    if (r.draft || r.failed) break; await wait(250); }
  const ms = (a) => Math.round(a - r.press);
  if (!r.pending) note("STOPSAVE", page.step, "Stop and save drew no pending block in Close out");
  else if (ms(r.pending) > PENDING_BY) note("STOPSAVE", page.step, `Close out's pending block took ${ms(r.pending)} ms to show - over ${PENDING_BY} ms`);
  if (r.failed) note("STOPSAVE", page.step, "the write-up failed in a world where it cannot");
  else if (!r.draft) {
    const d = await srv.api("GET", `/api/tasks/${tid}`);
    note("STOPSAVE", page.step, `the draft never replaced the pending block (the write-up: ${JSON.stringify(d.writeup)}, ${(d.reviews || []).length} review(s), `
      + `last note "${String((d.comments || []).slice(-1)[0]?.Body || "").slice(0, 120)}"; Close out reads "${
        (await page.evaluate(() => document.querySelector("[data-tq-closeout]")?.innerText || "")).replace(/\s+/g, " ").slice(0, 300)}")`);
  }
  else if (!r.same) note("STOPSAVE", page.step, "the draft came in a different Close out card - the page was redrawn, not the block replaced");
  if (await page.evaluate(() => location.href) !== href) note("STOPSAVE", page.step, "the page moved while the reply was written");
  walked.push(`stopsave: pending Close out at ${r.pending ? ms(r.pending) : "-"} ms, the draft in its place at ${r.draft ? ms(r.draft) : "-"} ms`);
  await page.close();
  // ...and a write-up that fails: Close out says so with its ways on - never an empty Close out - and Try again writes it up again
  const bad = ((await srv.api("GET", "/api/tasks")).data || []).find((t) => t.Title === STOPSAVE_FAILS)?.TaskId;
  const t2 = bad ? await srv.api("POST", "/api/terminals", { task_id: Number(bad) }) : null;
  if (!t2?.sid) { note("STOPSAVE", "stopsave fails", "no shell session opened on the task whose write-up fails"); srv.stop(); return; }
  const p2 = await pageOn(srv, "stopsave fails");
  await p2.goto(`${srv.base}/#task=${bad}`, { waitUntil: "load" });
  let b2 = null;
  for (let t = 0; t < 20000 && !b2; t += 500) { b2 = (await rowHandle(p2, "stop_agent")).asElement(); if (!b2) await wait(500); }
  const failedBlock = async () => { for (let t = 0; t < 20000; t += 250) { const f = await p2.$('[data-tq-closeout] [data-tq-writeup="failed"]'); if (f) return f; await wait(250); } return null; };
  if (!b2) note("STOPSAVE", p2.step, "the live session's task page offers no Stop and save");
  else {
    await b2.click(); p2.expect.add(`/api/tasks/${bad}/wrap`);
    const f = await failedBlock();
    const ways = f ? await f.evaluate((e) => [...e.querySelectorAll("button")].map((b) => b.innerText.trim())) : [];
    if (!f) note("STOPSAVE", p2.step, "a write-up that failed left Close out without saying so");
    else if (!ways.includes(label("try_again"))) note("STOPSAVE", p2.step, `the failed write-up offers no ${label("try_again")} (it offers ${JSON.stringify(ways)})`);
    else {
      await p2.evaluate((w) => [...document.querySelectorAll('[data-tq-writeup="failed"] button')].find((b) => b.innerText.trim() === w)?.click(), label("try_again"));
      mark("try_again", p2.step);
      let again = false;
      for (let t = 0; t < 3000 && !again; t += 50) { again = !!(await p2.$('[data-tq-closeout] [data-tq-writeup="pending"]')); if (!again) await wait(50); }
      if (!again) note("STOPSAVE", p2.step, `${label("try_again")} on the failed write-up showed no pending block - the press did nothing on screen`);
      else if (!(await failedBlock())) note("STOPSAVE", p2.step, `${label("try_again")} ran, failed again, and Close out did not say so`);
      walked.push(`stopsave: a failed write-up says so in Close out, with ${ways.join(" and ")}, and ${label("try_again")} runs it again`);
    }
  }
  await p2.close(); srv.stop();
}

browser = await launch();
const phases = { walk, sweep, faults, cards, links, search: searchPass, table, based, stopsave };
for (const [name, run] of Object.entries(phases)) {
  if (!only.has(name)) continue;
  try { await run(); } catch (e) { note("CRASH", name, `the ${name} pass did not finish: ${e.message.split("\n")[0]}`); }
}
await browser.close();

// COVER: every button on the list, and each of its states, pressed - or skipped for a reason written above
if (["walk", "sweep", "faults", "cards"].every((p) => only.has(p))) for (const [v, d] of Object.entries(VERBS)) for (const k of [v, ...Object.keys(d.states || {}).map((s) => `${v}:${s}`)])
  if (!pressed.has(k) && !WALK_SKIP[k]) note("COVER", k, `"${label(...k.split(":"))}" was never pressed, and WALK_SKIP gives no reason`);

if (process.argv.includes("--json")) {
  const counts = {};
  for (const f of found) { const r = f.split(" ")[0]; counts[r] = (counts[r] || 0) + 1; }
  console.log(JSON.stringify({ counts, found, pressed: [...pressed.keys()], walked })); process.exit(0);
}
console.log(`pressed ${pressed.size}: ${[...pressed.keys()].join(", ")}`);
console.log(`walked: ${walked.join("; ")}`);
if (found.length) { console.log(`${found.length} dead end${found.length === 1 ? "" : "s"}:\n` + found.join("\n")); process.exit(1); }
console.log("no dead ends: every step had its way on");
