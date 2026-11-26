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
import { PromptBox } from "../src/AgentSummary.jsx";
import { AttachChip, AttachRow, ImageTray } from "../src/promptImages.jsx";

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
// THE CHIP ON A PROMPT BOX, ALONE (`chips=1`, browser/chips.mjs; the owner, 2026-11-25 and again 11-26: "the blue pill does not match the
// words"): every place that draws one - the one box with what it came from, its files, an item's chip with its x; the dock's tray; a draft's
// files; his sent line - in a column `w` wide (a desk, a phone, a side panel). Invented names
const FILES = ["quarterly-vendor-spend-review-final.xlsx", "plans.pdf", "offsite-budget-march.xlsx", "notes.txt", "a.png"];
const picsOf = (names) => ({ imgs: names.map((n) => ({ name: n, path: n, image: false })), pending: [], busy: false, err: "", files: true, paths: names, drop: {}, add() {}, remove() {} });
const came = (name) => <AttachChip data-tq-came-chip="" name={name} icon={false} onClick={() => {}} />;
const ROUTINE = "Routine · Taskuary social post drafts";
const BOXES = { report: [came("Report"), []], routine: [came(ROUTINE), []], file: [null, FILES.slice(0, 1)], three: [came("Report"), FILES.slice(1, 3)],
  long3: [came(ROUTINE), [FILES[0], FILES[2]]], many: [came("Report"), FILES], item: [<AttachChip name="Weekly spend by vendor" onRemove={() => {}} />, []] };
function Chips({ w }) {
  const [text, setText] = useState("");
  return <div data-tq-chip-stage="" style={{ width: w || "100%", boxSizing: "border-box", padding: 12, display: "grid", gap: 10 }}>
    {Object.entries(BOXES).map(([k, [chip, names]]) => <div key={k} data-tq-chip-case={k} className="tq-aui-footer" style={{ border: 0 }}>
      <PromptBox text={text} setText={setText} pics={picsOf(names)} onSend={() => {}} placeholder="Message the agent…" chips={chip} /></div>)}
    <div data-tq-chip-case="dock" style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <ImageTray pics={picsOf(FILES.slice(0, 2))} sx={{ flex: "0 1 auto", maxWidth: 220, minWidth: 0, pb: 0 }} /><span>Ask anything</span></div>
    <div data-tq-chip-case="draft" style={{ width: 180, display: "flex", flexWrap: "wrap", gap: 6 }}><AttachRow sx={{ flex: "0 1 auto", pb: 0 }}>
      {FILES.slice(0, 2).map((n, i) => <AttachChip key={n} name={n} note={["44 KB", "1.2 MB"][i]} onClick={() => {}} onRemove={() => {}} />)}</AttachRow></div>
    <div data-tq-chip-case="sent" className="tq-aui-user-bubble" style={{ justifySelf: "end", maxWidth: "80%" }}><div data-tq-line-came="" style={{ marginBottom: 6, display: "flex", flexWrap: "wrap", gap: 4 }}>
      <AttachChip name="Report" /><AttachChip name={FILES[0]} /></div>Summarise this for Erin.</div>
  </div>;
}
const q = new URLSearchParams(location.search), tid = Number(q.get("task"));
const body = q.get("chips") ? <Chips w={Number(q.get("w")) || 0} /> : q.get("table") ? <div className="tq-aui-agent-body" style={{ width: 1100, padding: 24 }} data-tq-table-stage="">
  <Artifact>{q.get("fit") === "1" ? <Md text={`### Trending on GitHub today\n\n${TABLE}`} /> : <Before />}</Artifact></div> : <Stage tid={tid} />;
createRoot(document.getElementById("root")).render(<AppThemeProvider><div style={{ minHeight: "100vh", background: "var(--tq-bg, #f6f4f0)" }}>{body}</div></AppThemeProvider>);
