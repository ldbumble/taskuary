// THE PRESET COMPONENTS a dashboard is built from - the only shapes its AI setup may choose (compose.DASHBOARD_SYSTEM). Plain
// HTML and SVG, no chart library: thin marks, one axis, a hairline grid, values on the tip, a legend for two series or more, a
// tooltip on every mark that the table view also carries (docs/notes/dashboards.md). Text wears the ink; marks wear the slots.
import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { DASH } from "../words.js";
import { OTHER, aggregate, delta, fmt, itemLink, signed, sortRows, timeSeries } from "./slice.js";

export const slotColor = (i) => (i === undefined || i === null || i < 0 ? "var(--d-other)" : `var(--d-s${(i % 6) + 1})`);
const label = (k) => (k === OTHER ? DASH.other : k);
const shortDay = (d) => { const t = new Date(`${d}T12:00:00`); return Number.isNaN(t.getTime()) ? d : t.toLocaleDateString("en-US", { month: "short", day: "numeric" }); };
const keyLabel = (k, dated) => (dated ? shortDay(k) : label(k));
const cleanCol = (c) => String(c || "").replace(/_/g, " ");

// the width a chart is drawn at - measured, so text stays text-sized at every width
function useWidth() {
  const ref = useRef(null), [w, setW] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current; if (!el) return undefined;
    setW(el.clientWidth);
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)));
    ro.observe(el); return () => ro.disconnect();
  }, []);
  return [ref, w];
}

// one tooltip per card: what the pointer is over, placed beside it inside the card
function useTip() {
  const [tip, setTip] = useState(null);
  const show = (e, body) => {
    const card = e.currentTarget.closest(".tq-dash-card"); if (!card) return;
    const r = card.getBoundingClientRect(), x = (e.clientX ?? r.left + r.width / 2) - r.left, y = (e.clientY ?? r.top + 40) - r.top;
    setTip({ x: Math.min(x + 12, r.width - 150), y: Math.max(8, y - 12), body });
  };
  return [tip && <div className="tq-dash-tip" style={{ left: tip.x, top: tip.y }} role="status">{tip.body}</div>, show, () => setTip(null)];
}
const TipRows = ({ k, rows }) => (
  <>{k && <div className="k">{k}</div>}{rows.map(([name, v, color], i) => (
    <div className="r" key={i}>{color && <i style={{ background: color }} />}<b>{fmt(v)}</b>{name && <span>{name}</span>}</div>))}</>
);

// THE FRAME every component sits in: its title, the Chart/Table switch (the table is the chart's accessible twin), the body
export function Card({ c, w, children, table, stale, onPress, className = "" }) {
  const [asTable, setAsTable] = useState(false);
  return (
    <section className={`tq-dash-card w${w} ${stale ? "stale" : ""} ${className}`} data-tq-dash-kind={c.kind} aria-label={c.title} style={{ "--i": c.i ?? 0 }}
      onClick={onPress} onKeyDown={onPress ? (e) => { if (e.key === "Enter") onPress(e); } : undefined} tabIndex={onPress ? 0 : undefined}>
      <div className="tq-dash-h"><h3 title={c.title}>{c.title}</h3>
        {/* ...no switch where the rows' own table stands beside the chart (a report, ReportRows): `twin: false` */}
        {table && c.twin !== false && <button type="button" className="tq-dash-flip" aria-pressed={asTable} onClick={(e) => { e.stopPropagation(); setAsTable(!asTable); }}>
          {asTable ? DASH.chart : DASH.table}</button>}
      </div>
      {asTable ? table : children}
    </section>
  );
}

// ── the number ───────────────────────────────────────────────────────────────────────────────────────────
function Spark({ points }) {
  const vals = points.map((p) => p.value ?? 0), max = Math.max(1, ...vals), n = Math.max(1, vals.length - 1);
  const xy = vals.map((v, i) => [(i / n) * 100, 28 - (v / max) * 26]);
  if (vals.length < 2) return null;
  const last = xy[xy.length - 1], line = xy.map(([x, y]) => `${x},${y}`).join(" ");
  return (
    <svg className="tq-dash-spark" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
      <polygon className="ar" points={`0,30 ${line} 100,30`} />
      <polyline className="ln" points={line} />
      <rect className="now" x={last[0] - 1.2} y={last[1] - 1.2} width="2.4" height="2.4" rx="1.2" />
    </svg>
  );
}

// a value and its unit: the unit is set smaller, in the muted ink, so the number stays the thing read
const Value = ({ v, unit, of }) => (
  <div className="tq-dash-value">{fmt(v)}{unit && v !== null && v !== undefined && <span className="u">{unit}</span>}{of}</div>
);
// the change: its sign, coloured only when a direction is good ("good": "none" is a measure with no better way), and its share
const Delta = ({ d, good, days }) => {
  const g = good === "down" ? -1 : good === "none" ? 0 : 1, dir = !d.change || !g ? "" : d.change * g > 0 ? "up" : "down";
  return (
    <div className="tq-dash-delta"><b className={dir}>{signed(d.change)}{d.pct !== null && d.change ? ` (${Math.round(Math.abs(d.pct) * 100)}%)` : ""}</b>
      <span>vs the {days} days before</span></div>
  );
};

export function StatTile({ c, rows, all, date, days, now, onDrill, stale }) {
  const v = aggregate(rows, c.agg, c.y), d = delta(all, date, days, c.agg, c.y, now);
  const pts = date ? timeSeries(rows, date, c.agg, c.y, { days: days || 30, now }) : [];
  return (
    <Card c={c} w={1} stale={stale} className="tq-dash-stat" onPress={() => onDrill({ title: c.title, rows })}>
      <Value v={v} unit={c.unit} />
      {d ? <Delta d={d} good={c.good} days={days} /> : <div className="tq-dash-delta"><span>{date ? DASH.no_change : DASH.right_now}</span></div>}
      {pts.length > 1 && <Spark points={pts} />}
    </Card>
  );
}

export function Progress({ c, rows, onDrill, stale }) {
  const v = aggregate(rows, c.agg, c.y) ?? 0, t = Number(c.target) || 0, pct = t ? Math.max(0, Math.min(1, v / t)) : 0;
  const left = Math.max(0, t - v);
  return (
    <Card c={c} w={1} stale={stale} className="tq-dash-stat" onPress={() => onDrill({ title: c.title, rows })}>
      <Value v={v} of={<span className="u">/ {fmt(t)}</span>} />
      <div className="tq-dash-delta"><b>{Math.round(pct * 100)}%</b><span>{left ? `${fmt(left)} ${DASH.to_go}` : DASH.target_met}</span></div>
      <div className="tq-dash-track" role="meter" aria-valuemin={0} aria-valuemax={t} aria-valuenow={v} aria-label={c.title}>
        <div className="tq-dash-fill" style={{ width: `${pct * 100}%` }} /></div>
    </Card>
  );
}

// ── the table twin of a chart: one row per mark ───────────────────────────────────────────────────────────
const TwinTable = ({ head, rows }) => (
  <div className="tq-dash-tablewrap"><table className="tq-dash-table"><thead><tr>{head.map((h) => <th key={h}>{h}</th>)}</tr></thead>
    <tbody>{rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{typeof v === "number" ? fmt(v) : v}</td>)}</tr>)}</tbody></table></div>
);

// ── ranked bars ────────────────────────────────────────────────────────────────────────────────────────────
export function Bars({ c, groups, onDrill, stale }) {
  const [tipEl, show, hide] = useTip();
  const max = Math.max(1, ...groups.map((g) => g.value ?? 0));
  // "share": each bar also said as a part of the first - a funnel's stages read as what is left of what came in
  const first = groups[0]?.value || 0, pct = (g) => (c.share && first ? `${Math.round(((g.value ?? 0) / first) * 100)}%` : "");
  const table = <TwinTable head={[cleanCol(c.x), c.agg && c.agg !== "count" ? `${c.agg} ${cleanCol(c.y)}` : "count", ...(c.share ? ["share"] : [])]}
    rows={groups.map((g) => [label(g.key), g.value, ...(c.share ? [pct(g)] : [])])} />;
  return (
    <Card c={c} w={c.w || 2} stale={stale} table={table}>
      {!groups.length ? <div className="tq-dash-none">{DASH.no_rows}</div> : (
        <div className="tq-dash-bars">
          {groups.map((g) => (
            <React.Fragment key={g.key}>
              <span className="lbl" title={label(g.key)}>{label(g.key)}</span>
              <button type="button" className="tq-dash-press" aria-label={`${label(g.key)}: ${fmt(g.value)}`}
                onClick={() => onDrill({ title: `${c.title} · ${label(g.key)}`, rows: g.rows })}
                onPointerMove={(e) => show(e, <TipRows k={label(g.key)} rows={[["", g.value]]} />)} onPointerLeave={hide} onBlur={hide}>
                <div className="bar" style={{ width: `${((g.value ?? 0) / max) * 100}%`, ...(g.other ? { background: "var(--d-other)" } : {}) }} />
              </button>
              <span className="val">{fmt(g.value)}{pct(g) && <span className="pct">{pct(g)}</span>}</span>
            </React.Fragment>
          ))}
        </div>
      )}
      {tipEl}
    </Card>
  );
}

// ── stacked columns: categories (or days) split by a second column ─────────────────────────────────────────
export function Stacked({ c, st, slots, onDrill, stale }) {
  const [tipEl, show, hide] = useTip();
  const tot = (k) => st.series.reduce((a, s) => a + (st.cells[k][s]?.value ?? 0), 0);
  const max = niceMax(Math.max(1, ...st.keys.map(tot)));       // the axis's top is a round number, and its ticks say it
  const color = (s) => (s === OTHER ? "var(--d-other)" : slotColor(slots[s]));
  const every = Math.max(1, Math.ceil(st.keys.length / 6));
  const table = <TwinTable head={[cleanCol(c.x), ...st.series.map(label), "total"]}
    rows={st.keys.map((k) => [keyLabel(k, st.dated), ...st.series.map((s) => st.cells[k][s]?.value ?? 0), tot(k)])} />;
  return (
    <Card c={c} w={c.w || 2} stale={stale} table={table}>
      {st.series.length > 1 && <div className="tq-dash-legend">{st.series.map((s) => <span key={s}><i style={{ background: color(s) }} />{label(s)}</span>)}</div>}
      {!st.keys.length || !st.series.length ? <div className="tq-dash-none">{DASH.no_rows}</div> : (<div className="tq-dash-plot">
        <div className="tq-dash-yax" aria-hidden="true">{[1, 0.5, 0].map((f) => <span key={f} style={{ top: `${(1 - f) * 100}%` }}>{fmt(max * f)}</span>)}</div>
        <div className="tq-dash-plotbody">
        <div className="tq-dash-cols">
          {st.keys.map((k) => (
            <div key={k} className="tq-dash-col" tabIndex={0} role="button" aria-label={`${keyLabel(k, st.dated)}: ${fmt(tot(k))}`}
              onPointerMove={(e) => show(e, <TipRows k={keyLabel(k, st.dated)} rows={[...st.series.filter((s) => st.cells[k][s]).map((s) => [label(s), st.cells[k][s].value, color(s)]).reverse(), ...(st.series.length > 1 ? [["total", tot(k)]] : [])]} />)}
              onPointerLeave={hide} onBlur={hide}
              onClick={(e) => { const s = e.target?.dataset?.s; const cell = s && st.cells[k][s];
                onDrill({ title: `${c.title} · ${keyLabel(k, st.dated)}${cell ? ` · ${label(s)}` : ""}`, rows: cell ? cell.rows : st.series.flatMap((x) => st.cells[k][x]?.rows || []) }); }}
              onKeyDown={(e) => { if (e.key === "Enter") onDrill({ title: `${c.title} · ${keyLabel(k, st.dated)}`, rows: st.series.flatMap((x) => st.cells[k][x]?.rows || []) }); }}>
              {st.series.map((s) => st.cells[k][s]?.value ? <div key={s} className="seg" data-s={s}
                style={{ height: `${(st.cells[k][s].value / max) * 100}%`, background: color(s) }} /> : null)}
            </div>
          ))}
        </div>
        <div className="tq-dash-xlab">{st.keys.filter((_, i) => i % every === 0 || i === st.keys.length - 1).map((k) => <span key={k}>{keyLabel(k, st.dated)}</span>)}</div>
        </div></div>)}
      {tipEl}
    </Card>
  );
}

// ── a value over time: line or area, one series, a crosshair that finds the day ────────────────────────────
function niceMax(v) { if (v <= 0) return 1; const p = 10 ** Math.floor(Math.log10(v)), m = v / p; return (m <= 1 ? 1 : m <= 2 ? 2 : m <= 5 ? 5 : 10) * p; }
export function Line({ c, points, onDrill, stale }) {
  const [ref, w] = useWidth(), [hover, setHover] = useState(null);
  const H = Number(c.h) || 170, L = 34, R = 34, T = 10, B = 22, iw = Math.max(10, w - L - R), ih = H - T - B;
  const vals = points.map((p) => p.value).filter((v) => v !== null), top = niceMax(Math.max(0, ...vals));
  const x = (i) => L + (points.length < 2 ? iw / 2 : (i / (points.length - 1)) * iw), y = (v) => T + ih - (v / top) * ih;
  const segs = []; let cur = [];
  points.forEach((p, i) => { if (p.value === null) { if (cur.length) segs.push(cur); cur = []; } else cur.push([x(i), y(p.value)]); });
  if (cur.length) segs.push(cur);
  const lastI = points.map((p) => p.value !== null).lastIndexOf(true);
  const pick = (e) => { const r = e.currentTarget.getBoundingClientRect(); const i = Math.round(((e.clientX - r.left - L) / iw) * (points.length - 1)); return Math.max(0, Math.min(points.length - 1, i)); };
  const h = hover !== null ? points[hover] : null;
  const table = <TwinTable head={["day", c.agg && c.agg !== "count" ? `${c.agg} ${cleanCol(c.y)}` : "count"]} rows={points.map((p) => [shortDay(p.key), p.value ?? "–"])} />;
  return (
    <Card c={c} w={c.w || 2} stale={stale} table={table}>
      <div ref={ref} style={{ position: "relative" }}>
        {!points.length ? <div className="tq-dash-none">{DASH.no_rows}</div> : w > 0 && (
          <svg className="tq-dash-svg" width={w} height={H} role="img" aria-label={`${c.title}, ${points.length} days`}>
            {[0, 0.5, 1].map((f) => <g key={f}><line className={f === 0 ? "axis" : "grid"} x1={L} x2={L + iw} y1={y(top * f)} y2={y(top * f)} />
              <text x={L - 6} y={y(top * f) + 4} textAnchor="end">{fmt(top * f)}</text></g>)}
            {c.kind === "area" && segs.map((s, i) => <path key={`a${i}`} className="ar" d={`M${s[0][0]},${y(0)} ${s.map(([a, b]) => `L${a},${b}`).join(" ")} L${s[s.length - 1][0]},${y(0)} Z`} />)}
            {segs.map((s, i) => s.length > 1 ? <polyline key={i} className="ln" pathLength="1" points={s.map(([a, b]) => `${a},${b}`).join(" ")} />
              : <circle key={i} className="dot" cx={s[0][0]} cy={s[0][1]} r={4} />)}
            {[0, Math.floor((points.length - 1) / 2), points.length - 1].filter((v, i, a) => a.indexOf(v) === i).map((i) => (
              <text key={i} x={x(i)} y={H - 6} textAnchor={i === 0 ? "start" : i === points.length - 1 ? "end" : "middle"}>{shortDay(points[i].key)}</text>))}
            {lastI >= 0 && <><circle className="dot" cx={x(lastI)} cy={y(points[lastI].value)} r={4} />
              <text className="end" x={x(lastI) + 7} y={y(points[lastI].value) + 4}>{fmt(points[lastI].value)}</text></>}
            {h && <><line className="xh" x1={x(hover)} x2={x(hover)} y1={T} y2={T + ih} />
              {h.value !== null && <circle className="dot" cx={x(hover)} cy={y(h.value)} r={4} />}</>}
            <rect x={L} y={T} width={iw} height={ih} fill="transparent" style={{ cursor: "pointer" }}
              onPointerMove={(e) => setHover(pick(e))} onPointerLeave={() => setHover(null)}
              onClick={(e) => { const p = points[pick(e)]; onDrill({ title: `${c.title} · ${shortDay(p.key)}`, rows: p.rows }); }} />
          </svg>
        )}
        {h && <div className="tq-dash-tip" style={{ left: Math.min(x(hover) + 10, Math.max(0, w - 130)), top: 4 }} role="status">
          <TipRows k={shortDay(h.key)} rows={[["", h.value]]} /></div>}
      </div>
    </Card>
  );
}

// ── rows: a sortable table, and a list of items that open ───────────────────────────────────────────────────
// the columns a person reads: an id is wiring (the row opens its item instead), unless it is all there is
export const readable = (cols) => { const keep = cols.filter((k) => !/(^|_)id$/.test(k)); return (keep.length ? keep : cols).slice(0, 8); };

function TableBody({ c, rows, columns, onOpen }) {
  const [sort, setSort] = useState(c.sort || "");
  const cols = c.columns?.length ? c.columns.slice(0, 8) : readable(columns);
  const shown = sortRows(rows, sort).slice(0, Number(c.limit) || 100);
  return !shown.length ? <div className="tq-dash-none">{DASH.no_rows}</div> : (
        <div className="tq-dash-tablewrap"><table className="tq-dash-table">
          <thead><tr>{cols.map((k) => <th key={k} aria-sort={sort === k ? "ascending" : sort === `-${k}` ? "descending" : "none"}>
            <button type="button" onClick={() => setSort(sort === k ? `-${k}` : k)}>{cleanCol(k)}{sort === k ? " ↑" : sort === `-${k}` ? " ↓" : ""}</button></th>)}</tr></thead>
          <tbody>{shown.map((r, i) => { const go = itemLink(r); return (
            <tr key={i} className={go ? "go" : ""} onClick={go ? () => onOpen(go) : undefined}>
              {cols.map((k) => <td key={k} title={String(r[k] ?? "")}>{typeof r[k] === "number" ? fmt(r[k]) : String(r[k] ?? "")}</td>)}</tr>); })}</tbody>
        </table></div>
  );
}

export const Table = ({ c, rows, columns, onOpen, stale }) => (
  <Card c={c} w={c.w || 4} stale={stale}><TableBody c={c} rows={rows} columns={columns} onOpen={onOpen} /></Card>
);

export function List({ c, rows, onOpen, stale }) {
  const shown = sortRows(rows, c.sort).slice(0, Number(c.limit) || 8);
  return (
    <Card c={c} w={c.w || 2} stale={stale}>
      {!shown.length ? <div className="tq-dash-none">{DASH.no_rows}</div> : (
        <ul className="tq-dash-list">{shown.map((r, i) => { const go = itemLink(r); return (
          <li key={i} className={go ? "go" : ""} tabIndex={go ? 0 : undefined} role={go ? "link" : undefined}
            onClick={go ? () => onOpen(go) : undefined} onKeyDown={go ? (e) => { if (e.key === "Enter") onOpen(go); } : undefined}>
            <span className="t" title={String(r[c.label] ?? "")}>{String(r[c.label] ?? "")}</span>
            {c.meta && <span className="m">{String(r[c.meta] ?? "")}</span>}
          </li>); })}</ul>
      )}
    </Card>
  );
}

// a pressed mark's rows: the table at the top of the grid, closed by its own button or Escape
export function Drill({ drill, columns, onOpen, onClose }) {
  useEffect(() => {
    const esc = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", esc); return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  const cols = readable(columns.length ? columns : Object.keys(drill.rows[0] || {}));
  return (
    <section className="tq-dash-card w4 tq-dash-drill" aria-label={`${DASH.rows_behind}: ${drill.title}`} data-tq-dash-drill="">
      <div className="tq-dash-h"><h3>{DASH.rows_behind} · {drill.title} · {drill.rows.length}</h3>
        <button type="button" className="tq-dash-flip" onClick={onClose}>{DASH.close}</button></div>
      <TableBody c={{ kind: "table", columns: cols }} rows={drill.rows} columns={cols} onOpen={onOpen} />
    </section>
  );
}
