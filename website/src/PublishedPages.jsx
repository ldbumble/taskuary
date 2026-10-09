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
// a published page is not a run of the session: CoderReport numbers only its own session results
export const isPublished = (a) => !!a?.external_url;
const type = (p) => p?.content_type || "";
export const isHtml = (p) => !/markdown|csv/.test(type(p)) && !isPicture(p);
// drawn by <img> as itself; an SVG can carry script, so it goes through the sandboxed frame like a page
export const isPicture = (p) => /^image\//.test(type(p)) && !/svg/.test(type(p));
const label = (p) => (p.kind === "shown" ? (isPicture(p) ? "picture" : /csv/.test(type(p)) ? "table" : "page") : "published page");

function Preview({ page }) {
  const [body, setBody] = useState(null), [err, setErr] = useState("");
  const picture = isPicture(page);
  React.useEffect(() => {
    let live = true, url = "";
    api.get(page.url, picture ? { responseType: "blob" } : { responseType: "text", transformResponse: (x) => x })
      .then((r) => { if (!live) return; if (picture) { url = URL.createObjectURL(r.data); setBody(url); } else setBody(String(r.data ?? "")); })
      .catch(() => live && setErr(page.external_url ? "The saved copy could not be read - open it on claude.ai." : "The saved copy could not be read."));
    return () => { live = false; if (url) URL.revokeObjectURL(url); };
  }, [page.url, page.version, picture]);
  if (err) return <div className="tq-published-note">{err}</div>;
  if (body == null) return <div className="tq-published-note"><CircularProgress size={12} /></div>;
  if (picture) return <div className="tq-published-picture"><img src={body} alt={page.name} /></div>;
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
    : <div className="tq-published-md"><Md>{body}</Md></div>;
}

export default function PublishedPages({ pages, open: openAll = false }) {
  const [shut, setShut] = useState(() => new Set()), [opened, setOpened] = useState(() => new Set());
  if (!pages?.length) return null;
  const isOpen = (p) => (openAll ? !shut.has(p.id) : opened.has(p.id));
  const toggle = (p) => {
    const flip = (s) => { const n = new Set(s); n.has(p.id) ? n.delete(p.id) : n.add(p.id); return n; };
    openAll ? setShut(flip) : setOpened(flip);
  };
  return (
    <div className="tq-published">
      {pages.map((p) => (
        <div key={p.id} className="tq-published-page">
          <div className="tq-published-row">
            <button type="button" className="tq-published-name" disabled={!p.url} onClick={() => toggle(p)}
              title={p.url ? (isOpen(p) ? "Hide it" : "Show it here") : "No copy was kept - open it on claude.ai"}>
              <b>{p.name}</b><span>{label(p)}{p.url ? (isOpen(p) ? " · hide" : " · show here") : ""}</span>
            </button>
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
