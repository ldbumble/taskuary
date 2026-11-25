// ONE DASHBOARD, DRAWN: the filter row above everything it scopes, then the grid of presets, each reading the same sliced rows.
// The spec says what is drawn (dashboards.py validates it); the rows are the last run's. A pressed bar, column, day or tile puts
// the rows behind it at the top of the grid; a row that is a task or a message opens it. On the setup page each tile is drawn inside
// `frame` (its sentence and its buttons around it, DashboardEditor.jsx) and `after` closes the grid (the add box), so the page set up is
// the page drawn.
import React, { useCallback, useMemo, useState } from "react";
import "./dashboard.css";
import { DASH } from "../words.js";
import { openAppLink } from "../appLinks.js";
import { Bars, Drill, Kpis, Line, List, Pie, Progress, Stacked, StatTile, Table, Trend } from "./charts.jsx";
import { MAX_DAYS, RANGES, aggregate, trendView, clampDays, componentRows, dateOf, fmtOf, groupBy, inSegment, rowsOf, segmentValues, seriesSlots, spanOf, spanOf4, stacked, timeSeries, where } from "./slice.js";

export default function Dashboard({ spec, data, stale = false, onOpen = openAppLink, now: nowAt, frame = null, after = null }) {
  const f = spec?.filters || {};
  const [days, setDays] = useState(() => (RANGES.includes(Number(f.range)) ? Number(f.range) : 30));
  const [value, setValue] = useState("");
  const [drill, setDrill] = useState(null);
  const now = useMemo(() => nowAt || new Date(), [nowAt, data]);   // eslint-disable-line react-hooks/exhaustive-deps
  const segment = f.segment || "", choices = useMemo(() => segmentValues(data, segment), [data, segment]);
  const dated = (spec?.sources || []).some((s) => s.date);
  const cut = { days, segment, value, now };
  const close = useCallback(() => setDrill(null), []);
  const open = (hash) => onOpen?.(hash);

  // a number as a stat tile or a strip's cell draws it: its rows, the rows before the range (its delta), and what else it says (`also`)
  const statOf = (c) => {
    const base = componentRows(spec, data, { ...c, where: null }, cut);
    return { rows: componentRows(spec, data, c, cut), all: where(inSegment(rowsOf(data, c.source), segment, value), c.where), date: dateOf(spec, c),
      days: spanOf(c, days), now, also: (c.also || []).map((a) => ({ label: a.label, value: aggregate(where(base, a.where), a.agg, a.y, a.per) })) };
  };
  const draw = (c, i) => {
    const key = `${i}-${c.kind}-${c.title}`, w = spanOf4(c);
    const rows = componentRows(spec, data, c, cut), failed = data?.sources?.[c.source]?.failed;
    const props = { c: { ...c, w, i, fmt: fmtOf(c) }, onDrill: setDrill, stale: stale || failed };
    // a series' colour follows its entity: by the tile's own `order` where it gives one (triage, Advisor, tasks, Assistant - the same colour
    // on the columns and the pie), else by its share of all the source's rows, dealt before any filter
    const slotsOf = (col) => (c.order?.length ? Object.fromEntries(c.order.map((k, n) => [String(k), n])) : seriesSlots(rowsOf(data, c.source), col));
    if (c.kind === "stat") return <StatTile key={key} {...props} {...statOf(c)} />;
    if (c.kind === "kpis") return <Kpis key={key} {...props} cells={(c.items || []).map((x) => ({ c: x, ...statOf(x) }))} />;
    if (c.kind === "trend") {
      // ...one chart, its measure and split switched on its top: each is its source's rows per day, split by a column, coloured by its order
      return <Trend key={key} {...props} metrics={c.metrics} view={(mi, si) => trendView(spec, data, c.metrics[mi], si, cut)} />;
    }
    if (c.kind === "progress") return <Progress key={key} {...props} rows={rows} />;
    if (c.kind === "pie") { const slots = slotsOf(c.x);      // ...a slice wears its entity's colour too
      return <Pie key={key} {...props} groups={groupBy(rows, c.x, c.agg, c.y, { limit: Number(c.limit) || 6, order: c.order }).map((g) => ({ ...g, slot: slots[g.key] }))} />; }
    if (c.kind === "bar") return <Bars key={key} {...props} groups={groupBy(rows, c.x, c.agg, c.y, { limit: Number(c.limit) || 8, order: c.order })} />;
    if (c.kind === "line" || c.kind === "area") return <Line key={key} {...props} points={timeSeries(rows, c.x, c.agg, c.y, { days, now })} />;
    if (c.kind === "stacked") {
      const slots = slotsOf(c.series);
      return <Stacked key={key} {...props} slots={slots} st={stacked(rows, c.x, c.series, c.agg, c.y, { slots, days, now, limit: Number(c.limit) || 12 })} />;
    }
    const columns = data?.sources?.[c.source]?.columns || [];
    if (c.kind === "table") return <Table key={key} {...props} rows={rows} columns={columns} onOpen={open} />;
    if (c.kind === "list") return <List key={key} {...props} rows={rows} onOpen={open} />;
    return null;
  };
  const drillCols = drill ? Object.keys(drill.rows[0] || {}) : [];
  return (
    <div className="tq-dash" data-tq-dashboard="">
      {(dated || choices.length > 0) && (
        <div className="tq-dash-bar" role="toolbar" aria-label="Filters">
          {dated && <div className="tq-dash-seg" role="group" aria-label="Date range">
            {RANGES.map((d) => <button key={d} type="button" aria-pressed={days === d} onClick={() => { setDays(d); setDrill(null); }}>{DASH.ranges[String(d)]}</button>)}
          </div>}
          {/* ...and any number of days between, on a slider: every tile, chart and delta re-cuts as it moves */}
          {dated && <label className="tq-dash-slide"><span>{!days ? DASH.ranges["0"] : days === 1 ? DASH.last_day : DASH.last_days.replace("{n}", days)}</span>
            <input type="range" min={1} max={MAX_DAYS} step={1} value={days || MAX_DAYS} aria-label={DASH.range_slider}
              style={{ "--p": `${(((days || MAX_DAYS) - 1) / (MAX_DAYS - 1)) * 100}%` }}
              onChange={(e) => { setDays(clampDays(e.target.value)); setDrill(null); }} /></label>}
          {choices.length > 0 && <label>{segment.replace(/_/g, " ")}
            <select className="tq-dash-select" value={value} onChange={(e) => { setValue(e.target.value); setDrill(null); }}>
              <option value="">{DASH.all}</option>{choices.map((v) => <option key={v} value={v}>{v}</option>)}
            </select></label>}
        </div>
      )}
      <div className="tq-dash-grid">
        {drill && <Drill drill={drill} columns={drillCols} onOpen={open} onClose={close} />}
        {(spec?.components || []).map((c, i) => (frame ? <React.Fragment key={i}>{frame(c, i, draw(c, i), spanOf4(c))}</React.Fragment> : draw(c, i)))}
        {after}
      </div>
    </div>
  );
}

