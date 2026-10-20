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
  assert.match(page, /export default function TaskPage\(\{ taskId: selected, listRow = null, onListChanged, onSelect, onClose, onFinish, onReminded,/);
  assert.doesNotMatch(page, /api\.get\("\/api\/tasks", /);
  assert.match(page, /data-tq-task-page=\{selected \|\| ""\}/);
  assert.match(page, /height: canvas \? "auto" : "calc\(100vh - 118px\)"/);
});

test("Write reply calls the draft helper, not itself - the component's own openReply shadowed the import (2026-10-07)", () => {
  const s = src("TaskPage.jsx");
  assert.doesNotMatch(s, /import \{ openReply \} from "\.\/replyDraft\.js"/);
  assert.match(s, /generate \? draftReply\(api, replyMessage\.MessageId\)/);
});

// THE AUDIT FOR NON-CODERS (2026-10-17): what the task view offers and says when the person using it never wrote code
test("with no coding tool connected, Start is the general agent and nothing asks for a repository (B3)", () => {
  const page = src("TaskPage.jsx");
  assert.match(page, /startHere && !canCode && !ranBefore \? \[\{ id: "start-agent"[^\n]*labelOfRow\("start-agent"\),\n\s+disabled: !!startingAgent, run: startGeneralAgent/);
  assert.match(page, /const generalOnly = handOff \|\| !canCode;/);
  assert.match(page, /\{!generalOnly && <RepoSelect/);
  assert.match(page, /\{!generalOnly && startRepo === "" && <>/);
  assert.match(page, /\{handOff && canCode && <Button[^\n]*\n[^\n]*Back to coding/);
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

test("the header says what triage made of it in one plain line, and the kind hints carry no coding words", async () => {
  const page = src("TaskPage.jsx");
  assert.match(page, /data-tq-sorted=""[^\n]*\{sortedLine\(facts, t\?\.Kind \|\| "task"\)\}/);
  for (const jargon of ["without a repository", "the configured CLI", "the model triage uses", "harness"]) assert.ok(!page.includes(jargon), jargon);
  // sortedLine is pure: read it out of the source and run it
  const body = page.slice(page.indexOf("const SAID ="), page.indexOf("const FACT_TONE"));
  const { sortedLine } = await import(`data:text/javascript,${encodeURIComponent(body.replace("export const sortedLine", "export const sortedLine"))}`);
  const pills = (o) => Object.entries(o).map(([key, value]) => ({ key, value }));
  assert.equal(sortedLine({ triaged: true, pills: pills({ intent: "task", who: "an agent · general", priority: "normal" }) }, "general"),
    "Sorted as: a task for an assistant · normal priority");
  assert.equal(sortedLine({ triaged: true, pills: pills({ intent: "reply", priority: "high" }) }, "reply"), "Sorted as: a reply to send · high priority");
  assert.equal(sortedLine({ triaged: false, pills: pills({ priority: "normal" }) }, "task"), "A task for you · normal priority");
});

// the owner, 2026-10-19: "never get between a coder and their coding cli" - the question drawn over the terminal behind Show details is gone
test("an agent waiting on you keeps its terminal in view, and Answer it puts the cursor there", () => {
  const page = src("TaskPage.jsx");
  assert.match(page, /\{ id: "answer_agent", group: "agent", lead: true, label: labelOfRow\("answer_agent"\), run: answerAgent/);
  assert.match(page, /const answerAgent = \(\) => setTimeout\(\(\) => termBox\.current\?\.querySelector\("textarea"\)\?\.focus\(\), 0\);/);
  assert.doesNotMatch(page, /data-tq-agent-asks|seenAsk|>Show details</);
  assert.match(page, /subState\(term\) !== "stalled"/, "a stuck agent asks nothing - it keeps its screen and Run another agent");
});

test("the Advisor's suggestion reaches the Tasks tab and a phone's own row (U12)", () => {
  const page = src("TaskPage.jsx"), item = src("CanvasItem.jsx");
  assert.match(page, /api\.get\("\/api\/advice", \{ params: \{ key: `task:\$\{id\}` \} \}\)/);
  assert.match(page, /data-tq-task-advice=""/);
  // ...with its line docked to it: the line and the button it lights are one unit at the view's foot (2026-10-19)
  assert.match(item, /\{phone && <div className="tq-docked"><div className="tq-strip" data-tq-strip=""><AdvisorNext advice=\{advised\} \/><AdviceNone advice=\{none\} \/><\/div>\s*<ActionRow inline advised=\{advised \|\| none\} \/><\/div>\}/);
  assert.match(item, /adviceShown\(read, \{ key: card\.key, lane: card\.lane \}, busy\)/);
});

test("a chat reply that promises a file leads with replying by email, and sending the words alone says so (U17)", () => {
  const rd = src("ReviewDecision.jsx"), page = src("TaskPage.jsx");
  assert.match(rd, /id: no\("email-file"\), label: "Reply by email with the file", tone: "p"/);
  assert.match(rd, /`\$\{sendWord\} without the file`/);
  assert.match(page, /onEmailInstead=\{\(\) => setEmailOpen\(true\)\}/);
});
