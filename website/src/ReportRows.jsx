// A DATA REPORT, READ (the owner, 2026-10-28: "the report on the demo site looks horrible. make it look better"): its name and one line of
// what it found, then the chart and the table side by side - the chart drawn live from the rows in the dashboards' own palette and marks
// (dashboard/charts.jsx), the table with its numbers right-aligned in tabular figures - and the files it carries as one row of chips.
// Every data report on the table is drawn by this, the demo's and a real install's alike (assistantCards FullText `report`).
import React, { useMemo, useRef, useState } from "react";
import "./dashboard/dashboard.css";
import "./reportRows.css";
import { Bars, Line } from "./dashboard/charts.jsx";
import { Attachments } from "./Attachments.jsx";
import { colWords, fmtNum, numOf, places, reportShape, reportSummary } from "./reportRows.js";

const BARS = 12;     // a ranking past a dozen is a table's job; the table beside it holds every row

export default function ReportRows({ rows, name, mid }) {
  const shape = useMemo(() => reportShape(rows), [rows]);
  const said = useMemo(() => reportSummary(rows, shape), [rows, shape]);
  const p = useMemo(() => Object.fromEntries(shape.nums.map((c) => [c, places(rows, c)])), [rows, shape]);
  const [on, setOn] = useState(-1), body = useRef(null);
  const { lab, val } = shape;
  // a pressed mark lights its row in the table, and brings it into view
  const drill = ({ rows: [r] = [] }) => {
    const i = rows.indexOf(r); setOn(i);
    body.current?.querySelector(`tr[data-i="${i}"]`)?.scrollIntoView({ block: "nearest" });
  };
  const what = lab ? `${colWords(val)} by ${colWords(lab)}` : colWords(val);
  const c = { kind: shape.chart, title: what.charAt(0).toUpperCase() + what.slice(1), x: lab, y: val, agg: "sum", w: 2, twin: false, h: rows.length > 8 ? 260 : 200 };
  const marks = rows.map((r, i) => ({ key: lab ? String(r[lab] ?? "") : `#${i + 1}`, value: numOf(r[val]), rows: [r] }));
  const cell = (r, k) => (shape.nums.includes(k) ? fmtNum(numOf(r[k]), p[k]) : r[k] == null ? "" : String(r[k]));
  return (
    <div className="tq-dash tq-rep" data-tq-report-rows="">
      <header className="tq-rep-h">
        {name && <h2>{name}</h2>}
        <p data-tq-report-summary="">{said}</p>
      </header>
      <div className={`tq-rep-grid${shape.chart ? "" : " solo"}`}>
        {shape.chart && <div className="tq-rep-chart" data-tq-report-chart={shape.chart}>
          {shape.chart === "line" ? <Line c={c} points={marks} onDrill={drill} />
            : <Bars c={c} groups={marks.slice(0, BARS).map((m) => ({ ...m, value: m.value ?? 0 }))} onDrill={drill} />}
        </div>}
        <div className="tq-rep-table" ref={body} data-tq-report-table="">
          <table className="tq-rep-rows">
            <thead><tr>{shape.cols.map((k) => <th key={k} className={shape.nums.includes(k) ? "n" : ""} scope="col">{colWords(k)}</th>)}</tr></thead>
            <tbody>{rows.map((r, i) => (
              <tr key={i} data-i={i} className={on === i ? "on" : ""}>
                {shape.cols.map((k) => <td key={k} className={shape.nums.includes(k) ? "n" : ""} title={cell(r, k)}>{cell(r, k)}</td>)}
              </tr>))}</tbody>
          </table>
        </div>
      </div>
      {/* the spreadsheet and the chart's picture (what an email of it carries), as chips: the chart is already drawn above */}
      {mid != null && <Attachments messageId={mid} dense asFiles={shape.chart ? (a) => a.content_type === "image/svg+xml" : null} />}
    </div>
  );
}
