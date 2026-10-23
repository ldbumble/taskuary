// ONE DASHBOARD, DRAWN: the filter row above everything it scopes, then the grid of presets, each reading the same sliced rows.
// The spec says what is drawn (dashboards.py validates it); the rows are the last run's. A pressed bar, column, day or tile puts
// the rows behind it at the top of the grid; a row that is a task or a message opens it.
import React, { useCallback, useMemo, useState } from "react";
import "./dashboard.css";
import { DASH } from "../words.js";
import { openAppLink } from "../appLinks.js";
import { Bars, Drill, Line, List, Progress, Stacked, StatTile, Table } from "./charts.jsx";
import { RANGES, componentRows, dateOf, groupBy, inSegment, rowsOf, segmentValues, seriesSlots, spanOf4, stacked, timeSeries, where } from "./slice.js";

export default function Dashboard({ spec, data, stale = false, onOpen = openAppLink, now: nowAt }) {
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

  const draw = (c, i) => {
    const key = `${i}-${c.kind}-${c.title}`, w = spanOf4(c);
    const rows = componentRows(spec, data, c, cut), failed = data?.sources?.[c.source]?.failed;
    const props = { c: { ...c, w }, onDrill: setDrill, stale: stale || failed };
    if (c.kind === "stat") {
      // the delta reads the period before the range, so it takes the rows before the range cut (segment and where still apply)
      const all = where(inSegment(rowsOf(data, c.source), segment, value), c.where);
      return <StatTile key={key} {...props} rows={rows} all={all} date={dateOf(spec, c)} days={days} now={now} />;
    }
    if (c.kind === "progress") return <Progress key={key} {...props} rows={rows} />;
    if (c.kind === "bar") return <Bars key={key} {...props} groups={groupBy(rows, c.x, c.agg, c.y, { limit: Number(c.limit) || 8 })} />;
    if (c.kind === "line" || c.kind === "area") return <Line key={key} {...props} points={timeSeries(rows, c.x, c.agg, c.y, { days, now })} />;
    if (c.kind === "stacked") {
      const slots = seriesSlots(rowsOf(data, c.source), c.series);      // dealt before any filter: colour follows the entity
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
          {choices.length > 0 && <label>{segment.replace(/_/g, " ")}
            <select className="tq-dash-select" value={value} onChange={(e) => { setValue(e.target.value); setDrill(null); }}>
              <option value="">{DASH.all}</option>{choices.map((v) => <option key={v} value={v}>{v}</option>)}
            </select></label>}
        </div>
      )}
      <div className="tq-dash-grid">
        {drill && <Drill drill={drill} columns={drillCols} onOpen={open} onClose={close} />}
        {(spec?.components || []).map(draw)}
      </div>
    </div>
  );
}

