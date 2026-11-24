// THE ONE REVIEW CARD, ALONE ON A PAGE (browser/one-card.mjs): each kind's review read from the fixture's task and drawn by the real component in
// the chat's own column and theme - its presses go to the fixture's server. Not the app: a stage for looking at one card at a time.
import "../src/fonts.css";
import "../src/appTheme.css";
import "../src/generalWorkspace.css";
import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { AppThemeProvider } from "../src/AppThemeProvider.jsx";
import api from "../src/api.js";
import ReviewDecision from "../src/ReviewDecision.jsx";
import BulkReview from "../src/BulkCard.jsx";
import Artifact from "../src/Artifact.jsx";
import { Md } from "../src/md.jsx";

function Stage({ tid }) {
  const [rows, setRows] = useState(null);
  const read = useCallback(() => api.get(`/api/tasks/${tid}`).then(({ data }) => setRows(data.reviews || [])), [tid]);
  useEffect(() => { read(); }, [read]);
  if (!rows) return null;
  const batch = rows.filter((r) => r.Batch), one = rows.find((r) => !r.Batch);
  return <div className="tq-aui-agent-body" style={{ width: 860, padding: 24 }} data-tq-task-page="">
    {batch.length ? <BulkReview rows={batch} tid={tid} onChanged={read} /> : one ? <ReviewDecision review={one} onChanged={read} /> : null}
  </div>;
}
// A REPORT'S TABLE IN ITS FRAME (the owner, 2026-11-24: "I hate wrapped text"): `fit=0` as it stood - the chat's fixed table, no fit - `fit=1`
// through the one Md, which fits every table (tableFit.js). Invented repositories
const LANG = ["Rust", "TypeScript", "Python", "Go", "Zig"];
const TABLE = ["| # | Repository | What it is | Language | Stars today | Stars |", "|---|---|---|---|---|---|",
  ...Array.from({ length: 15 }, (_, i) => `| ${i + 1} | ${["elementalsoul/sigil", "northwind/ledger", "orgchart/tidewater", "quietlabs/lantern-db", "paperkite/inkwell"][i % 5]}${i > 4 ? `-${i}` : ""} | ${
    ["A terminal UI for watching your coding agents work", "Double-entry books for small teams", "Org charts from your HR export", "An embedded vector store", "Markdown notes that sync"][i % 5]} | ${LANG[i % 5]} | ${(900 - i * 37).toLocaleString("en-US")} | ${(24000 - i * 1100).toLocaleString("en-US")} |`)].join("\n");
const Before = () => <div className="tq-md"><h3>Trending on GitHub today</h3><div className="tbl"><table>
  <thead><tr>{TABLE.split("\n")[0].split("|").slice(1, -1).map((c) => <th key={c}>{c.trim()}</th>)}</tr></thead>
  <tbody>{TABLE.split("\n").slice(2).map((l, i) => <tr key={i}>{l.split("|").slice(1, -1).map((c, j) => <td key={j}>{c.trim()}</td>)}</tr>)}</tbody></table></div></div>;
const q = new URLSearchParams(location.search), tid = Number(q.get("task"));
const body = q.get("table") ? <div className="tq-aui-agent-body" style={{ width: 1100, padding: 24 }} data-tq-table-stage="">
  <Artifact>{q.get("fit") === "1" ? <Md text={`### Trending on GitHub today\n\n${TABLE}`} /> : <Before />}</Artifact></div> : <Stage tid={tid} />;
createRoot(document.getElementById("root")).render(<AppThemeProvider><div style={{ minHeight: "100vh", background: "var(--tq-bg, #f6f4f0)" }}>{body}</div></AppThemeProvider>);
