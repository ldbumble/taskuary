// Pages the agent published with Claude Code's Artifact tool (claude_artifacts.py), and files a chat chose to SHOW the owner
// (selfclose.SHOW_LINE: a chart, a picture, a table or a small page, only when it makes the answer easier to understand).
// The link opens a published page on claude.ai; the preview draws the copy the task kept, in place - claude.ai refuses to be
// framed by another site, and the copy is the same file the agent published (the owner, 2026-10-02: "show it in the
// agent session on bottom as link or if you click in it as rendered in line"). In the chat each sits under the answer that
// made it, open (2026-10-09: the agent chose to show it); under a terminal they stay one row each until clicked.
import React, { useState } from "react";
import { Button, CircularProgress } from "@mui/material";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import api from "./api.js";
import { attUrl } from "./Attachments.jsx";
import { Md } from "./md.jsx";
import { csvRows, lockDown } from "./shownPages.js";
import "./publishedPages.css";

// sandboxed WITHOUT allow-same-origin: the page's scripts run (charts, tabs) but in an opaque origin -
// no Taskuary token, no cookies, no reach into this window
export const SANDBOX = "allow-scripts allow-popups allow-popups-to-escape-sandbox";
// a published page is not a run of the session: AgentReport numbers only its own session results
export const isPublished = (a) => !!a?.external_url;
const type = (p) => p?.content_type || "";
export const isHtml = (p) => !/markdown|csv/.test(type(p)) && !isPicture(p);
// drawn by <img> as itself; an SVG can carry script, so it goes through the sandboxed frame like a page
export const isPicture = (p) => /^image\//.test(type(p)) && !/svg/.test(type(p));
// ...and a file the agent made for its task (taskOutputs.js, outputs.py): previewed by what it is, everything else Download only
const isOutput = (p) => p?.kind === "output";
const OUTPUT_LABEL = { sheet: "spreadsheet", table: "table", pdf: "PDF", picture: "picture", text: "text", page: "page" };
const label = (p) => isOutput(p) ? (OUTPUT_LABEL[p.preview] || (/\.xlsm?$/i.test(p.name) ? "spreadsheet" : "file")) : (p.kind === "shown" ? (isPicture(p) ? "picture" : /csv/.test(type(p)) ? "table" : "page") : "published page");

// a workbook's sheet as the server read it (outputs.sheet): capped rows and columns, a tab per sheet
function SheetPreview({ page }) {
  const [sheet, setSheet] = useState(""), [got, setGot] = useState(null), [err, setErr] = useState("");
  React.useEffect(() => {
    let live = true;
    setErr("");
    api.get(page.url, { params: { preview: true, ...(sheet ? { sheet } : {}) } })
      .then((r) => live && setGot(r.data))
      .catch((e) => live && setErr(e?.response?.data?.detail || "This workbook could not be previewed - Download it to open it."));
    return () => { live = false; };
  }, [page.url, sheet]);
  if (err) return <div className="tq-published-note">{err}</div>;
  if (!got) return <div className="tq-published-note"><CircularProgress size={12} /></div>;
  const [head, ...rows] = got.rows || [];
  const cut = [got.more_rows && `${got.max_rows} rows`, got.more_cols && `${got.max_cols} columns`].filter(Boolean).join(" and ");
  return (
    <div data-tq-sheet-preview="">
      {got.sheets?.length > 1 && (
        <div className="tq-published-tabs" role="tablist">
          {got.sheets.map((n) => <button key={n} type="button" role="tab" aria-selected={n === got.sheet}
            className={n === got.sheet ? "on" : ""} onClick={() => setSheet(n)}>{n}</button>)}
        </div>
      )}
      {head ? (
        <div className="tq-published-table"><table>
          <thead><tr>{head.map((h, i) => <th key={i}>{h}</th>)}</tr></thead>
          <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
        </table></div>
      ) : <div className="tq-published-note">This sheet is empty.</div>}
      {cut && <div className="tq-published-note">The first {cut} are shown - Download it for the whole sheet.</div>}
    </div>
  );
}

function Preview({ page }) {
  const [body, setBody] = useState(null), [err, setErr] = useState("");
  const sheet = isOutput(page) && page.preview === "sheet", pdf = isOutput(page) && page.preview === "pdf";
  const picture = isPicture(page) || pdf, text = isOutput(page) && page.preview === "text" && !/markdown/.test(type(page));
  React.useEffect(() => {
    if (sheet) return undefined;
    let live = true, url = "";
    api.get(page.url, picture ? { responseType: "blob" } : { responseType: "text", transformResponse: (x) => x })
      .then((r) => {
        if (!live) return;
        if (picture) { url = URL.createObjectURL(pdf ? new Blob([r.data], { type: "application/pdf" }) : r.data); setBody(url); }
        else setBody(String(r.data ?? ""));
      })
      .catch(() => live && setErr(page.external_url ? "The saved copy could not be read - open it on claude.ai." : "The saved copy could not be read."));
    return () => { live = false; if (url) URL.revokeObjectURL(url); };
  }, [page.url, page.version, picture, pdf, sheet]);
  if (sheet) return <SheetPreview page={page} />;
  if (err) return <div className="tq-published-note">{err}</div>;
  if (body == null) return <div className="tq-published-note"><CircularProgress size={12} /></div>;
  if (pdf) return <iframe className="tq-published-frame" title={page.name} src={body} />;
  if (picture) return <div className="tq-published-picture"><img src={body} alt={page.name} /></div>;
  if (text) return <pre className="tq-published-text">{body.length > 200000 ? `${body.slice(0, 200000)}\n…` : body}</pre>;
  if (/csv/.test(type(page))) {
    const [head, ...rows] = csvRows(body);
    return (
      <div className="tq-published-table"><table>
        <thead><tr>{(head || []).map((h, i) => <th key={i}>{h}</th>)}</tr></thead>
        <tbody>{rows.slice(0, 500).map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody>
      </table></div>
    );
  }
  return isHtml(page)
    ? <iframe className="tq-published-frame" title={page.name} sandbox={SANDBOX} srcDoc={lockDown(body)} />
    : <div className="tq-published-md"><Md text={body} /></div>;
}

// a file the agent made: its name and kind, Preview where it has one, and Download - or, gone from the folder, says so
const sizeOf = (n) => n < 1024 ? `${n} B` : n < 1048576 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`;
function OutputFile({ file: p, open, onToggle, verb = "" }) {
  const can = !!p.preview && !p.missing;
  return (
    <div className="tq-published-page" data-tq-output={p.path}>
      <div className="tq-published-row">
        <div className="tq-published-name tq-published-file">
          <b>{p.name}</b>
          <span>{p.missing ? "not in this task's files any more" : `${label(p)}${p.size ? ` · ${sizeOf(p.size)}` : ""}`}</span>
        </div>
        {can && <Button size="small" variant={open ? "contained" : "outlined"} disableElevation onClick={onToggle}
          title={open ? "Hide the preview" : "Show it here"} data-tq-open={verb ? "" : undefined}>{open ? (verb ? "Hide" : "Hide preview") : verb || "Preview"}</Button>}
        {!p.missing && <Button size="small" href={attUrl(p, true)} title="Save a copy">Download</Button>}
      </div>
      {p.note && !p.missing && <div className="tq-published-note">{p.note}</div>}
      {open && can && <Preview page={p} />}
    </div>
  );
}

// `verb`: the press that shows each one is a button named for it ("Open", the Result's What it made) rather than the name's own " · show here"
export default function PublishedPages({ pages, open: openAll = false, verb = "" }) {
  const [shut, setShut] = useState(() => new Set()), [opened, setOpened] = useState(() => new Set());
  if (!pages?.length) return null;
  const isOpen = (p) => (openAll ? !shut.has(p.id) : opened.has(p.id));
  const toggle = (p) => {
    const flip = (s) => { const n = new Set(s); n.has(p.id) ? n.delete(p.id) : n.add(p.id); return n; };
    openAll ? setShut(flip) : setOpened(flip);
  };
  return (
    <div className="tq-published">
      {pages.map((p) => isOutput(p) ? <OutputFile key={p.id} file={p} open={isOpen(p)} onToggle={() => toggle(p)} verb={verb} /> : (
        <div key={p.id} className="tq-published-page">
          <div className="tq-published-row">
            <button type="button" className="tq-published-name" disabled={!p.url} onClick={() => toggle(p)}
              title={p.url ? (isOpen(p) ? "Hide it" : "Show it here") : "No copy was kept - open it on claude.ai"}>
              <b>{p.name}</b><span>{label(p)}{p.url && !verb ? (isOpen(p) ? " · hide" : " · show here") : ""}</span>
            </button>
            {p.url && verb && <Button size="small" variant={isOpen(p) ? "contained" : "outlined"} disableElevation data-tq-open=""
              onClick={() => toggle(p)} title={isOpen(p) ? "Hide it" : "Show it here"}>{isOpen(p) ? "Hide" : verb}</Button>}
            {p.url && (
              <Button size="small" href={attUrl(p, true)} title="Save a copy">Download</Button>
            )}
            {p.external_url && (
              <Button size="small" variant="outlined" href={p.external_url} target="_blank" rel="noopener noreferrer"
                endIcon={<OpenInNewIcon sx={{ fontSize: 13 }} />}>Open on claude.ai</Button>
            )}
          </div>
          {isOpen(p) && p.url && <Preview page={p} />}
        </div>
      ))}
    </div>
  );
}
