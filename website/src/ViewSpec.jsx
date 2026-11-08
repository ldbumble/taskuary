// A VIEW THE AGENT SHOWED, DRAWN (agenttools `show`, viewSpec.js): each element in the parts the app already draws with - a table as a
// report's (reportRows.css), stats and charts as a dashboard's (dashboard/charts.jsx), a checklist as the agent's plan, words through Md.
// A button lights the real one on the task page (pageView's `point`: never pressed) or opens an app page - nothing here sends, pays or closes.
// Its buttons are never the page's own (data-tq-view-skip): the reader that lights one never finds this copy instead.
// A spec the page cannot read, or one that throws while drawing, is shown as its JSON: a view never takes the chat down with it.
import React, { useMemo } from "react";
import { Button } from "@mui/material";
import DoneIcon from "@mui/icons-material/CheckBoxRounded";
import NowIcon from "@mui/icons-material/IndeterminateCheckBoxRounded";
import TodoIcon from "@mui/icons-material/CheckBoxOutlineBlankRounded";
import "./dashboard/dashboard.css";
import "./reportRows.css";
import "./diffView.css";
import "./viewSpec.css";
import { Bars, Card, Line } from "./dashboard/charts.jsx";
import { Md } from "./md.jsx";
import { fmtNum, numOf, places, reportShape } from "./reportRows.js";
import { run as pageRun } from "./pageView.js";
import { openAppLink } from "./appLinks.js";
import { buttonOf } from "./viewSpec.js";

// A CHECKLIST: done ticked, the one being done marked, the rest open - the agent's plan (GeneralWorkspace) is drawn by the same row
const PLAN_ICON = { done: DoneIcon, now: NowIcon, todo: TodoIcon };
export const PlanRow = ({ p, label = "The agent's plan" }) => (
  <ul className="tq-cc-plan" data-tq-plan="" aria-label={label}>{p.items.map((x, i) => { const Icon = PLAN_ICON[x.state] || TodoIcon;
    return <li key={i} data-tq-plan-item={x.state}><Icon aria-hidden sx={{ fontSize: 15 }} /><span>{x.text}</span></li>; })}</ul>);

// a table reads its numbers as a report does: right-aligned, one count of decimals a column
function Table({ columns, rows }) {
  const objs = useMemo(() => rows.map((r) => Object.fromEntries(columns.map((c, i) => [c, r[i]]))), [columns, rows]);
  const nums = useMemo(() => new Set(reportShape(objs).nums), [objs]);
  const p = useMemo(() => Object.fromEntries([...nums].map((c) => [c, places(objs, c)])), [nums, objs]);
  const show = (r, c) => (r[c] == null ? "" : nums.has(c) ? fmtNum(numOf(r[c]), p[c]) : String(r[c]));
  return <div className="tq-rep-table"><table className="tq-rep-rows">
    <thead><tr>{columns.map((c) => <th key={c} scope="col" className={nums.has(c) ? "n" : ""}>{c}</th>)}</tr></thead>
    <tbody>{objs.map((r, i) => <tr key={i}>{columns.map((c) => <td key={c} className={nums.has(c) ? "n" : ""} title={show(r, c)}>{show(r, c)}</td>)}</tr>)}</tbody>
  </table></div>;
}

const Stats = ({ items }) => (
  <div className="tq-dash-grid tq-view-stats">{items.map((t, i) => (
    <Card key={i} c={{ kind: "stat", title: t.label }} w={1}>
      <div className="tq-dash-value">{typeof t.value === "number" ? fmtNum(t.value, (String(t.value).split(".")[1] || "").length) : String(t.value)}</div>
      {t.note && <div className="tq-dash-delta"><span>{t.note}</span></div>}
    </Card>))}</div>);

// a chart from its points alone: no rows behind a mark, so nothing to drill into, and no table twin (the points are the whole of it)
const Chart = ({ kind, title = "", points }) => {
  const c = { kind: kind === "line" ? "line" : "bars", title, x: "label", y: "value", w: 2, twin: false };
  const marks = points.map((x, i) => ({ key: x.label || `#${i + 1}`, value: x.value, rows: [] }));
  return kind === "line" ? <Line c={c} points={marks} onDrill={() => {}} /> : <Bars c={c} groups={marks} onDrill={() => {}} />;
};

function ViewButton({ p }) {
  const b = buttonOf(p);
  const press = () => (b.verb ? pageRun([{ op: "point", button: b.lights }]) : openAppLink(b.open));
  return <Button size="small" variant="outlined" className="tq-view-button" data-tq-view-button={b.verb || b.open}
    title={b.verb ? `Shows you ${b.lights} - you press it` : undefined} onClick={press}>{b.label}</Button>;
}

const DRAW = {
  table: (p) => <Table columns={p.columns} rows={p.rows} />,
  stats: (p) => <Stats items={p.items} />,
  chart: (p) => <Chart {...p} />,
  list: (p) => <ul className="tq-view-list">{p.items.map((x, i) => <li key={i}>{x}</li>)}</ul>,
  steps: (p) => <ol className="tq-view-list">{p.items.map((x, i) => <li key={i}>{x}</li>)}</ol>,
  checklist: (p) => <PlanRow label="Checklist" p={{ items: p.items.map((x) => ({ text: x.text, state: x.done ? "done" : "todo" })) }} />,
  text: (p) => <Md text={p.text} />,
  button: (p) => <ViewButton p={p} />,
};
// an element, then its children under it; a run of buttons sits on one line
const Node = ({ els, id }) => {
  const e = els[id], kids = e.children || [];
  return <div className="tq-view-el" data-tq-view-el={e.type}>{DRAW[e.type](e.props)}
    {!!kids.length && <div className={kids.every((k) => els[k].type === "button") ? "tq-view-buttons" : "tq-view-kids"}>
      {kids.map((k) => <Node key={k} els={els} id={k} />)}</div>}</div>;
};

const AsText = ({ raw }) => <pre className="tq-view-raw" data-tq-view-raw="">{(() => { try { return JSON.stringify(raw, null, 2); } catch { return String(raw); } })()}</pre>;
class Guard extends React.Component {
  constructor(props) { super(props); this.state = { bad: false }; }
  static getDerivedStateFromError() { return { bad: true }; }
  componentDidCatch(err) { console.warn("view could not be drawn:", err); }
  render() { return this.state.bad ? <AsText raw={this.props.raw} /> : this.props.children; }
}

export default function ViewSpec({ spec, raw }) {
  if (!spec) return <AsText raw={raw} />;
  return <Guard raw={raw}><section className="tq-dash tq-view" data-tq-view="" data-tq-view-skip="" aria-label={spec.title || "A view from the agent"}>
    {spec.title && <h3 className="tq-view-title">{spec.title}</h3>}
    <Node els={spec.elements} id={spec.root} />
  </section></Guard>;
}
