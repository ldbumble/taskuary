import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("a running turn says so, whichever backend is answering", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.ok(view.includes("<ThreadPrimitive.If running>"), "the running thread must render something");
  // Both roads still say it - the pane that is streaming the answer, and a turn running without us.
  // The DOCK says it with the dots it always had; a work window says it with the band, which also
  // says who is working, what it is doing now, how long, and what it has got (agentWork.js).
  // ...the band only while nothing else on screen shows it working: once its steps stream into the thread the dots alone
  // say it is alive (the owner, 2026-10-14: "no need ... to tell you what it's doing in 2 places")
  assert.match(view, /const atWork = dock \|\| work\?\.steps\?\.length \? <Thinking[\s\S]*?: <AgentBand/);
  assert.match(view, /<ThreadPrimitive\.If running>\s*\{atWork\}/);
  assert.match(view, /\{serverBusy && atWork\}/);
  assert.match(view, /serverBusy=\{busy\} provider=\{session\?\.provider \|\| pickedLabel\} name=\{name\}/);
  assert.match(view, /const Thinking = \(/);
  assert.match(view, /const AgentBand = \(\{ name, provider, work, since, starting = "" \}\)/);
});

test("the band reports the turn, and never invents a total it was not told", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.match(view, /work\.steps\.length > 1 && <span className="tq-aui-band-step"> — step \{work\.steps\.length\}/);
  assert.doesNotMatch(view, /of about/);                                            // no made-up denominator
  assert.match(view, /elapsedText\(now - since\)/);                                 // the turn's clock
  assert.match(view, /what it has so far/);
  const css = read("generalWorkspace.css");
  assert.match(css, /\.tq-aui-band \{/);
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
  assert.match(view, /const busy = !!data\?\.session\?\.busy \|\| !!data\?\.starting;/);
  const poll = view.slice(view.indexOf("const busy ="), view.indexOf("const pasted ="));
  assert.match(poll, /if \(!busy\) return undefined;/, "one definition of work in flight drives the poll");
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
test("the general agent's question is drawn in its canvas with a box that answers it", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.match(view, /\{!dock && asking && <AgentAsks asking=\{asking\} name=\{name\} onAnswer=\{onAnswer\} \/>\}/);
  assert.match(view, /setOwnPrompt\(\{ id: `ask:\$\{req\.request_id\}`, text \}\)/);
  assert.match(view, /api\.post\(`\/api\/tasks\/\$\{task\.TaskId\}\/worker\/answer`, \{ request_id: req\.request_id, text \}\)/);
  assert.match(view, /data\.asking\.request_id !== answered/, "answered here, it goes at once - the snapshot still carries it");
});

test("the working dots animate from the general workspace's own stylesheet", () => {
  const css = read("generalWorkspace.css");
  assert.match(css, /\.tq-aui-thinking i \{[^}]*animation: tqAuiThinking/);
  assert.match(css, /@keyframes tqAuiThinking/);
});

test("a turn that died shows its reason, with no answer of its own to hang it on", () => {
  const view = read("GeneralWorkspace.jsx");
  assert.match(read("agentSteps.js"), /kind: "error", summary: `⚠ \$\{e\.detail\?\.result/);   // the reason is built
  // ...and it reaches the page. The trail used to be folded into the newest ASSISTANT message,
  // so a turn that filed no answer folded it into nothing and the chat showed the question,
  // no reply, and no reason at all (TQ-0496).
  assert.match(view, /const tail = out\[out\.length - 1\];/);
  assert.match(view, /tail\?\.role === "assistant"[\s\S]{0,400}?out\.push\(\{ id: `trace-/);
  assert.doesNotMatch(view, /for \(let i = out\.length - 1; i >= 0; i -= 1\)/);
});
