import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = (name) => fs.readFileSync(path.join(process.cwd(), "src", name), "utf8");

test("the assistant offers ONE Send to agent, and the card asks coding or not", () => {
  const cards = src("assistantCards.jsx");
  // the card is what the thing IS; the verbs are the chat line's (concierge.CHIPS)
  assert.doesNotMatch(cards, /"Coding agent"/);
  assert.doesNotMatch(cards, /"Regular agent"/);
  const py = fs.readFileSync(path.join(process.cwd(), "..", "taskuary", "concierge.py"), "utf8");
  // one button (the owner, 2026-09-25) - and still two separate roads, never one guessed kind: the card's own
  // question offers both, triage's pick first (concierge.ALTS)
  assert.match(py, /'regular_agent': 'Send to agent'/);
  assert.match(py, /'mine', 'regular_agent', 'not_ours'/);
  assert.match(py, /'agent': \(\('coder', 'A coding agent'\), \('regular_agent', 'A non-coding agent'\)\)/);
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
  const before = mount.indexOf("const updateProvider");
  assert.ok(before > 0, "the provider change (which does start a session) comes after the mount");
  assert.doesNotMatch(mount.slice(0, before), /assistant\/session/);
});

test("every live agent ends the same way, and never without being written up", () => {
  const tasks = src("TasksView.jsx");
  const start = tasks.indexOf("{term?.alive && (", tasks.indexOf("Agent running"));
  const controls = tasks.slice(start, tasks.indexOf("{report &&", start));
  assert.ok(start >= 0);
  // Three controls all ended the session and differed only in what they wrote down - a result, a
  // handover note, or nothing - which is unreadable as three labels (the owner, 2026-09-16: "save
  // result vs end session vs stop session???"). One ending now, and it writes up either way.
  assert.match(controls, />Save and end session<\/Button>/);
  // and NO way to end one without that write-up (the owner: "meaning no stop without saving")
  assert.doesNotMatch(controls, />Stop session<\/Button>/);
  assert.doesNotMatch(controls, /handover<\/Button>/);
  // the parity this has always guarded: the ending is not gated on a coding session, so a general
  // agent ends exactly as a coding one does
  assert.doesNotMatch(controls, /liveCodingSession && <Button[^>]*>Save and end session/);
});

test("task references use readable sans-serif digits", () => {
  const tasks = src("TasksView.jsx");
  const ui = src("ui.jsx");
  assert.match(tasks, /fontVariantNumeric: "tabular-nums"/);
  assert.match(ui.slice(ui.indexOf("export const RefChip"), ui.indexOf("export const ActionChip")),
    /IBM Plex Sans/);
});

test("the New sheet reports what the dispatch answered, not what it hoped", () => {
  // a coding task with no checkout comes back needs_repo with started:false, and this said
  // "is on it in a live session" over the top of it (the owner, 2026-09-22)
  const sheet = src("NewSheet.jsx");
  assert.match(sheet, /import \{ outcomeOf \}/);
  assert.match(sheet, /outcomeOf\(out\)\.text/);
  assert.doesNotMatch(sheet, /setOk\(`\$\{data\.ref\} — \$\{agent\}/);   // never the hoped-for sentence
});

test("the brain picked in the New sheet and on the task page travels with the role", () => {
  assert.match(src("NewSheet.jsx"), /brain: brain \|\| null/);
  assert.match(src("TasksView.jsx"), /brain: run\.brain \|\| null/);
});
