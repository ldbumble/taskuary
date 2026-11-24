// WHAT TASKUARY MADE ON ITS OWN, AS A TASK (madeTask.js): a report's run and an Advisor's idea are read once into the spec the one view renderer
// draws (ViewSpec.jsx) - never a renderer of their own - the files a run carries that its view already IS are never drawn again, and what it
// rests on is its Came from (the routine behind it; an idea's evidence).
import test from "node:test";
import assert from "node:assert/strict";
import { ideaSource, ideaView, madeTask, reportView, routineSource } from "../src/madeTask.js";
import { normalise } from "../src/viewSpec.js";

const els = (spec) => Object.values(spec.elements);
const typed = (spec, t) => els(spec).filter((e) => e.type === t);

test("a data report is its line, its chart and every row, in the view an agent's `show` draws - and its chart's picture is the chart's alone", () => {
  const text = ["Lakeview", "Riverside", "Fairhaven"].map((site, i) => JSON.stringify({ site, headcount: [112, 98, 143][i] })).join("\n");
  const { spec, owns } = reportView(text, "Headcount by site, nightly");
  assert.equal(spec.title, "Headcount by site, nightly");
  assert.ok(normalise(spec), "the catalogue's own check passes it: the same spec an agent could have shown");
  assert.match(typed(spec, "text")[0].props.text, /3 rows · 353 headcount in all · largest Fairhaven at 143/);
  assert.deepEqual(typed(spec, "chart")[0].props.points.map((p) => p.value), [112, 98, 143]);
  assert.deepEqual(typed(spec, "table")[0].props, { columns: ["Site", "Headcount"], rows: [["Lakeview", 112], ["Riverside", 98], ["Fairhaven", 143]] });
  // ONE THING, ONE PLACE: the run's chart picture is drawn by the chart, the spreadsheet stays a file
  assert.equal(owns({ name: "Headcount by site.svg", content_type: "image/svg+xml" }), true);
  assert.equal(owns({ name: "Headcount by site.xlsx", content_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" }), false);
});

test("a brief reads as its roll-ups side by side, each group of items, and its close; words stay words and own no file", () => {
  const brief = ["Done today: Closed the GL reconciliation.", "Tomorrow: Confirm the AP cutover date with Erin Blake.", "", "**Mail**",
    "- ✉️ ✅ Marcus Reed — Q3 numbers — sent the workbook", "- 👥 📅 Gail Moreno — audit list — half an hour booked", "", "A calm day."].join("\n");
  const { spec, owns } = reportView(brief, "End of day checkup");
  const grid = typed(spec, "grid").find((g) => g.props.cols === 2);
  assert.deepEqual(grid.children.map((id) => spec.elements[id].props.title), ["Done today", "Tomorrow"]);
  const mail = typed(spec, "text").find((t) => /^Mail/.test(t.props.title || ""));
  assert.equal(mail.props.title, "Mail · 2");
  assert.match(mail.props.text, /- \*\*Marcus Reed\*\* · Q3 numbers {2}\n {2}sent the workbook/);
  assert.match(mail.props.text, /Gail Moreno\*\* · audit list · _meeting_/);
  assert.ok(typed(spec, "text").some((t) => t.props.text === "A calm day."));
  assert.equal(owns({ content_type: "image/svg+xml" }), false, "no chart drawn, so no picture is the chart's");
  const words = reportView("Three things worth your time today.\n\n- **Payworth charged twice**", "Advisor").spec;
  assert.deepEqual(typed(words, "text").map((t) => t.props.text), ["Three things worth your time today.\n\n- **Payworth charged twice**"]);
});

test("an Advisor's idea is what it noticed and what to do; what it rests on is its Came from - each a link into the app", () => {
  const card = { title: "Payworth charged the October run twice", action: { type: "lookout", next_step: "Ask Payworth to refund the second charge.",
    pitch: "Caught a duplicate charge before close.", mid: 9, who: "Erin Blake", why: "the same amount twice", evidence: [{ ref: "msg9", label: "the invoice" }, { ref: "task7", label: "the close" }] } };
  const spec = ideaView(card), [lead, pitch] = typed(spec, "text");
  assert.deepEqual(lead.props, { title: card.title, text: "Ask Payworth to refund the second charge." });
  assert.match(pitch.props.text, /\*\*Pitch\*\* - Caught a duplicate charge/);
  assert.ok(normalise(spec));
  const src = ideaSource(card);
  assert.deepEqual(src.links, [{ label: "Erin Blake's message", href: "#msg=9" }, { label: "the invoice", href: "#msg=9" }, { label: "the close", href: "#task=7" }]);
  assert.deepEqual(src.rows, [["Why", "the same amount twice"]]);
});

test("a report's source is its routine: name, schedule, prompt, what it reads, where it goes, and Edit", () => {
  const row = { SourceId: 4, Address: "Headcount by site", ScheduleWords: "every day at 07:00", RouteWords: "Reports: every run" };
  const src = routineSource(row, { ai_prompt: "Count heads per site.", sources: [{ type: "mssql" }, { type: "mssql" }, { type: "rss" }] }, { types: { mssql: "SQL Server" }, edit: "Edit this report" });
  assert.deepEqual(src.rows, [["Name", "Headcount by site"], ["Runs", "every day at 07:00"], ["Prompt", "Count heads per site."], ["Reads", "SQL Server, rss"], ["Goes to", "Reports: every run"]]);
  assert.deepEqual(src.edit, { label: "Edit this report", href: "#report=4" });
});

test("the item is a task-shaped record: its prompt the chat's input line, its run the turn whose artifact is the made view", () => {
  const m = madeTask({ key: "report:4", kind: "report", label: "Report", title: "Headcount", when: "2026-11-24 07:00:00", input: { head: "Automated · Headcount", text: "Count heads." }, source: { rows: [] } });
  assert.equal(m.detail.task.TaskId, "report:4"); assert.equal(m.detail.ref, "Report");
  const [line, turn] = m.list.items;
  assert.deepEqual([line.kind, line.auto, line.text], ["line", "Automated · Headcount", "Count heads."]);
  assert.deepEqual([turn.kind, turn.state, turn.cards[0].review], ["turn", "done", "made:run"]);
});
