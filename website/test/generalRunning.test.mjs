import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("a running turn says so, whichever backend is answering", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.ok(view.includes("<ThreadPrimitive.If running>"), "the running thread must render something");
  // Both roads still say it - the pane that is streaming the answer, and a turn running without us.
  // The DOCK says it with the dots it always had; a work window with ONE QUIET LINE, "Working on this…" (the closeout-in-chat spec,
  // 2026-11-04) - folded over the turn's steps once they stream in (WorkSteps), on its own until then (AtWork -> AgentBand)
  assert.match(view, /const atWork = dock \? <Thinking provider=\{provider\} \/> : <AtWork name=\{name\}/);
  assert.match(view, /<ThreadPrimitive\.If running>\s*<WhileLines feed=\{feed\} waits=\{false\}>\{chat \? <BareHead or=\{pressedAt\}>\{atWork\}<\/BareHead> : atWork\}<\/WhileLines>/);
  assert.match(view, /\{dock \? serverBusy && atWork\s*: <PendingTurn busy=\{serverBusy\}/);
  assert.match(view, /serverBusy=\{busy \|\| codingBusy\} provider=\{coding \? cc\.live\?\.cli \|\| "" : session\?\.provider \|\| pickedLabel\} name=\{name\}/);
  assert.match(view, /const Thinking = \(/);
  assert.match(view, /const AgentBand = \(\{ name, provider, work, starting = "" \}\)/);
  // ...the spin only, no words: the head says who, when and how long (the owner, 2026-11-10: "don't want the working... thing")
  const band = view.slice(view.indexOf("const AgentBand"), view.indexOf("const RunClock"));
  assert.match(band, /<i \/><i \/><i \/><\/div>/); assert.doesNotMatch(band, /Working on this|<span>\{starting\}/);
});

test("the working line reports the turn quietly, and never invents a total it was not told", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.doesNotMatch(view, /of about/);                                            // no made-up denominator
  assert.match(view, /elapsedText\(now - since\)/);                                 // the turn's clock
  assert.doesNotMatch(view, /tq-aui-band-meter|what it has so far/, "no meter or sources scrolling past - the steps fold under the line");
  const css = read("generalWorkspace.css");
  assert.match(css, /\.tq-aui-working \{/);
  // ...and the six identical COMPLETEs go quiet, except in the dock, which is left as it was
  assert.match(css, /\.tq-aui-tool-complete summary em \{ display: none; \}/);
  assert.match(css, /\.tq-aui-dock \.tq-aui-tool-complete summary em \{ display: block; \}/);
});

test("a turn the SERVER started before this pane opened is still a turn in flight", () => {
  // The walk's opening turn is dispatched in the background a second or two after the task exists
  // (server._walk_opens), so the snapshot this pane loads on mount can arrive before there is any
  // session to see. Polling only while a session said "busy" left the welcome copy on screen
  // through the whole first answer - no question, no band, no browser beside it, which reads
  // exactly like a walk that never started (the owner, 2026-09-14).
  const view = read("GeneralWorkspace.jsx");
  // ...and one the page already knows of (`opening`, the task detail's `starting`) before this pane has read it (2026-11-04)
  assert.match(view, /const busy = !!data\?\.working \|\| !!data\?\.session\?\.busy \|\| !!data\?\.starting \|\| \(!dock && opening\);/);
  const poll = view.slice(view.indexOf("const busy ="), view.indexOf("const pasted ="));
  // ...and a wait on the page, which Taskuary itself can answer (a sign-in typed from the vault, 2026-11-04)
  assert.match(poll, /if \(!busy && !onPage\) return undefined;/, "one definition of work in flight drives the poll");
  assert.match(poll, /api\.get\(`\/api\/tasks\/\$\{task\.TaskId\}\/assistant`\)/);
});

test("the picker names the brain that is actually answering, not the one it opened on", () => {
  // The strip said "Azure OpenAI (API)" while codex drove the walk's browser, and that stale value
  // is what the next message would have been SENT to - handing a browser walk to a brain that
  // cannot click (the owner, 2026-09-14).
  const view = read("GeneralWorkspace.jsx");
  const at = view.indexOf("const accept = useCallback");
  const accept = view.slice(at, view.indexOf("onSession]);", at));
  assert.match(accept, /payload\?\.session\?\.pick/, "a live session's own pick wins over what the picker opened on");
  assert.doesNotMatch(accept, /setConnectorId\(\(old\) => old \|\| String\(provider\.id\)\);\s*$/m);
});

// THE QUESTION IS ON THE AGENT'S CANVAS WITH ITS ANSWER BOX (owner-approved, the UI audit's W6, 2026-10-21): "Agent asked you something"
// stood over a pane that never showed what, the question only in the rail row's hover. The conversation's own agent takes the answer as
// its next message; an agent asking from a terminal on the task gets it through the worker's answer road
test("the general agent's question is drawn in its canvas, answered by its presses or the composer", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.match(view, /\{!dock && asking && <AgentAsks asking=\{asking\} name=\{name\} onAnswer=\{onAnswer\} taskId=\{task\.TaskId\} \/>\}/);
  assert.match(view, /setOwnPrompt\(\{ id: `ask:\$\{req\.request_id\}`, text \}\)/);
  assert.match(view, /api\.post\(`\/api\/tasks\/\$\{task\.TaskId\}\/worker\/answer`, \{ request_id: req\.request_id, text \}\)/);
  assert.match(view, /ask\.request_id !== answered/, "answered here, it goes at once - the snapshot still carries it");
});

// ONE BOX TYPES THE ANSWER (the owner, 2026-11-03: "i hate this double ui. we don't need question box if we have way to answer on the
// bottom"): the card keeps the question and a CLI chooser's presses (a general agent's ask has none - general.py), and the composer
// below is where an answer is typed
test("the question card has no box of its own - the composer answers an open question", () => {
  const view = read("GeneralWorkspace.jsx");
  const card = view.slice(view.indexOf("export function AgentAsks"), view.indexOf("function AssistantThread("));
  assert.doesNotMatch(card, /<TextField|<form|>Answer<|"Answer"|placeholder=/, "no field and no Answer button on the card");
  assert.match(card, /choices\.map\(\(c\) => <Button key=\{c\}[^>]*onClick=\{\(\) => send\(c\)\}>/, "a choice still answers at a press");
  // the composer's Enter (the form's submit) and its Send both take an open question's road, never a fresh turn beside it
  assert.match(view, /<OneBox root=\{ComposerPrimitive\.Root\} rootProps=\{\{ onSubmit: answerTyped \}\}/);
  assert.match(view, /<ComposerPrimitive\.Send [^>]*onClick=\{answerTyped\}>/);
  const typed = view.slice(view.indexOf("const answerTyped"), view.indexOf("const askWords"));
  assert.match(typed, /if \(dock \|\| !asking\) return;\s*e\.preventDefault\(\);/, "only while a question is open; otherwise the composer sends as ever");
  assert.match(typed, /onAnswer\?\.\(w\)/, "the same road the card's presses take - so the card and the waiting chip clear the same way");
  assert.match(typed, /\.catch\(\(x\) => \{ setHeld\(\(h\) => h\.filter\(\(l\) => l\.id !== id\)\); setSent\(null\); c\.setText\(w\); setAskErr\(errText\(x\)\); \}\)/,
    "a refused answer keeps its words - back in the box, not held as well");
  assert.match(view, /String\(asking\.request_id \|\| ""\)\.startsWith\("signin:"\) \? "Message the agent - never your password" : "Answer the agent's question…";/);
  assert.doesNotMatch(read("generalWorkspace.css"), /tq-aui-asking-box/);
});

// NOTHING THE AGENT ASKS IS A BOX (the owner, 2026-11-11: "Stop making popups for approvals. just ask. there is no buttons anyway"): a
// request for leave drew a boxed "Agent needs your approval" over a command, with nothing to press, and words typed under it came back as
// "not_a_choice: coding is waiting on a pick". It is a line of the chat with its buttons where it has any, and words that are no answer to
// its buttons are his next line - the request stays lit
test("a request for leave is a line of the chat, and words under its buttons are his next line", () => {
  const view = read("GeneralWorkspace.jsx");
  const card = view.slice(view.indexOf("export function AgentAsks"), view.indexOf("function AssistantThread("));
  assert.doesNotMatch(card, /"tq-aui-asking"|<b>\{says\(/, "no boxed lead for an approval or a stuck turn");
  assert.match(card, /<div className="tq-aui-asked" data-tq-asking=\{asking\.request_id\}>/);
  assert.doesNotMatch(read("generalWorkspace.css"), /\.tq-aui-asking \{/);
  assert.match(view, /if \(got\?\.state !== "line"\) setAnswered\(req\.request_id\);/, "words that named no button leave the request lit");
  assert.doesNotMatch(read("ui.jsx"), /not_a_choice/, "no state code is ever read out to him");
});

// A SIGN-IN THE AGENT WAITS ON (signin.py) offers the one-time fill page beside its answers: minted by the owner's press, opened in a
// tab - or, in the desktop app with no browser of its own, by the server - and never for any other question
test("a sign-in ask offers the fill page, and no other ask does", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.match(view, /String\(asking\.request_id \|\| ""\)\.startsWith\("signin:"\)/);
  assert.match(view, /api\.post\(`\/api\/tasks\/\$\{taskId\}\/signin\/link\$\{app \? "\?open=1" : ""\}`\)/);
  // ...as a link in the question's line, not a press on a card (the owner, 2026-11-03)
  assert.match(view, /<a href="#" onClick=\{fillPage\} data-tq-signin-link=""/);
});

test("the working dots animate from the general workspace's own stylesheet", () => {
  const css = read("generalWorkspace.css");
  assert.match(css, /\.tq-aui-thinking i \{[^}]*animation: tqAuiThinking/);
  assert.match(css, /@keyframes tqAuiThinking/);
});

test("a running turn's spin stands right under its head, with no band between (the owner, 2026-11-10)", () => {
  // the live turn the thread draws has an empty body until its first word, and the spin stands outside it (AtWork under ThreadPrimitive.If
  // running): the body's padding and the turn's 18px foot made the band. Measured against this stylesheet in Chrome: head to spin 34px -> 11px,
  // the same 11px as the turn drawn from the press (PendingTurn), so nothing jumps when the thread takes the turn over
  const css = read("generalWorkspace.css");
  assert.match(css, /\.tq-aui-chat \.tq-aui-agent-body:empty \{ display: none; \}/);
  assert.match(css, /\.tq-aui-chat \.tq-aui-message:has\(\+ \.tq-aui-thinking\) \{ margin-bottom: 7px; \}/);
  assert.match(css, /\.tq-aui-chat \.tq-aui-agent > \.tq-aui-role \{ padding-top: 0; margin-bottom: 4px; \}/);
  assert.match(css, /\.tq-aui-thinking \{[^}]*margin: 0 0 10px;/);                     // the spin carries no top margin of its own
});

test("a turn that died shows its reason, with no answer of its own to hang it on", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.match(read("agentSteps.js"), /kind: "error", summary: `⚠ \$\{e\.detail\?\.result/);   // the reason is built
  // ...and it reaches the page. The trail used to be folded into the newest ASSISTANT message,
  // so a turn that filed no answer folded it into nothing and the chat showed the question,
  // no reply, and no reason at all (TQ-0496).
  // ...the newest TURN's: a press made since (a stop) stays under it (the side-by-side walk, 2026-11-11)
  assert.match(view, /const at = out\.findLastIndex\(\(m\) => !m\.press\), tail = out\[at\];/);
  assert.match(view, /tail\?\.role === "assistant"[\s\S]{0,400}?out\.splice\(at \+ 1, 0, \{ id: `trace-/);
  assert.doesNotMatch(view, /for \(let i = out\.length - 1; i >= 0; i -= 1\)/);
});
