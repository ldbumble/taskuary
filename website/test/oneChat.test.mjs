// ONE CHAT FOR EVERY TASK'S AGENT (the owner, 2026-11-06: "maybe one shared chat object for coding and regular but for coding default tool call
// backs are high and low for general agents, just summary though the settings can be changed. and diff shows up if there is branch or checkout
// stuff available. But combine the code as much as possible"). One mapper (chatStream.js) both sources feed, one component (GeneralWorkspace.jsx),
// three detail levels - and every chat fix of the day held in it. Invented people and repos only.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { chatRows, chatSource, eventsOf, rowMessages, stepsFromAcp, turnParts, workCount } from "../src/chatStream.js";
import { SHIPPED, defaultDetail, detailFor, keepOwnDetail, ownDetail } from "../src/chatDetail.js";
import { notShown, stillHeld } from "../src/heldLines.js";
import { freshNext, staleOn, withTurns } from "../src/agentSummary.js";

const read = (f) => fs.readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");
const gw = read("GeneralWorkspace.jsx"), page = read("TaskPage.jsx");
const bare = (parts) => parts.map(({ id, ...p }) => (p.steps ? { ...p, steps: p.steps.map(({ id: _, detail, ...s }) => s) } : p));
const call = (id, name, args, extra = {}) => ({ type: "tool_call", name, detail: { tool_call_id: id, args, ...extra } });
const done = (id, result = "") => ({ type: "tool_result", name: id, detail: { tool_call_id: id, result } });
const words = (t) => ({ type: "progress", name: "text", detail: t });

// ── 1. one mapper, both sources ─────────────────────────────────────────────────────────────────
// the same turn, as a general agent's run trace and as a coding CLI's log
const TRACE = [call("a", "Read", { file_path: "C:/work/ledger/store.py" }), done("a"),
  call("b", "Bash", { command: "pytest -q tests" }), done("b", "3 passed"),
  call("c", "Edit", { file_path: "C:/work/ledger/budget.py", old_string: "total = a", new_string: "total = a + tax" }), done("c"),
  call("p", "TodoWrite", { todos: [{ content: "Read the ledger", status: "completed" }, { content: "Fix the tax line", status: "in_progress" }] }), done("p"),
  words("Fixed: the total now adds the tax line.")];
const LOG = [{ k: "brief", text: "TASKUARY: work TQ-0042 ..." },
  { k: "tool", name: "Read", args: { file_path: "C:/work/ledger/store.py" } },
  { k: "tool", name: "Bash", args: { command: "pytest -q tests" }, output: "3 passed" },
  { k: "tool", name: "Edit", args: { file_path: "C:/work/ledger/budget.py" }, file: "C:/work/ledger/budget.py", edit: { parts: [{ old: "total = a", new: "total = a + tax" }] } },
  { k: "plan", items: [{ text: "Read the ledger", status: "completed" }, { text: "Fix the tax line", status: "in_progress" }] },
  { k: "said", text: "Fixed: the total now adds the tax line." }];

test("the shared mapper: a general run trace and a coding session's log give the same row shapes", () => {
  const general = turnParts(TRACE), [coding] = chatRows({ sessions: [{ sid: "s1", cli: "claude", at: "2026-11-06 09:00:00", steps: LOG }] });
  assert.deepEqual(bare(general), bare(coding.parts));
  assert.deepEqual(general.map((p) => p.type), ["work", "edit", "plan", "said"]);
  assert.equal(general[1].summary, "Edited budget.py (+1 −1)");
  assert.deepEqual(general[2].items.map((x) => x.state), ["done", "now"]);
  assert.equal(workCount(general), 3, "two steps and an edit");
  // ...and the same session over ACP is that log again (chatStream.stepsFromAcp)
  assert.deepEqual(stepsFromAcp([{ sessionUpdate: "tool_call", toolCallId: "x", kind: "read", status: "completed", locations: [{ path: "C:/work/ledger/store.py" }] }])
    .map(({ k, name, args }) => ({ k, name, args })), [{ k: "tool", name: "Read", args: { file_path: "C:/work/ledger/store.py" } }]);
});

test("a general agent that edits files gets its edit rows with diffs; a call that carries no diff stays a step", () => {
  const parts = turnParts([call("w", "Write", { file_path: "portal/new.js", content: "x\ny\n" }), done("w"),
    call("e", "Edit", { file_path: "portal/app.js" }), done("e")]);
  assert.deepEqual(parts.map((p) => p.type), ["edit", "work"]);
  assert.equal(parts[0].summary, "Wrote new.js (+2 −0)");
});

test("a coding source's rows become the one thread's messages: mail a brief, the owner's line theirs, a turn at work the live one", () => {
  const rows = chatRows({ sessions: [{ sid: "s1", at: "2026-11-06 09:00:00", live: true, steps: [...LOG, { k: "you", text: "Run the whole suite too.", at: "2026-11-06 09:01:00" },
    { k: "tool", name: "Bash", args: { command: "pytest -q" }, at: "2026-11-06 09:01:04" }] }],
    mails: [{ who: "Erin Blake", words: "The budget skips tax.", channel: "email", at: "2026-11-06 08:58:00" }], live: { working: true } });
  const ms = rowMessages(rows);
  assert.deepEqual(ms.map((m) => m.role), ["user", "assistant", "user", "assistant"]);
  assert.equal(ms[0].brief, true); assert.equal(ms[0].mail[0].who, "Erin Blake");
  assert.equal(ms[2].content[0].text, "Run the whole suite too.");
  assert.match(ms[3].id, /^live-/, "the turn at work is the live one");
  assert.match(ms[1].id, /^(?!live-)/);
  assert.equal(ms[1].content[0].name, "agent_parts");
});

// ── 2. parallel work and helpers ────────────────────────────────────────────────────────────────
// the owner, 2026-11-06: "it's spinning but not the last thing … if it's still working why are we on next thing, shouldn't it be in order? unless
// it's in parallel"
test("a helper's own steps nest under its row, and while it runs alongside later steps it says so (run trace)", () => {
  const trace = [call("h", "Task", { description: "Check live portal pages" }),
    call("k1", "WebFetch", { url: "https://portal.example/status" }, { parent: "h" }), done("k1"),
    call("k2", "Grep", { pattern: "outage" }, { parent: "h" }), done("k2"),
    call("m", "Read", { file_path: "notes/status.md" }), done("m")];
  const [work] = turnParts(trace), [helper, main] = work.steps;
  assert.equal(work.steps.length, 2, "the helper's calls are not the main agent's");
  assert.equal(helper.status, "running"); assert.equal(helper.alongside, true);
  assert.deepEqual(helper.kids.map((s) => s.summary), ["Read portal.example/status", "Searched files for 'outage'"]);
  assert.equal(main.summary, "Read status.md");
  // ...and done, the spinner goes and the row says what it was and how much it did
  const [ended] = turnParts([...trace, done("h")]);
  assert.equal(ended.steps[0].summary, "Helper: Check live portal pages (done, 2 steps)");
  assert.equal(ended.steps[0].alongside, undefined);
});

test("over ACP a helper's calls name their parent too, and nest the same way (coding source)", () => {
  const ups = [{ sessionUpdate: "user_message_chunk", content: { type: "text", text: "TASKUARY: work ..." }, _meta: { taskuary: "brief" } },
    { sessionUpdate: "tool_call", toolCallId: "h", kind: "think", title: "Task", status: "in_progress", rawInput: { description: "Check live portal pages" }, _meta: { claudeCode: { toolName: "Task" } } },
    { sessionUpdate: "tool_call", toolCallId: "k1", kind: "fetch", status: "completed", rawInput: { url: "https://portal.example/status" }, _meta: { claudeCode: { toolName: "WebFetch", parentToolUseId: "h" } } },
    { sessionUpdate: "tool_call", toolCallId: "m", kind: "read", status: "completed", locations: [{ path: "notes/status.md" }] }];
  const live = { working: true, transport: "acp" };
  const [turn] = chatRows({ sessions: [{ sid: "s", source: "acp", live: true, at: "2026-11-06 09:00:00", updates: ups }], live });
  const [helper, main] = turn.parts[0].steps;
  assert.equal(turn.parts[0].steps.length, 2);
  assert.equal(helper.alongside, true); assert.deepEqual(helper.kids.map((s) => s.summary), ["Read portal.example/status"]);
  assert.equal(main.summary, "Read status.md");
  const [ended] = chatRows({ sessions: [{ sid: "s", source: "acp", at: "2026-11-06 09:00:00", updates: [...ups, { sessionUpdate: "tool_call_update", toolCallId: "h", status: "completed" }] }] });
  assert.equal(ended.parts[0].steps[0].summary, "Helper: Check live portal pages (done, 1 step)");
  assert.match(read("AgentStepRows.jsx"), /data-tq-step-alongside="">still working in parallel</);
  assert.match(read("AgentStepRows.jsx"), /if \(step\.kids\?\.length\) return <details className=\{`\$\{cls\} tq-aui-step-helper`\} data-tq-helper="">/);
});

// ── 3. the detail level ─────────────────────────────────────────────────────────────────────────
test("the detail level: Everything for coding work, Summary for other work, Settings' defaults, and a task's own choice over both", () => {
  assert.deepEqual(SHIPPED, { coding: "everything", other: "summary" });
  assert.equal(defaultDetail("coding"), "everything"); assert.equal(defaultDetail("general"), "summary");
  assert.equal(defaultDetail("coding", { chat_detail_coding: "steps" }), "steps");
  assert.equal(defaultDetail("general", { chat_detail_other: "nonsense" }), "summary", "an unknown value is the shipped default");
  assert.equal(detailFor({ source: "general", own: "everything" }), "everything");
  const kept = new Map(), events = [];
  globalThis.window = { localStorage: { getItem: (k) => kept.get(k) ?? null, setItem: (k, v) => kept.set(k, v), removeItem: (k) => kept.delete(k) },
    dispatchEvent: (e) => events.push(e.detail) };
  keepOwnDetail(42, "steps");
  assert.equal(ownDetail(42), "steps"); assert.equal(ownDetail(43), null, "per task");
  assert.deepEqual(events.at(-1), { tid: 42, level: "steps" });
  keepOwnDetail(42, null); assert.equal(ownDetail(42), null, "back to the default");
  globalThis.window = { get localStorage() { throw new Error("blocked"); }, dispatchEvent() {} };
  assert.equal(ownDetail(42), null, "blocked storage only loses the memory");
  delete globalThis.window;
  // ...Settings has the two, and every chat's corner draws the same slider
  const knobs = JSON.parse(fs.readFileSync(new URL("../../taskuary/settings_schema.json", import.meta.url), "utf8")).knobs;
  assert.equal(knobs.chat_detail_coding.type, "detail"); assert.equal(knobs.chat_detail_other.type, "detail");
  assert.match(read("SettingsView.jsx"), /if \(m\.type === "detail"\) return <DetailSlider /);
  assert.match(page, /<HeadPop id="chat-detail" title="Chat detail" .*?><ChatDetail taskId=\{t\.TaskId\} source=\{chatSource\(t, term\)\} \/><\/HeadPop>/);
});

test("the levels draw: Summary folds every step behind one quiet line, Steps folds each group, Everything opens every call", () => {
  const tw = gw.slice(gw.indexOf("const TurnWork = "), gw.indexOf("// ...and with none of its steps on screen yet"));
  assert.match(tw, /if \(level === "summary"\) \{/);
  assert.match(tw, /<Fold k=\{`\$\{key\}:all`\} quiet label=\{stepsWord\(rest\)\}>/);
  // ...its words stay at Summary, and so does a view it showed (ViewSpec.jsx): never folded away
  assert.match(tw, /const out = \(p\) => p\.type === "view" \|\| \(!ended && p\.type === "said"\)/);
  assert.match(tw, /\{said\.map\(\(p, i\) => draw\(p, i, "everything"\)\)\}/, "its words stay at Summary");
  assert.match(tw, /p\.type === "view" \? <ViewSpec key=\{p\.id\} spec=\{p\.spec\} raw=\{p\.raw\} \/>/);
  assert.match(tw, /lvl === "everything" \? <AgentSteps key=\{p\.id\} data=\{\{ steps: p\.steps \}\} \/>/);
  assert.match(tw, /: <Fold key=\{p\.id\} k=\{`\$\{key\}:\$\{p\.id\}`\} label=\{stepsWord\(\[p\]\)\}>/);
  assert.match(gw, /const level = chat && !dock \? detailFor\(\{ source, settings: defaults, own \}\) : "steps";/);
  assert.match(gw, /data: \{ by_name: \{ \[PARTS\]: TurnWork, agent_steps: TurnWork \} \}/);
});

test("a task's source is its sessions when it is coding or a coding CLI runs on it, else the general agent's conversation", () => {
  assert.equal(chatSource({ Kind: "coding" }, null), "coding");
  assert.equal(chatSource({ Kind: "general" }, { alive: true, mode: "pty" }), "coding");
  assert.equal(chatSource({ Kind: "general" }, { alive: true, mode: "assistant" }), "general");
  assert.equal(chatSource({ Kind: "reply" }, null), "general");
});

// ── 4. one component ────────────────────────────────────────────────────────────────────────────
test("only one chat component exists: no second stream renderer, and the page never picks between two", () => {
  assert.ok(!fs.existsSync(new URL("../src/CodingChat.jsx", import.meta.url)), "CodingChat.jsx is gone");
  assert.ok(!fs.existsSync(new URL("../src/codingChat.js", import.meta.url)), "its mapper merged into chatStream.js");
  const src = new URL("../src/", import.meta.url), files = fs.readdirSync(src).filter((f) => /\.jsx?$/.test(f) && f !== "chatStream.js");   // the mapper itself defines them
  const drawing = files.filter((f) => /<ThreadPrimitive\.Messages|chatRows\(|rowMessages\(|data-tq-coding-chat/.test(fs.readFileSync(new URL(f, src), "utf8")));
  assert.deepEqual(drawing, ["GeneralWorkspace.jsx"]);
  assert.equal((page.match(/<GeneralWorkspace /g) || []).length, 1, "the task page mounts the one chat for every kind");
  assert.doesNotMatch(page, /CodingChat|liveTerminal\(term\) \? </);
});

test("the Changes popover and the landing card show only where the task works in a checkout, whatever its kind", () => {
  assert.match(page, /\{canCode && detail\?\.checkout && <HeadPop id="changes" title="Changes" wide /);
  assert.match(page, /landing=\{canCode && detail\?\.checkout && <LandingCard /);
  assert.doesNotMatch(page, /t\.Kind === "coding" && <HeadPop id="changes"/);
  assert.match(gw, /\{!dock && landing\}/);
});

// ── 5. every chat fix of the day, held in the one chat ──────────────────────────────────────────
test("regression: the owner's line shows once (heldLines notShown)", () => {
  const thread = [{ role: "user", content: [{ type: "text", text: "Run the whole suite too." }] }];
  assert.deepEqual(notShown([{ id: "h", text: "Run the whole suite too.", drawn: 0 }], thread), []);
  assert.equal(stillHeld([{ id: "h", text: "yes", after: 1 }], [{ role: "user", content: [{ type: "text", text: "yes" }] }]).length, 1, "an earlier yes never takes a new one");
  assert.match(gw, /\.\.\.notShown\(held, mineDrawn\)\]\.map\(\(l\) =>/);      // after the server's kept lines (waitingShown), each drawn once
});

test("regression: the mail that came in stays above the owner's first typed line", () => {
  const rows = chatRows({ sessions: [{ sid: "s", at: "2026-11-06 09:00:00", steps: [{ k: "you", text: "Look at this one first.", at: "2026-11-06 09:05:00" }, ...LOG.slice(1).map((s) => ({ ...s, at: "2026-11-06 09:06:00" }))] }],
    mails: [{ who: "Ray Colton", words: "Any news on the tax line?", channel: "email", at: "2026-11-06 09:02:00" }] });
  assert.deepEqual(rows.map((r) => r.kind), ["mail", "you", "turn"]);
  assert.match(gw, /return coding \? byTime\(\[\.\.\.general, \.\.\.turns\]\) : general;/);
});

test("regression: no 'Working on this…' after the turn ends or while it waits on the owner", () => {
  const ses = [{ sid: "s", source: "acp", live: true, at: "2026-11-06 09:00:00", updates: [{ sessionUpdate: "agent_message_chunk", content: { type: "text", text: "Should I go ahead?" } }] }];
  assert.equal(chatRows({ sessions: ses, live: { working: false } }).at(-1).running, false);
  assert.equal(chatRows({ sessions: ses, live: { working: true }, permissions: [{ id: 1 }] }).at(-1).waiting, true);
  assert.match(gw, /const codingBusy = coding && !!cc\.live\?\.working && !screenAsks && !perms\.length;/);
  assert.match(gw, /const calm = \(st\) => \(!now && st\.status === "running" \? \{ \.\.\.st, status: "done", alongside: false \}/, "an ended turn spins nothing");
});

test("regression: strict arrival order - a later message draws below a step still running, and steps never reorder", () => {
  const parts = turnParts([words("Running the suite."), call("t", "Bash", { command: "pytest -q" }), words("Quick update: half of it passed.")]);
  assert.deepEqual(parts.map((p) => p.type), ["said", "work", "said"]);
  assert.equal(parts[1].steps[0].status, "running");
  // ...an edit between a call and its result leaves nothing it started spinning
  const cut = turnParts([call("t", "Bash", { command: "pytest -q" }), call("e", "Edit", { file_path: "a.py", old_string: "a", new_string: "b" }), done("e"), done("t")]);
  assert.deepEqual(cut.map((p) => p.type), ["work", "edit"]); assert.equal(cut[0].steps[0].status, "done");
});

test("regression: no Terminal button; the PTY asking card shows only while the screen asks", () => {
  assert.doesNotMatch(gw, /terminal-toggle|TerminalIcon|<span>Terminal<\/span>/);
  assert.match(gw, /screenAsks = coding && !!cc\.live\?\.asking && !acp && !!cc\.live\?\.sid/);
  assert.match(gw, /\{screenAsks && <div className="tq-cc-screen" data-tq-chat-screen=""[^]*<TerminalPane sid=\{cc\.live\.sid\}/);
});

test("regression: a command's output opens under its own step", () => {
  const [w] = turnParts(eventsOf(stepsFromAcp([{ sessionUpdate: "tool_call", toolCallId: "c", kind: "execute", rawInput: { command: "pytest -q" } },
    { sessionUpdate: "tool_call_update", toolCallId: "c", status: "completed", content: [{ type: "content", content: { type: "text", text: "```\n3 passed\n```" } }] }]), false));
  assert.equal(w.steps[0].detail, "$ pytest -q\n→ 3 passed");
});

test("regression: the owner's own ask gets no reply narration (server: tests/test_own_ask_no_reply.py, both sources' prompts)", () => {
  const py = fs.readFileSync(new URL("../../tests/test_own_ask_no_reply.py", import.meta.url), "utf8");
  assert.match(py, /def test_the_reply_tools_are_not_offered_on_the_owners_own_ask/);
  assert.match(py, /def test_the_coding_seed_says_there_is_nobody_to_reply_to/);
});

test("regression: an FYI handful says '6 messages', never 'nothing to decide'", () => {
  const cards = read("assistantCards.jsx");
  assert.doesNotMatch(cards, /`\$\{plural\(n, "message"\)\} - nothing to decide`|`\$\{plural\(n, "message"\)\} · nothing to decide`/);
  assert.match(cards, /title=\{batch \? plural\(n, "message"\) : card\.title\}/);
});

test("regression: files leave the box once the send is accepted, on every road", () => {
  assert.match(gw, /if \(event\.type !== "error"\) took\(\);/);
  assert.match(gw, /const files = \[\.\.\.attachmentsRef\.current\];\s*if \(files\.length\) onClearAttachments\(files\.map\(\(a\) => a\.path\)\);/);
  assert.match(gw, /onAttachBack\(files\)/, "and come back when it did not go");
});

test("regression: one OneBox everywhere, with its paperclip and its mic", () => {
  assert.match(gw, /<OneBox root=\{ComposerPrimitive\.Root\}/);
  const one = read("AgentSummary.jsx"), box = one.slice(one.indexOf("export function OneBox"), one.indexOf("export const micInto"));
  assert.match(box, /className="tq-aui-attach"/); assert.match(box, /<MicButton /);
});

test("regression: the plan is one checklist, the newest of its turn", () => {
  const parts = turnParts([call("p1", "update_plan", { plan: ["Read the ledger", "Fix the tax line"] }), done("p1"),
    call("p2", "update_plan", { plan: [{ step: "Read the ledger", status: "completed" }, { step: "Fix the tax line", status: "in_progress" }] }), done("p2")]);
  assert.equal(parts.filter((p) => p.type === "plan").length, 1);
  assert.deepEqual(parts[0].items, [{ text: "Read the ledger", state: "done" }, { text: "Fix the tax line", state: "now" }]);
  assert.match(read("ViewSpec.jsx"), /<ul className="tq-cc-plan" data-tq-plan="" aria-label=\{label\}>/);
  assert.match(read("ViewSpec.jsx"), /PlanRow = \(\{ p, label = "The agent's plan" \}\)/);
});

test("regression: permission cards stand in the stream while the agent works", () => {
  assert.match(gw, /<PermissionCards taskId=\{task\.TaskId\} items=\{perms\} onAnswered=\{cc\.load\} \/>/);
  const thread = gw.slice(gw.indexOf("function AssistantThread("), gw.indexOf("export function GeneralWorkspace("));
  assert.ok(thread.indexOf("{!dock && cards}") < thread.indexOf("<ThreadPrimitive.If running={false}>\n          {dock && <DockActions"), "never only once it stopped");
});

test("regression: a nothing-new turn is one line", () => {
  assert.match(read("AgentSummary.jsx"), /if \(oneLine\(summary\)\) return <>\{<Box data-tq-summary="line"/);
});

test("regression: how it closed is the stream's last line, under the landing card", () => {
  const thread = gw.slice(gw.indexOf("function AssistantThread("), gw.indexOf("export function GeneralWorkspace("));
  const land = thread.indexOf("{!dock && landing}"), closed = thread.indexOf('{!dock && closedLine && <div className="tq-aui-closed" data-tq-chat-closed="">');
  assert.ok(land > 0 && closed > land && closed > thread.indexOf("data-tq-next-steps"));
});

test("regression: AI used and Talk to this agent from… sit in the header's corner, never at the chat's foot", () => {
  const head = page.slice(page.indexOf("<StatusPill status={status}"), page.indexOf("{onExpand && ("));
  assert.match(head, /<HeadPop id="ai-used" title="AI used"/);
  assert.match(head, /<HeadPop id="agent-channels" title="Talk to this agent from…"/);
  assert.doesNotMatch(gw, /<AgentChannels |<AiUsed /);
});

test("a draft stays under its own turn; a stale one is never under the newest turn's Next steps (latest-wins hook)", () => {
  const fresh = { ReviewId: 1, Status: "pending", DraftText: "Thanks Erin, on it.", turn: "m1" };
  const stale = { ...fresh, ReviewId: 2, stale: true, drafted_at: "2026-11-06 14:48:00" };
  assert.equal(freshNext([fresh]), true); assert.equal(freshNext([stale]), false); assert.equal(freshNext([]), true);
  assert.deepEqual(staleOn([fresh, stale], "m1").map((r) => r.ReviewId), [2]); assert.deepEqual(staleOn([stale], "m2"), []);
  assert.deepEqual(staleOn([{ ...fresh }], "m1"), [], "a payload without the fields draws as before");
  assert.match(gw, /next=\{custom\.folded \|\| !freshNext\(work\.reviews\) \? null : work\.next\}/);
  // ...read off the payload's `drafts` (general.draft_turns), under the message whose id is the draft's turn
  const got = withTurns([{ ReviewId: 7, Status: "pending", DraftText: "On it." }], [{ review: 7, turn: "comment-12", at: "2026-11-06 14:48:00", stale: true, before: "2026-11-06 15:00:00" }]);
  assert.deepEqual(staleOn(got, "comment-12").map((r) => r.drafted_at), ["2026-11-06 14:48:00"]);
  assert.match(gw, /reviews: withTurns\(reviews, data\?\.drafts\)/);
  assert.match(gw, /work\.next && freshNext\(work\.reviews\) && chat/);
  assert.match(gw, /nextAt\?\.next && freshNext\(nextAt\.reviews\)/);
});
