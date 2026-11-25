// A VIEW THE AGENT SHOWED, DRAWN (agenttools `show`, viewSpec.js): each block a card of its own after json-render's look (viewSpec.css) -
// tiles side by side, a grid that sets a chart beside its table, the dashboard's bars and line (dashboard/charts.jsx), words through Md.
// A button lights the real one on the task page (pageView's `point`: never pressed) or opens an app page - nothing here sends, pays or closes.
// Its buttons are never the page's own (data-tq-view-skip): the reader that lights one never finds this copy instead.
// A VIEW IS DRAWN, NEVER ITS JSON (the owner, 2026-11-15): a spec the page cannot read is no view (viewSpec.viewOf - it stays a step), and one
// that throws while drawing says so in a line - a view never takes the chat down with it.
import React, { createContext, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTableFit } from "./tableFit.js";
import { Button, MenuItem, Slider, Switch, TextField } from "@mui/material";
import PickedIcon from "@mui/icons-material/CheckRounded";
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
import { Bars, Line, PieBody, Stacked } from "./dashboard/charts.jsx";
import { Md } from "./md.jsx";
import { fmtNum, numOf, places, reportShape } from "./reportRows.js";
import { run as pageRun } from "./pageView.js";
import { openAppLink } from "./appLinks.js";
import api from "./api.js";
import Artifact from "./Artifact.jsx";
import { asks, buttonOf, colName, columnsOf, evalExpr, fillIn, fmtAs, labels, placesOf } from "./viewSpec.js";

// ── A VIEW HE CAN WORK WITH (after json-render's state and actions): its values (the spec's `state`), moved by its controls on his screen
// alone; every value written {$expr} is worked out from them as they move (viewSpec.evalExpr - no eval), and one that cannot be is said
// in plain words where it stands. His pick on a choice, or a button's answer, goes to the agent once as his press (viewspec.answer) and
// stays on what he pressed; nothing in a view sends or pays.
const ViewCtx = createContext({ state: {}, set: () => {}, picks: {}, answer: null });
const useView = () => useContext(ViewCtx);
// a value as it stands now: {value}, or {error} where its expression cannot be worked out
const now = (v, scope) => (v && typeof v === "object" && "$expr" in v ? evalExpr(v.$expr, scope) : { value: v });
const Err = ({ e }) => (e ? <div className="tq-view-err" role="note" data-tq-view-err="">Could not work out {e}</div> : null);

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
const withSym = (raw, n) => { const m = typeof raw === "string" && raw.trim().match(/^-?\s*([$€£¥])/); return !m ? n : n.startsWith("-") ? `-${m[1]}${n.slice(1)}` : `${m[1]}${n}`; };
function Table({ columns, rows }) {
  const names = useMemo(() => labels(columns), [columns]), fmts = useMemo(() => columns.map((c) => c.format || null), [columns]);
  const objs = useMemo(() => rows.map((r) => Object.fromEntries(names.map((c, i) => [c, r[i]]))), [names, rows]);
  const nums = useMemo(() => new Set([...reportShape(objs).nums, ...names.filter((c, i) => fmts[i] && objs.every((r) => r[c] == null || numOf(r[c]) !== null))]), [objs, names, fmts]);
  const p = useMemo(() => Object.fromEntries(names.map((c, i) => [c, fmts[i] ? placesOf(objs.map((r) => numOf(r[c])), fmts[i]) : places(objs, c)])), [names, objs, fmts]);
  // ...and a cell written with its money's symbol keeps it (round 4, 2026-11-22: "$1,234" read as a number drew as "1,234" - the price lost its "$")
  const show = (r, c, i) => (r[c] == null ? "" : !nums.has(c) ? String(r[c]) : fmts[i] ? fmtAs(numOf(r[c]), fmts[i], p[c]) : withSym(r[c], fmtNum(numOf(r[c]), p[c])));
  // ...A TABLE WIDER THAN THE TURN'S COLUMN TAKES THE ROOM ITS COLUMNS NEED (the owner, 2026-11-23: "if it requires full page it can"), by the
  // one rule every table fits by (tableFit.js)
  const ref = useRef(null);
  useTableFit(ref, [names, objs]);
  return <div className="tq-view-table" ref={ref}><table>
    <thead><tr>{names.map((c) => <th key={c} scope="col" className={nums.has(c) ? "n" : ""}>{c}</th>)}</tr></thead>
    <tbody>{objs.map((r, j) => <tr key={j}>{names.map((c, i) => <td key={c} className={nums.has(c) ? "n" : ""} title={show(r, c, i)}>{show(r, c, i)}</td>)}</tr>)}</tbody>
  </table></div>;
}

// ...its cells worked out against the view's values and their own row's columns (lower case, _ for a space: viewSpec.colName)
function TableNow({ columns, rows }) {
  const { state } = useView(), names = labels(columns);
  let err = null;
  const got = rows.map((r) => { const scope = { ...state };
    names.forEach((c, i) => { if (!(r[i] && typeof r[i] === "object")) scope[colName(c)] = r[i]; });
    return r.map((c) => { const x = now(c, scope); if (x.error) { err ||= x.error; return "—"; } return x.value; }); });
  return <><Table columns={columns} rows={got} /><Err e={err} /></>;
}

// a tile: its label, the number large, and how it moved - the arrow and its colour say which way, the words say by how much
const TREND = { up: UpIcon, down: DownIcon, neutral: FlatIcon };
const tileValue = (t) => (typeof t.value !== "number" ? String(t.value) : t.format ? fmtAs(t.value, t.format) : fmtNum(t.value, (String(t.value).split(".")[1] || "").length));
function Stats({ items }) {
  const { state } = useView();
  return <div className="tq-view-tiles">{items.map((t, i) => { const Icon = t.trend && TREND[t.trend.dir], v = now(t.value, state);
    return <div key={i} className="tq-view-card tq-view-tile">
      <div className="lbl">{t.label}</div>
      <div className="val" data-tq-view-value="">{v.error ? "—" : tileValue({ ...t, value: v.value })}</div>
      <Err e={v.error} />
      {t.trend && <div className={`trend ${t.trend.dir}`}><Icon aria-hidden sx={{ fontSize: 16 }} /><span>{t.trend.text || t.trend.dir}</span></div>}
      {t.note && <div className="note">{t.note}</div>}
    </div>; })}</div>;
}

// a chart from its points alone: no rows behind a mark, so nothing to drill into, and no table twin (the points are the whole of it). The
// dashboard's own bars and line, each value at its bar's end in the view's format, one point picked out where the agent highlighted it
// ...and a run of short labels as columns (viewSpec.columnsOf), the chart's height whatever their count
// ...a pie: the dashboards' own (charts.PieBody) - each slice its share, its colour the series', the legend its label, value and share
function ChartNow(p) {
  const { state } = useView();
  let err = null;
  const points = p.points.map((x) => { const v = now(x.value, state); if (v.error || typeof v.value !== "number") err ||= v.error || `"${x.value.$expr}" - it does not come to a number`;
    return { ...x, value: typeof v.value === "number" ? v.value : 0 }; });
  return <>{!err && <Chart {...p} points={points} />}<Err e={err} /></>;
}
const Chart = ({ kind, title = "", format, points }) => {
  const nf = format ? (n) => fmtAs(n, format, placesOf(points.map((x) => x.value), format)) : undefined;
  const c = { kind: kind === "line" || kind === "area" ? kind : "bars", title, x: "label", y: "value", w: 2, twin: false, inline: true, fmt: nf, h: 160 };
  const marks = points.map((x, i) => ({ key: x.label || `#${i + 1}`, value: x.value, rows: [], on: !!x.highlight }));
  if (kind === "pie") return <PieBody groups={marks} f={nf || ((n) => fmtNum(n, 0))} />;
  if (kind === "line" || kind === "area") return <Line c={c} points={marks} onDrill={() => {}} />;      // ...an area: the line over its soft fill
  const st = columnsOf(marks);
  return st ? <Stacked c={c} st={st} slots={{ value: 0 }} onDrill={() => {}} /> : <Bars c={c} groups={marks} onDrill={() => {}} />;
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

function ViewButton({ p, on, id }) {
  const v = useView(), act = on?.press;
  if (act?.action === "answer") return <Answer id={id} asked={p.label} options={[p.label]} pickOf={() => fillIn(act.params.text, v.state)} one />;
  if (act?.action === "setState") return <Button size="small" variant="outlined" className="tq-view-button" data-tq-view-button="setState"
    onClick={() => { const x = now(act.params.value, v.state); if (!x.error) v.set(act.params.statePath, x.value); }}>{p.label}</Button>;
  const b = buttonOf(p);
  const press = () => (b.verb ? pageRun([{ op: "point", button: b.lights }]) : openAppLink(b.open));
  return <Button size="small" variant="outlined" className="tq-view-button" data-tq-view-button={b.verb || b.open}
    title={b.verb ? `Shows you ${b.lights} - you press it` : undefined} onClick={press}>{b.label}</Button>;
}

// HIS ANSWER: each option a button; pressed, the pick goes to the agent once (viewspec.answer) and stands here, the rest greyed. Pressed
// again anywhere - a second tab - the server says the first pick, and that is what stands. Off a task (a report, the Assistant) there is
// no agent to answer, and the buttons say so
function Answer({ id, asked, options, pickOf = (o) => ({ value: o }), one }) {
  const { picks, answer } = useView(), [going, setGoing] = useState(""), [err, setErr] = useState("");
  const picked = picks[id];
  const press = async (o) => {
    const got = pickOf(o); if (got.error) return setErr(`Could not work out ${got.error}`);
    setGoing(o); setErr("");
    try { await answer(id, got.value, asked); } catch (e) { setErr(e?.response?.data?.detail || e?.message || "It did not reach the agent."); } finally { setGoing(""); }
  };
  const mine = (o) => picked != null && (one || picked === o);
  return <div className="tq-view-answer" data-tq-view-answer={id}>
    <div className="tq-view-buttons">{options.map((o) => <Button key={o} size="small" variant={mine(o) ? "contained" : "outlined"} disableElevation
      className="tq-view-button" data-tq-view-pick={o} disabled={!answer || picked != null || !!going} aria-pressed={mine(o)}
      title={!answer ? "Answer in the chat - this view is not on a task" : undefined} startIcon={mine(o) ? <PickedIcon /> : undefined}
      onClick={() => press(o)}>{o}</Button>)}</div>
    {picked != null && <div className="tq-view-said" role="status">{one ? "You answered" : "You picked"}: {picked}</div>}
    {err && <div className="tq-view-err" role="alert">{err}</div>}
  </div>;
}

// A CONTROL moves one of the view's values, on his screen alone - what is worked out from it changes as it moves
function Control({ type, p }) {
  const { state, set } = useView(), v = state[p.value];
  if (type === "slider") return <div className="tq-view-control" data-tq-view-control={p.value}>
    <div className="tq-view-control-head"><span>{p.label}</span><b data-tq-view-now="">{typeof v === "number" ? (p.format ? fmtAs(v, p.format) : fmtNum(v, (String(v).split(".")[1] || "").length)) : ""}</b></div>
    <Slider size="small" value={typeof v === "number" ? v : p.min} min={p.min} max={p.max} step={p.step || (p.max - p.min > 20 ? 1 : (p.max - p.min) / 100)}
      onChange={(_, x) => set(p.value, x)} aria-label={p.label} valueLabelDisplay="off" /></div>;
  if (type === "toggle") return <label className="tq-view-control row" data-tq-view-control={p.value}>
    <Switch size="small" checked={!!v} onChange={(e) => set(p.value, e.target.checked)} /><span>{p.label}</span></label>;
  if (type === "select") return <TextField select size="small" label={p.label} value={p.options.includes(v) ? v : p.options[0]}
    onChange={(e) => set(p.value, e.target.value)} className="tq-view-control" data-tq-view-control={p.value}>
    {p.options.map((o) => <MenuItem key={o} value={o}>{o}</MenuItem>)}</TextField>;
  return <TextField type="date" size="small" label={p.label} value={typeof v === "string" ? v : ""} onChange={(e) => set(p.value, e.target.value)}
    className="tq-view-control" data-tq-view-control={p.value} InputLabelProps={{ shrink: true }} />;
}

const DRAW = {
  table: (p) => <Block p={p} flush><TableNow columns={p.columns} rows={p.rows} /></Block>,
  stats: (p) => <><Head p={p} /><Stats items={p.items} /></>,
  chart: (p) => <Block p={p}><ChartNow {...p} /></Block>,
  list: (p) => <Block p={p}><ul className="tq-view-list">{p.items.map((x, i) => <li key={i}>{x}</li>)}</ul></Block>,
  steps: (p) => <Block p={p}><ol className="tq-view-list steps">{p.items.map((x, i) => <li key={i}><b>{i + 1}</b><span>{x}</span></li>)}</ol></Block>,
  checklist: (p) => <Checklist p={p} />,
  // ...words alone are words in the chat; given a title they are a card like the rest
  text: (p) => (p.title || p.description ? <Block p={p}><Md text={p.text} /></Block> : <Md text={p.text} />),
  grid: (p) => <Head p={p} />,
  badge: (p) => <span className={`tq-view-badge ${p.variant || "default"}`} title={p.title || p.description || undefined}>{p.text}</span>,
  note: (p) => <Note p={p} />,
  button: (p, e, id) => <ViewButton p={p} on={e.on} id={id} />,
  slider: (p) => <Control type="slider" p={p} />, toggle: (p) => <Control type="toggle" p={p} />,
  select: (p) => <Control type="select" p={p} />, date: (p) => <Control type="date" p={p} />,
  choice: (p, e, id) => <Block p={{ ...p, title: p.title || p.label }}><Answer id={id} asked={p.label} options={p.options} /></Block>,
};
// an element, then its children: under it, side by side in a grid (stacking where the chat is narrow), and a run of badges and buttons on one line
const INLINE = new Set(["button", "badge"]);
const Node = ({ els, id }) => {
  const e = els[id], kids = e.children || [], cols = e.type === "grid" ? e.props.cols || Math.min(kids.length, 4) : 0;
  const cls = cols ? "tq-view-grid" : kids.every((k) => INLINE.has(els[k].type)) ? "tq-view-buttons" : "tq-view-kids";
  return <div className="tq-view-el" data-tq-view-el={e.type}>{DRAW[e.type](e.props, e, id)}
    {!!kids.length && <div className={cls} data-cols={cols || undefined}>{kids.map((k) => <Node key={k} els={els} id={k} />)}</div>}</div>;
};

class Guard extends React.Component {
  constructor(props) { super(props); this.state = { bad: false }; }
  static getDerivedStateFromError() { return { bad: true }; }
  componentDidCatch(err) { console.warn("view could not be drawn:", err); }
  render() { return this.state.bad ? <p className="tq-aui-hint" data-tq-view-failed="">This view could not be drawn here.</p> : this.props.children; }
}

// `taskId`: the task whose agent showed it - where his answers go. A view off a task draws its answer buttons greyed
export default function ViewSpec({ spec, taskId }) {
  const [state, setState] = useState(() => ({ ...(spec?.state || {}) })), [picks, setPicks] = useState({});
  const answering = !!(spec && taskId && spec.id && asks(spec.elements));
  // ...what he answered already, so the view drawn again (a reload, the phone) shows his pick, never the buttons lit again
  useEffect(() => { if (!answering) return undefined;
    let on = true; api.get(`/api/tasks/${taskId}/view-answers`).then(({ data }) => on && setPicks((p) => ({ ...(data?.[spec.id] || {}), ...p }))).catch(() => {});
    return () => { on = false; }; }, [answering, taskId, spec?.id]);
  const ctx = useMemo(() => ({ state, picks, set: (k, v) => setState((s) => ({ ...s, [k]: v })),
    answer: answering ? async (el, pick, asked) => {
      try { await api.post(`/api/tasks/${taskId}/view-answer`, { view: spec.id, el, pick, asked }); setPicks((p) => ({ ...p, [el]: pick })); }
      catch (e) { const d = String(e?.response?.data?.detail || "");      // ...answered already (a second tab): the first pick is what stands
        if (e?.response?.status === 409) setPicks((p) => ({ ...p, [el]: d.replace(/^answered already:\s*/, "") })); else throw e; }
    } : null }), [state, picks, answering, taskId, spec?.id]);
  if (!spec) return null;
  return <Guard><ViewCtx.Provider value={ctx}><Artifact as="section" className="tq-dash tq-view" data-tq-view="" data-tq-view-skip="" aria-label={spec.title || "A view from the agent"}>
    {spec.title && <h3 className="tq-view-title">{spec.title}</h3>}
    <Node els={spec.elements} id={spec.root} />
  </Artifact></ViewCtx.Provider></Guard>;
}
