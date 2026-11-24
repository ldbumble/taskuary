// WHAT TASKUARY MADE ON ITS OWN, AS A VIEW (madeView.js): a report's run and an Advisor's idea are read once into the spec the one view renderer
// draws (ViewSpec.jsx) - never a renderer of their own - and the files a run carries that its view already IS are never drawn again.
import test from "node:test";
import assert from "node:assert/strict";
import { ideaView, reportView } from "../src/madeView.js";
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

test("an Advisor's idea is what it noticed and what to do, then what it rests on - each a link into the app", () => {
  const card = { title: "Payworth charged the October run twice", action: { type: "lookout", next_step: "Ask Payworth to refund the second charge.",
    pitch: "Caught a duplicate charge before close.", mid: 9, who: "Erin Blake", why: "the same amount twice", evidence: [{ ref: "msg9", label: "the invoice" }, { ref: "task7", label: "the close" }] } };
  const spec = ideaView(card), [lead, facts] = typed(spec, "text");
  assert.deepEqual(lead.props, { title: card.title, text: "Ask Payworth to refund the second charge." });
  assert.match(facts.props.text, /\*\*Pitch\*\* - Caught a duplicate charge/);
  assert.match(facts.props.text, /\*\*Based on\*\* - \[Erin Blake's message ↗\]\(#msg=9\): the same amount twice/);
  assert.match(facts.props.text, /\*\*Rests on\*\* - \[the invoice ↗\]\(#msg=9\) · \[the close ↗\]\(#task=7\)/);
  assert.ok(normalise(spec));
});
