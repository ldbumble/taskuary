import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (name) => fs.readFileSync(path.join(process.cwd(), "src", name), "utf8");

test("the assistant offers an explicit coding or regular agent choice, in ONE place", () => {
  const cards = src("assistantCards.jsx");
  // the card is what the thing IS; the verbs are the chat line's (concierge.CHIPS)
  assert.doesNotMatch(cards, /"Coding agent"/);
  assert.doesNotMatch(cards, /"Regular agent"/);
  const py = fs.readFileSync(path.join(process.cwd(), "..", "taskuary", "concierge.py"), "utf8");
  assert.match(py, /'coder': 'Hand it to a coding agent'/);      // still two separate roads...
  assert.match(py, /'regular_agent': 'Hand it to an agent'/);    // ...never one guessed kind
  assert.match(py, /'coder', 'mine', 'not_ours'/);               // both offered on a message
  assert.doesNotMatch(cards, /kind: coding \? "coding" : "general"/);
});

test("the timeline handoff asks for an agent type before Send is enabled", () => {
  const ui = src("ui.jsx");
  const handoff = ui.slice(ui.indexOf("export const SendToAgent"), ui.indexOf("export const TASK_STATES"));
  assert.match(handoff, /Which kind of agent\?/);
  assert.match(handoff, /Coding agent/);
  assert.match(handoff, /Regular agent/);
  assert.match(handoff, /disabled=\{busy \|\| !agentKind\}/);
  assert.match(handoff, /\{ kind: agentKind/);
});

test("a handed-off agent workspace is folded in the main Assistant by default", () => {
  const cards = src("assistantCards.jsx");
  const agentCard = cards.slice(cards.indexOf("export function AgentCard"), cards.indexOf("export function MeetingCard"));
  assert.match(agentCard, /useState\(false\)/);
  assert.match(agentCard, /Open agent workspace/);
});

test("opening a general task reads state without starting an agent", () => {
  const workspace = src("GeneralWorkspace.jsx");
  const mount = workspace.slice(workspace.indexOf("useEffect(() => {", workspace.indexOf("export function GeneralWorkspace")));
  assert.match(mount, /api\.get\(`\/api\/tasks\/\$\{task\.TaskId\}\/assistant`\)/);
  assert.doesNotMatch(mount.slice(0, mount.indexOf("const chooseView")), /assistant\/session/);
});

test("every live agent has the same pause, finish, and stop controls", () => {
  const tasks = src("TasksView.jsx");
  const start = tasks.indexOf("{term?.alive && (", tasks.indexOf("Agent running"));
  const controls = tasks.slice(start, tasks.indexOf("{report &&", start));
  assert.ok(start >= 0);
  assert.match(controls, />Save result & end session<\/Button>/);      // relabelled: saving a result is not completing the task (PW-218)
  assert.match(controls, />End session & save handover<\/Button>/);    // relabelled: nothing is paused in place (PW-219)
  assert.match(controls, />Stop session<\/Button>/);
  assert.doesNotMatch(controls, /liveCodingSession && <Button[^>]*>Save result & end session/);
});

test("task references use readable sans-serif digits", () => {
  const tasks = src("TasksView.jsx");
  const ui = src("ui.jsx");
  assert.match(tasks, /fontVariantNumeric: "tabular-nums"/);
  assert.match(ui.slice(ui.indexOf("export const RefChip"), ui.indexOf("export const ActionChip")),
    /IBM Plex Sans/);
});
