// A VIEW THE AGENT SHOWED, DRAWN (agenttools `show`, viewSpec.js): each block a card of its own after json-render's look (viewSpec.css) -
// tiles side by side, a grid that sets a chart beside its table, the dashboard's bars and line (dashboard/charts.jsx), words through Md.
// A button lights the real one on the task page (pageView's `point`: never pressed) or opens an app page - nothing here sends, pays or closes.
// Its buttons are never the page's own (data-tq-view-skip): the reader that lights one never finds this copy instead.
// A spec the page cannot read, or one that throws while drawing, is shown as its JSON: a view never takes the chat down with it.
import React, { useMemo } from "react";
import { Button } from "@mui/material";
import PlanDone from "@mui/icons-material/CheckBoxRounded";
import NowIcon from "@mui/icons-material/IndeterminateCheckBoxRounded";
import PlanTodo from "@mui/icons-material/CheckBoxOutlineBlankRounded";
import DoneIcon from "@mui/icons-material/CheckCircleRounded";
import TodoIcon from "@mui/icons-material/RadioButtonUncheckedRounded";
import UpIcon from "@mui/icons-material/TrendingUp";
import DownIcon from "@mui/icons-material/TrendingDown";
import FlatIcon from "@mui/icons-material/TrendingFlat";
import InfoIcon from "@mui/icons-material/InfoOutlined";
import OkIcon from "@mui/icons-material/CheckCircleOutlineRounded";
import WarnIcon from "@mui/icons-material/WarningAmberRounded";
import "./dashboard/dashboard.css";
import "./diffView.css";
import "./viewSpec.css";
import { Bars, Line } from "./dashboard/charts.jsx";
import { Md } from "./md.jsx";
import { fmtNum, numOf, places, reportShape } from "./reportRows.js";
import { run as pageRun } from "./pageView.js";
import { openAppLink } from "./appLinks.js";
import { buttonOf, fmtAs, labels, placesOf } from "./viewSpec.js";

// A CHECKLIST: done ticked, the one being done marked, the rest open - the agent's plan (GeneralWorkspace) is drawn by the same row
const PLAN_ICON = { done: PlanDone, now: NowIcon, todo: PlanTodo };
export const PlanRow = ({ p, label = "The agent's plan" }) => (
  <ul className="tq-cc-plan" data-tq-plan="" aria-label={label}>{p.items.map((x, i) => { const Icon = PLAN_ICON[x.state] || PlanTodo;
    return <li key={i} data-tq-plan-item={x.state}><Icon aria-hidden sx={{ fontSize: 15 }} /><span>{x.text}</span></li>; })}</ul>);

// EVERY BLOCK ON ITS OWN CARD (after json-render's): a hairline edge, a soft shadow, its title and the line under it. Stats and a grid have
// no card of their own - their tiles and children are the cards, never a card round cards. `flush` runs a table to the card's edges.
const Head = ({ p, aside }) => (p.title || p.description || aside
  ? <header className="tq-view-head"><div>{p.title && <h4>{p.title}</h4>}{p.description && <p>{p.description}</p>}</div>{aside}</header> : null);
const Block = ({ p, aside, flush, children }) => (
  <section className={`tq-view-card${flush ? " flush" : ""}`} aria-label={p.title || undefined}><Head p={p} aside={aside} />{children}</section>);

// a table reads its numbers as a report does: right-aligned in tabular figures, one count of decimals a column - or in the column's own
// format (money, a count, a percent), when the agent named one
function Table({ columns, rows }) {
  const names = useMemo(() => labels(columns), [columns]), fmts = useMemo(() => columns.map((c) => c.format || null), [columns]);
  const objs = useMemo(() => rows.map((r) => Object.fromEntries(names.map((c, i) => [c, r[i]]))), [names, rows]);
  const nums = useMemo(() => new Set([...reportShape(objs).nums, ...names.filter((c, i) => fmts[i] && objs.every((r) => r[c] == null || numOf(r[c]) !== null))]), [objs, names, fmts]);
  const p = useMemo(() => Object.fromEntries(names.map((c, i) => [c, fmts[i] ? placesOf(objs.map((r) => numOf(r[c])), fmts[i]) : places(objs, c)])), [names, objs, fmts]);
  const show = (r, c, i) => (r[c] == null ? "" : !nums.has(c) ? String(r[c]) : fmts[i] ? fmtAs(numOf(r[c]), fmts[i], p[c]) : fmtNum(numOf(r[c]), p[c]));
  return <div className="tq-view-table"><table>
    <thead><tr>{names.map((c) => <th key={c} scope="col" className={nums.has(c) ? "n" : ""}>{c}</th>)}</tr></thead>
    <tbody>{objs.map((r, j) => <tr key={j}>{names.map((c, i) => <td key={c} className={nums.has(c) ? "n" : ""} title={show(r, c, i)}>{show(r, c, i)}</td>)}</tr>)}</tbody>
  </table></div>;
}

// a tile: its label, the number large, and how it moved - the arrow and its colour say which way, the words say by how much
const TREND = { up: UpIcon, down: DownIcon, neutral: FlatIcon };
const tileValue = (t) => (typeof t.value !== "number" ? String(t.value) : t.format ? fmtAs(t.value, t.format) : fmtNum(t.value, (String(t.value).split(".")[1] || "").length));
const Stats = ({ items }) => (
  <div className="tq-view-tiles">{items.map((t, i) => { const Icon = t.trend && TREND[t.trend.dir];
    return <div key={i} className="tq-view-card tq-view-tile">
      <div className="lbl">{t.label}</div>
      <div className="val">{tileValue(t)}</div>
      {t.trend && <div className={`trend ${t.trend.dir}`}><Icon aria-hidden sx={{ fontSize: 16 }} /><span>{t.trend.text || t.trend.dir}</span></div>}
      {t.note && <div className="note">{t.note}</div>}
    </div>; })}</div>);

// a chart from its points alone: no rows behind a mark, so nothing to drill into, and no table twin (the points are the whole of it). The
// dashboard's own bars and line, each value at its bar's end in the view's format, one point picked out where the agent highlighted it
const Chart = ({ kind, title = "", format, points }) => {
  const nf = format ? (n) => fmtAs(n, format, placesOf(points.map((x) => x.value), format)) : undefined;
  const c = { kind: kind === "line" ? "line" : "bars", title, x: "label", y: "value", w: 2, twin: false, inline: true, fmt: nf, h: 180 };
  const marks = points.map((x, i) => ({ key: x.label || `#${i + 1}`, value: x.value, rows: [], on: !!x.highlight }));
  return kind === "line" ? <Line c={c} points={marks} onDrill={() => {}} /> : <Bars c={c} groups={marks} onDrill={() => {}} />;
};

// a checklist under how far along it is: "2 of 6" beside its title and a bar across
function Checklist({ p }) {
  const n = p.items.filter((x) => x.done).length, all = p.items.length;
  return <Block p={p} aside={<span className="tq-view-count">{n} of {all}</span>}>
    <div className="tq-view-progress" role="progressbar" aria-valuemin={0} aria-valuemax={all} aria-valuenow={n} aria-label={`${n} of ${all} done`}>
      <div style={{ width: `${(n / all) * 100}%` }} /></div>
    <ul className="tq-view-checks" aria-label={p.title || "Checklist"}>{p.items.map((x, i) => (
    <li key={i} data-done={x.done || undefined}>{x.done ? <DoneIcon aria-hidden sx={{ fontSize: 18 }} /> : <TodoIcon aria-hidden sx={{ fontSize: 18 }} />}
      <span>{x.text}{x.done && <span className="sr"> (done)</span>}</span></li>))}</ul></Block>;
}

const NOTE = { info: InfoIcon, success: OkIcon, warning: WarnIcon };
const Note = ({ p }) => { const tone = p.tone || "info", Icon = NOTE[tone];
  return <aside className={`tq-view-note ${tone}`} role="note"><Icon aria-hidden sx={{ fontSize: 18 }} />
    <div>{p.title && <h4>{p.title}</h4>}<Md text={p.text} />{p.description && <p>{p.description}</p>}</div></aside>; };

function ViewButton({ p }) {
  const b = buttonOf(p);
  const press = () => (b.verb ? pageRun([{ op: "point", button: b.lights }]) : openAppLink(b.open));
  return <Button size="small" variant="outlined" className="tq-view-button" data-tq-view-button={b.verb || b.open}
    title={b.verb ? `Shows you ${b.lights} - you press it` : undefined} onClick={press}>{b.label}</Button>;
}

const DRAW = {
  table: (p) => <Block p={p} flush><Table columns={p.columns} rows={p.rows} /></Block>,
  stats: (p) => <><Head p={p} /><Stats items={p.items} /></>,
  chart: (p) => <Block p={p}><Chart {...p} /></Block>,
  list: (p) => <Block p={p}><ul className="tq-view-list">{p.items.map((x, i) => <li key={i}>{x}</li>)}</ul></Block>,
  steps: (p) => <Block p={p}><ol className="tq-view-list steps">{p.items.map((x, i) => <li key={i}><b>{i + 1}</b><span>{x}</span></li>)}</ol></Block>,
  checklist: (p) => <Checklist p={p} />,
  // ...words alone are words in the chat; given a title they are a card like the rest
  text: (p) => (p.title || p.description ? <Block p={p}><Md text={p.text} /></Block> : <Md text={p.text} />),
  grid: (p) => <Head p={p} />,
  badge: (p) => <span className={`tq-view-badge ${p.variant || "default"}`} title={p.title || p.description || undefined}>{p.text}</span>,
  note: (p) => <Note p={p} />,
  button: (p) => <ViewButton p={p} />,
};
// an element, then its children: under it, side by side in a grid (stacking where the chat is narrow), and a run of badges and buttons on one line
const INLINE = new Set(["button", "badge"]);
const Node = ({ els, id }) => {
  const e = els[id], kids = e.children || [], cols = e.type === "grid" ? e.props.cols || Math.min(kids.length, 4) : 0;
  const cls = cols ? "tq-view-grid" : kids.every((k) => INLINE.has(els[k].type)) ? "tq-view-buttons" : "tq-view-kids";
  return <div className="tq-view-el" data-tq-view-el={e.type}>{DRAW[e.type](e.props)}
    {!!kids.length && <div className={cls} data-cols={cols || undefined}>{kids.map((k) => <Node key={k} els={els} id={k} />)}</div>}</div>;
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
