// THE ONE AGENT BOX (the owner, 2026-10-23: "start a agent on fyi email or any email you need to write prompt what about the email or
// attachment is the issue?? regular box should show up with voice note and attachment button ... Same for sending to agent ... a
// report"). Every door that starts an agent on an item opens the same box first - words, a voice note, pictures, which agent - and
// only its Start starts; the owner's words ride to the start and lead the agent's prompt (server tests: test_agent_box.py).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
const box = read("RunForm.jsx");
const runForm = box.slice(box.indexOf("export function RunForm"), box.indexOf("export function AgentAsk"));
const ask = box.slice(box.indexOf("export function AgentAsk"));

test("the box has the words, the mic and the paperclip, and says the one prompt wording", () => {
  // ...the ONE box (AgentSummary.PromptBox): its paperclip and mic are OneBox's own, and a voice note lands after what is typed (micInto)
  assert.match(runForm, /<PromptBox text=\{value\} setText=\{setText\} pics=\{pics\}/);
  assert.match(runForm, /const setText = onValue;/);
  assert.match(read("AgentSummary.jsx"), /export const micInto = \(put\) => \(t\) => put\(\(w\) => \(w\.trim\(\) \? `\$\{w\.trimEnd\(\)\} \$\{t\}` : t\)\);/);
  assert.match(box, /export const ASK_WHAT = MESSAGE;/);
});

test("an item's box starts nothing by itself: its Start hands the words, the pictures and the agent chosen to the caller", () => {
  assert.match(ask, /data-tq-agent-start=\{coding \? "coding" : "general"\}\s[^>]*onClick=\{start\}/);
  assert.match(ask, /text: withImages\(text\.trim\(\), pics\.paths\) \|\| ""/);
  assert.match(ask, /agent: coding \? null : run\.agent \|\| null/);
  assert.match(ask, /brain: coding \? run\.brain \|\| null : null, pick: coding && run\.brain \? null : run\.pick \|\| null, model: run\.model \|\| null/);
  // ...the coding agent offered only where a coding tool is connected, the other kind one press away
  assert.match(ask, /const coding = canCode && !general;/);
  assert.match(ask, /\{canCode && <Button size="small" variant="outlined" disabled=\{busy\} onClick=\{\(\) => swap\(coding\)\}>/);
  assert.match(ask, /<AgentPicker [^>]*coding=\{coding\}/);
  assert.doesNotMatch(ask, /useEffect\([^)]*onStart/, "never started on mount");
});

test("the canvas's Send to agent - a chip, the Advisor's pick - opens the box where the item is, never a proposal at the press", () => {
  const v = read("AssistantView.jsx");
  assert.match(v, /const AGENT_VERBS = \["coding_agent", "regular_agent", "coder"\];/);
  const chip = v.slice(v.indexOf("const runChip = async"), v.indexOf("const previewProposal"));
  const at = chip.indexOf("if (AGENT_VERBS.includes(c.verb) && !c.text) { askAgent(item, c.verb); return; }");
  assert.ok(at > 0 && at < chip.indexOf("proposeDirect(verb, key, true, null)"), "asked before the proposal road");
  const advice = v.slice(v.indexOf("const pressAdvice = async"), v.indexOf("const calendarDrafted"));
  assert.ok(advice.indexOf("askAgent(currentRef.current, liveVerb(a.verb))") < advice.indexOf("proposeDirect(a.verb"), "the Advisor's pick too");
  // a task on the table opens ITS box, in its agent step; anything else gets the box under its card
  assert.match(v, /if \(item\?\.tid && showsTask\(item, cardFor\(item\)\)\) \{ window\.dispatchEvent\(new CustomEvent\("tq-agent-ask"/);
  assert.match(v, /<AgentAsk inline coding=\{agentOn\.coding\}(?:[^\n]*\n){1,7}?\s+onClose=\{\(\) => setAgentOn\(null\)\} onStart=\{\(o\) => startOnItem\(agentOn\.item, o\)\} \/>/);
  assert.doesNotMatch(v, /ASK_REPORT|ASK_MEETING/, "one prompt wording on every door - a report and a meeting too (audit 2026-11-05)");
  // ...and while it is open the box is the page the pop-up Assistant reads (pageView.js): its words box and its Send to agent (2026-11-02)
  assert.match(v, /view=\{\{ item: \{ kind: agentOn\.item\.kind \|\| "item", id: agentOn\.item\.key/);
  const box = read("RunForm.jsx");
  assert.match(box, /useViewExtras\(box, view \? \{ item: view\.item, title: view\.title \} : \{\}\);/);
  assert.match(box, /data-tq-view=\{view \? "agent" : undefined\} data-tq-view-label=\{view\?\.title\}/);
  // ...and its Start is the hand-off's own proposal, carrying the words and the picks, run at once
  const start = v.slice(v.indexOf("const startOnItem = async"), v.indexOf("// ANSWER IT has nothing to send"));
  assert.match(start, /api\.post\("\/api\/concierge\/propose", \{ verb: o\.verb, key: item\.key, table: true, exact: true, text: o\.text \|\| null,/);
  assert.match(start, /agent: o\.agent \|\| null, brain: o\.brain \|\| null, pick: o\.pick \|\| null, model: o\.model \|\| null/);
  assert.match(start, /await runProposal\(/);
  assert.match(v, /onAgent=\{actions\.agent\}/);
  assert.match(v, /agent: startOnItem,/);
});

test("the message card's hand-off opens the box and its start carries the words", () => {
  const cards = read("assistantCards.jsx");
  const msg = cards.slice(cards.indexOf("export function MessageCard"), cards.indexOf("// the day, at the top of a new chat"));
  assert.match(msg, /const handIt = agentRuns\(card\) \|\| !\(card\.mid \|\| card\.tid\) \? null : \(\) => setAskOpen\(true\);/);
  assert.match(msg, /\{askOpen && <AgentAsk [^\n]*\n\s+onClose=\{\(\) => setAskOpen\(false\)\} onStart=\{handOver\} \/>\}/);
  assert.match(msg, /kind: o\.kind, agent: o\.agent \|\| null, brain: o\.brain \|\| null, pick: o\.pick \|\| null, model: o\.model \|\| null, instruction: o\.text \|\| null/);
  assert.match(msg, /instructions: o\.text \|\| null/);
});

test("the Game's hand-off opens the same box", () => {
  const g = read("gameItem.jsx");
  assert.match(g, /onClick=\{\(\) => setAsk\(coding\)\}>🤖/);
  assert.match(g, /<AgentAsk inline coding=\{ask\}/);
  assert.match(g, /if \(AGENT_VERBS\.includes\(c\.verb\) && onAgent\) \{ onAgent\(c\.verb\); return null; \}/);
  assert.match(g, /text: o\.text \|\| null,/);
});
