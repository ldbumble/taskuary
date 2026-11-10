import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

// TaskPage is the Tasks tab's task view, extracted so the assistant canvas shows the very same view (the canvas
// redesign, 2026-09-29): the list owns selection and what comes next, the view owns one task.
test("the Tasks tab draws the task through TaskPage, and the list holds no task state of its own", () => {
  const list = src("TasksView.jsx"), page = src("TaskPage.jsx");
  assert.match(list, /import TaskPage from "\.\/TaskPage\.jsx"/);
  assert.match(list, /<TaskPage taskId=\{selected\}/);
  for (const own of ["const [detail, setDetail]", "const [term, setTerm]", "const loadDetail", "WorkflowHeading number="])
    assert.ok(!list.includes(own) && page.includes(own), own);
});

test("the view takes the list's part as props - it never loads the task list itself", () => {
  const page = src("TaskPage.jsx");
  assert.match(page, /export default function TaskPage\(\{ taskId: selected, listRow = null, onListChanged, onSelect, onClose, onFinish, walkLeave = null, onReminded,/);
  assert.doesNotMatch(page, /api\.get\("\/api\/tasks", /);
  assert.match(page, /data-tq-task-page=\{selected \|\| ""\}/);
  assert.match(page, /height: canvas \? "auto" : "calc\(100vh - 118px\)"/);
});

test("Write reply calls the draft helper, not itself - the component's own openReply shadowed the import (2026-10-07)", () => {
  const s = src("TaskPage.jsx");
  assert.doesNotMatch(s, /import \{ openReply \} from "\.\/replyDraft\.js"/);
  assert.match(s, /generate \? draftReply\(api, replyMessage\.MessageId, null, null, generate === "ai"\)/);
});

// THE AUDIT FOR NON-CODERS (2026-10-17): what the task view offers and says when the person using it never wrote code
test("with no coding tool connected, Start is the general agent and nothing asks for a repository (B3)", () => {
  const page = src("TaskPage.jsx");
  // ...opening the agent box, whose one Start is the general agent's (the owner, 2026-10-23: every start asks what first)
  assert.match(page, /startHere && !canCode && !ranBefore \? \[\{ id: "start-agent"[^\n]*labelOfRow\("start-agent"\),\n\s+disabled: !!startingAgent \|\| !!noAiWhy, why: noAiWhy, run: openBox/);
  assert.match(page, /const generalOnly = handOff \|\| !canCode \|\| goalRun;/);
  assert.match(page, /\{!generalOnly && <RepoSelect/);
  assert.doesNotMatch(page, /startRepo === "" && <>/);              // no repository chosen is the agent's pick, never a hold
  // the coding agent is one press back from a hand-off - only where a coding tool is connected
  assert.match(page, /\{handOff && canCode && !goalRun && <Button[^\n]*\n[^\n]*\n[^\n]*choice\("agent", "coding_agent"\)/);
  // ...except a start already HELD for it: then choosing where the code is is the way on, whatever is connected (the walk, 2026-10-18)
  assert.match(page, /\.\.\.\(heldRepo \|\| \(!isGeneral && canCode\) \? \[\{ id: "repo"/);
  assert.match(page, /\{!isGeneral && canCode && <Button size="small" variant="outlined" sx=\{chipBtn\}/);
  assert.match(page, /\.\.\.\(!isGeneral && canCode \? \[<MenuItem key="repo"/);
});

test("one verb for removing a task: the button and its hover say Remove (U13); the press removes, no dialog", () => {
  const page = src("TaskPage.jsx");
  assert.match(page, /\{ id: "nat", group: "more", label: labelOfRow\("nat"\), run: notATask, title: NAT_TITLE/);
  assert.match(page, /Taskuary stops making tasks from messages like this; the email itself is kept, and search finds it\./);
  assert.doesNotMatch(page, /confirmNAT|<ConfirmDelete /);      // the owner, 2026-10-19: a hover over the button, not a box
  assert.doesNotMatch(page, /triage is taught|stay on the Timeline/);
});

test("From's last line says what triage made of it in one plain sentence, and the kind hints carry no coding words", async () => {
  const page = src("TaskPage.jsx");
  assert.match(page, /<Box data-tq-sorted="" title=/);
  assert.match(page, /\{triageSays\(facts, t\?\.Kind \|\| "task", triaged\.why\)\}/);
  for (const jargon of ["without a repository", "the configured CLI", "the model triage uses", "harness"]) assert.ok(!page.includes(jargon), jargon);
  const { sortedLine, triageSays } = await import("../src/taskSources.js");
  const pills = (o) => Object.entries(o).map(([key, value]) => ({ key, value }));
  assert.equal(sortedLine({ triaged: true, pills: pills({ intent: "task", who: "an agent · general", priority: "normal" }) }, "general"),
    "Sorted as: a task for an assistant · normal priority");
  assert.equal(sortedLine({ triaged: true, pills: pills({ intent: "reply", priority: "high" }) }, "reply"), "Sorted as: a reply to send · high priority");
  assert.equal(sortedLine({ triaged: false, pills: pills({ priority: "normal" }) }, "task"), "A task for you · normal priority");
  // ...and the why triage recorded rides at its end: "Sorted as: <what> · <priority> · <why>"
  assert.equal(triageSays({ triaged: true, pills: pills({ intent: "reply", priority: "normal" }) }, "reply", "  she asks for half an hour\n on a named day "),
    "Sorted as: a reply to send · normal priority · she asks for half an hour on a named day");
  assert.equal(triageSays({ triaged: true, pills: pills({ intent: "task", priority: "high" }) }, "coding", ""), "Sorted as: a task for your coding tool · high priority");
});

// THE HEADER IS ONE ROW, AND NO CHIPS (the redesign, owner-approved 2026-10-21): the ref, the title, and at the right the status - the
// rail's own mark and word for this task (railStatus.js) - then Expand and the X. What triage made of it is the last line of From.
test("the task header has no chips: its one pill is the status, the rail's own mark and word", () => {
  const page = src("TaskPage.jsx");
  const head = page.slice(page.indexOf("<Box data-tq-task-head"), page.indexOf("{/* a flex column so the terminal takes exactly"));
  assert.ok(head.length > 100, "the header strip is found");
  assert.doesNotMatch(head, /HeadPills|headPills|data-tq-fact|LifecycleChip|sortedLine\(|completionFact\(|<Chip/);
  assert.match(head, /<StatusPill status=\{status\} agent=\{agentName\(t\)\}/);
  assert.match(page, /const status = taskStatus\(\{ chat: isGeneral, queued: queuedRow, live: term\?\.alive \? \{ alive: true, waiting: agentState === AGENT\.waiting \} : null, rail, state: rowState,\n\s+closed: \["done", "dropped"\]\.includes\(t\?\.Status\), cantSend: !!pendingReview && cantSend, page: rail\?\.tid \? pageRead\(rail\.tid\) : null,\n\s+owed: pendingReview \? !String\(pendingReview\.FinalText \|\| pendingReview\.DraftText \|\| ""\)\.trim\(\) : null \}\);/);
  assert.doesNotMatch(page, /export const headPills|function HeadPills/);
});
// the owner, 2026-10-19: "never get between a coder and their coding cli" - the question drawn over the terminal behind Show details is gone
// ...and NO "Answer it" on the row (owner-approved, 2026-10-20: "we don't need that button"): the question is answered in the pane
// right above it - and no Stop and save either (the owner, 2026-11-10: "no need for stop and save button"): the x on the running turn
// is the one stop, and typing carries the work on.
test("an agent waiting on you keeps its terminal in view; its row has no Answer it and no Stop and save", () => {
  const page = src("TaskPage.jsx");
  assert.doesNotMatch(page, /id: "answer_agent"|answerAgent|askKey/);
  // ...nor under another name: a run left asking is Continued, its box showing the question, and nothing over it is filled (the owner,
  // 2026-11-10: "yes remove that button. the agent itself asks that question. Never need that button")
  for (const f of ["TaskPage.jsx", "ContinueBox.jsx", "AssistantView.jsx"]) assert.doesNotMatch(src(f), /"answer_agent"/, f);
  assert.match(page, /\{ id: "continue", group: "agent", lead: !pendingReview && !runFix && !leftAsking,/);
  assert.doesNotMatch(page, /data-tq-agent-asks|seenAsk|>Show details</);
  assert.doesNotMatch(page, /"save-end"|stopSave/);
});

// NOTHING DARKENS ITSELF: a running agent's Stop and save did (the owner, 2026-10-20), the one exception the dead-end walk excused - it is
// gone (the owner, 2026-11-10: "no need for stop and save button"), and so is the exception
test("no verb on the row darkens itself; only the Advisor's pick is dark", async () => {
  const { rowOf } = await import("../src/actionRow.js");
  const v = (id, group, extra = {}) => ({ id, group, label: id, tone: "s", promote: true, ...extra });
  const list = [v("continue", "agent", { lead: true, fill: true }), v("diff", "agent"), v("done", "more"), v("next", "next")];
  const dark = (r) => [...r.decide, ...r.agent, ...r.more].filter((x) => x.tone === "p");
  assert.deepEqual(dark(rowOf({ ref: "", list })), [], "nothing said: nothing dark");
  assert.deepEqual(dark(rowOf({ ref: "", list }, { verb: "review_changes", label: "diff" })).map((x) => x.id), ["diff"], "the Advisor's pick");
  assert.doesNotMatch(src("ActionRow.jsx"), /data-tq-own/);
  assert.doesNotMatch(readFileSync(new URL("../deadend_check.mjs", import.meta.url), "utf8"), /darkOwn|data-tq-own/);
});

test("the row puts a leading agent verb first and Mark done beside it (actionRow.rowOf)", async () => {
  const { rowOf, clustersOf } = await import("../src/actionRow.js");
  const v = (id, group, extra = {}) => ({ id, group, label: id, tone: "s", promote: true, ...extra });
  // nothing waiting on approval: the agent's lead (Continue) leads, Mark done does not take the lead from it
  const live = rowOf({ ref: "", list: [v("continue", "agent", { lead: true }), v("diff", "agent"), v("done", "more"), v("next", "next")] });
  assert.deepEqual(live.agent.map((x) => x.id), ["continue", "diff", "done"]);
  assert.equal(live.decide.length, 0);
  assert.deepEqual(clustersOf(live).find((c) => c.type === "move").shown.map((x) => x.id), ["done", "continue", "diff"], "Mark done, then the agent's lead");
  // ...a reply waiting: its Send leads (a decision), and the agent's moves wait after it
  const waiting = rowOf({ ref: "", list: [v("r1:approve", "decide", { tone: "p" }), v("diff", "agent"), v("run-another", "agent"), v("done", "more", { promote: false }), v("next", "next")] });
  assert.equal(waiting.decide[0].id, "r1:approve");
  assert.deepEqual(waiting.agent.slice(0, 2).map((x) => x.id), ["diff", "run-another"]);
});

// THE TASK'S OWN RECOMMENDED MOVE (the owner, 2026-11-09: "the agents while running should recommend actions, no assistant"): U12 brought
// the Advisor's read (/api/advice) to the Tasks tab and to a narrow window's row. Both fill the field the task's own read carries now
test("the task's own recommended move fills the Tasks tab's bar and a narrow window's row, and no Advisor is asked", () => {
  const page = src("TaskPage.jsx"), item = src("CanvasItem.jsx");
  assert.doesNotMatch(page, /api\/advice|taskAdvice|barLit|readTaskAdvice|taskNote|data-tq-task-advice/);
  assert.match(page, /const rec = notDone && detail\?\.task\?\.TaskId === selected \? detail\?\.recommended \|\| null : null;/);
  assert.match(page, /const filled = \(verb\) => liveVerb\(rec\?\.verb\) === verb;/);
  assert.match(page, /variant=\{filled\("close"\) \? "contained" : "outlined"\}/);
  for (const v of ["remove", "forward", "split"]) assert.match(page, new RegExp(`variant=\\{filled\\("${v}"\\) \\? "contained" : "outlined"\\}`), v);
  assert.match(page, /<RemindMe task=\{t\} sx=\{filled\("defer"\) \? primaryBtn : barBtn\} lit=\{filled\("defer"\)\}/);
  // ...a narrow window's row at the view's foot, with no line over it (2026-10-26, as the desk): only the Advisor's own row - an idea -
  // joins a move the row lacks
  assert.match(item, /\{phone && <div className="tq-docked">\s*\{isIdea\(card\) && <AdvisorNext advice=\{noAi \? null : advised\} onPropose=\{onPropose\} \/>\}\s*<ActionRow inline advised=\{pick\}( says=\{.*?\})? \/><\/div>\}/);
  assert.match(item, /const advised = lit \? null : adviceShown\(read, \{ key: card\.key, lane: card\.lane \}, busy\)/);
  // ...lit by the page's own read of the same item (a narrowed window kept its lit move), and it asks nothing of its own
  assert.match(item, /const read = phone && advice\?\.for === card\.key \? advice : null;/);
  assert.doesNotMatch(item, /useItemAdvice|Thinking about this one|AdviceNone/);
  assert.match(src("AssistantView.jsx"), /onPropose=\{actions\.pressAdvice\} \/>/);
});

test("a chat reply that promises a file leads with replying by email, and sending the words alone says so (U17)", () => {
  const rd = src("ReviewDecision.jsx"), page = src("TaskPage.jsx");
  assert.match(rd, /id: no\("email-file"\), label: "Reply by email with the file", tone: "p"/);
  assert.match(rd, /`\$\{sendWord\} without the file`/);
  assert.match(page, /onEmailInstead=\{\(\) => setEmailOpen\(true\)\}/);
});
