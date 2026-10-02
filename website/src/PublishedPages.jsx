// Pages the agent published with Claude Code's Artifact tool, at the foot of its session (claude_artifacts.py).
// The link opens the page on claude.ai; the preview draws the copy the task kept, in place - claude.ai refuses to be
// framed by another site, and the copy is the same file the agent published (the owner, 2026-10-02: "show it in the
// agent session on bottom as link or if you click in it as rendered in line").
import React, { useState } from "react";
import { Button, CircularProgress } from "@mui/material";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import api from "./api.js";
import { Md } from "./md.jsx";
import "./publishedPages.css";

// sandboxed WITHOUT allow-same-origin: the page's scripts run (charts, tabs) but in an opaque origin -
// no Taskuary token, no cookies, no reach into this window
export const SANDBOX = "allow-scripts allow-popups allow-popups-to-escape-sandbox";
// a published page is not a run of the session: CoderReport numbers only its own session results
export const isPublished = (a) => !!a?.external_url;
export const isHtml = (p) => !/markdown/.test(p?.content_type || "");

function Preview({ page }) {
  const [text, setText] = useState(null), [err, setErr] = useState("");
  React.useEffect(() => {
    let live = true;
    api.get(page.url, { responseType: "text", transformResponse: (x) => x })
      .then((r) => live && setText(String(r.data ?? ""))).catch(() => live && setErr("The saved copy could not be read - open it on claude.ai."));
    return () => { live = false; };
  }, [page.url, page.version]);
  if (err) return <div className="tq-published-note">{err}</div>;
  if (text == null) return <div className="tq-published-note"><CircularProgress size={12} /></div>;
  return isHtml(page)
    ? <iframe className="tq-published-frame" title={page.name} sandbox={SANDBOX} srcDoc={text} />
    : <div className="tq-published-md"><Md>{text}</Md></div>;
}

export default function PublishedPages({ pages }) {
  const [open, setOpen] = useState(null);
  if (!pages?.length) return null;
  return (
    <div className="tq-published">
      {pages.map((p) => (
        <div key={p.id} className="tq-published-page">
          <div className="tq-published-row">
            <button type="button" className="tq-published-name" disabled={!p.url} onClick={() => setOpen(open === p.id ? null : p.id)}
              title={p.url ? (open === p.id ? "Hide the page" : "Show the page here") : "No copy was kept - open it on claude.ai"}>
              <b>{p.name}</b><span>published page{p.url ? (open === p.id ? " · hide" : " · show here") : ""}</span>
            </button>
            <Button size="small" variant="outlined" href={p.external_url} target="_blank" rel="noopener noreferrer"
              endIcon={<OpenInNewIcon sx={{ fontSize: 13 }} />}>Open on claude.ai</Button>
          </div>
          {open === p.id && p.url && <Preview page={p} />}
        </div>
      ))}
    </div>
  );
}
