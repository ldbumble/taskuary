import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");




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

// A QUESTION IS SAID ONCE (the recorded walk, 2026-11-11): the agent's ask was the last sentence of its answer, above the reply card, and
// the page drew it again under the card - where the list says the turn said it (conversation.items `said`) only its buttons are drawn
test("a question its turn already said is not drawn a second time under the card", () => {
  const view = read("GeneralWorkspace.jsx");
  const card = view.slice(view.indexOf("export function AgentAsks"), view.indexOf("function AssistantThread("));
  assert.match(card, /if \(asking\.said && !choices\.length && !err\) return null;/);
  assert.match(card, /\{!asking\.said && <p className="tq-aui-asked-q">\{plain\}<\/p>\}/);
});

// THE CHAT STAYS AT ITS END WHEN THE BOX GROWS (the recorded walks, 2026-11-11): a long line typed made the box a line taller, the view a
// line shorter, and the chat stood 14 px behind its end - the pin watched only the list's own size
test("the chat is pinned to its end when its view gets shorter, as when its list gets longer", () => {
  assert.match(read("GeneralWorkspace.jsx"), /ro\.observe\(el\); ro\.observe\(v\);/);
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
