// WHERE A TASK IS UP TO, read from taskuary/stages.json - the same file the server's task detail and the Assistant's CANVAS read
// (taskuary/stages.py). The owner, 2026-10-26: "are these modes defined well anywhere besides the UI, how the parts of the UI display and
// what is hidden - we should define this well". Each stage names its main view, the drawer and what is in it, whether that drawer's tab
// is lit, where the Advisor's section stands and the moves it is about; the rules that pick it are the file's, in its order.
import data from "../../taskuary/stages.json" with { type: "json" };

export const STAGE = Object.fromEntries(data.stages.map((s) => [s.key, s]));
export const RULES = data.rules.map((r) => [r.if || null, r.stage]);
// the first rule whose fact holds
export const stageFrom = (facts = {}) => RULES.find(([f]) => !f || facts[f])[1];

// THE PAGE'S FACTS, from what it draws (TaskPage): a live session has no white section (`focus` null); a task waiting on a person has
// nothing white ("none"); the agent's Result or failure is the white section ("agent"); Close out is ("reply") - with something of its
// own (`drafted`) or still to write; a to-do's list ("list"); else the block an ask came in ("source"). `closed`: done or removed.
export const stageOf = ({ focus = null, drafted = false, closed = false } = {}) => stageFrom({
  live: focus === null, waiting: focus === "none", closed, drafted: focus === "reply" && drafted,
  result: focus === "agent", owed: focus === "reply", list: focus === "list",
});

// THE MAIN VIEW: the stage's, except while a session fills the page (always the work) and on a phone's narrow body (one stacked page, null)
export const mainView = ({ stage, sessionView = false, stacked = false }) =>
  sessionView ? "work" : stacked ? null : STAGE[stage]?.main || "task";
// ...the right drawer's tab is lit where the stage's next move is in it, and only while it is a drawer
export const drawerLit = ({ stage, main }) => main === "task" && !!STAGE[stage]?.lit;
