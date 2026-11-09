// Markdown, rendered. An agent-written report arrives as markdown - headings, a table of repos,
// bold star counts - and showing the SOURCE of that made a 106-line report unreadable. Report
// bodies only: an email that happens to contain an asterisk is not a document.
import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Box, Button, Dialog, DialogContent, DialogTitle, IconButton } from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import { BORDER, DIM, INK, PANEL, mono } from "./theme.jsx";

import { linkRefs, looksMd, refParts } from "./mdText.js";
import { appLink, linkRoad, openAppLink, ownPath } from "./appLinks.js";
import { codeLocalPaths, localFile, plainCitations } from "./taskOutputs.js";
import CopyCorner from "./CopyCorner.jsx";
import { attUrl, isPdf, PdfView, saveFile } from "./Attachments.jsx";
export { looksMd };

const TASK_LINK = /#task=(\d+)/;
// A WEB LINK IN A CHAT'S ANSWER OPENS OVER IT, as a file the agent made does (the owner, 2026-11-05: "links should show in popup view as well
// like preview of all other files"): inside a LinkPopups - an agent's turns, an item's answers - an http(s) link is a framed page with its
// address for a title, Open in browser and Close. A site that refuses framing stays blank, which the page cannot always tell, so it says so
const LinkPop = React.createContext(null);
export const isWebLink = (h) => /^https?:\/\//i.test(String(h || "").trim());
export function LinkDialog({ url, onClose }) {
  if (!url) return null;
  const out = () => { window.open(url, "_blank", "noopener,noreferrer"); onClose(); };
  return (
    <Dialog open onClose={onClose} maxWidth="lg" fullWidth data-tq-link-dialog={url}>
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1, py: 1, fontSize: 14 }}>
        <span title={url} style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: 600 }}>{url}</span>
        <Button size="small" onClick={out} data-tq-link-out="">Open in browser</Button>
        <IconButton size="small" aria-label="Close" onClick={onClose}><CloseIcon fontSize="small" /></IconButton>
      </DialogTitle>
      <DialogContent dividers sx={{ p: 0, display: "flex", flexDirection: "column" }}>
        <iframe src={url} title={url} sandbox="allow-scripts allow-same-origin allow-forms allow-popups" referrerPolicy="no-referrer"
          style={{ border: 0, width: "100%", height: "70vh", background: "#fff" }} />
        <Box data-tq-link-blank="" sx={{ px: 1.5, py: 0.75, fontSize: 12, color: DIM, borderTop: `1px solid ${BORDER}` }}>
          If it stays blank, this site won't show inside Taskuary - <Box component="button" type="button" onClick={out}
            sx={{ border: 0, p: 0, bgcolor: "transparent", color: "#55697a", fontWeight: 600, cursor: "pointer", font: "inherit" }}>Open in browser</Box>
        </Box>
      </DialogContent>
    </Dialog>
  );
}
export function LinkPopups({ children }) {
  const [url, setUrl] = React.useState("");
  return <LinkPop.Provider value={setUrl}>{children}<LinkDialog url={url} onClose={() => setUrl("")} /></LinkPop.Provider>;
}
const fileName = (u) => { const n = String(u).split(/[?#]/)[0].split("/").pop() || "PDF"; try { return decodeURIComponent(n); } catch { return n; } };
// `onTask` (the chat's): a task link opens it as a press of its rail row does, and a bare ref keeps its own words
const A = ({ href, children, onTask }) => {
  // ...BY ITS ROAD (appLinks.linkRoad, the owner 2026-11-02): the web alone opens a new tab - the system browser, from the desktop window -
  // and the app's own address, written out whole or as a path, stays in the window like its #links
  const road = linkRoad(href), own = ownPath(href) || "", hash = own.includes("#") ? own.slice(own.indexOf("#")) : href;
  const m = road === "task" ? TASK_LINK.exec(hash || "") : null, bare = !!m && /^TQ-\d+$/.test(String(React.Children.toArray(children).join("")));
  // ...and a page of the app itself (appLinks.js): opened on the canvas here, never a new browser tab
  const page = road === "page" ? appLink(hash) || String(hash).trim() : null;
  // ...and a file an agent made, as the Assistant links it (lookups.outputs_find): the Result's own Download - one tap saves it
  const file = road === "file";
  // ...SAVED where it is (Attachments.saveFile), never a new tab: the desktop window handed that tab to the system browser, and a file
  // moved or deleted since the link was written opened a raw 404 there - now it is a line beside the link
  const [err, setErr] = React.useState(""), [saved, setSaved] = React.useState(""), raw = file ? own : href;
  // ...but a PDF is READ under the link, Download beside it (Attachments.PdfView; the owner, 2026-11-04)
  const [view, setView] = React.useState(false), pdf = file && isPdf({ name: fileName(raw) });
  const pop = React.useContext(LinkPop), web = !!pop && road === "outside" && isWebLink(href);
  if (file) href = attUrl({ url: own }, true);
  return (<>
    <a href={href} target={road === "outside" ? "_blank" : undefined} data-tq-file-link={file ? "" : undefined} data-tq-web-link={web ? "" : undefined} aria-expanded={pdf ? view : undefined} data-tq-road={road} rel="noreferrer" style={{ color: "#55697a", fontWeight: 600, textDecoration: "none" }}
      data-tq-task-link={m ? m[1] : undefined}
      onClick={(e) => {
        if (m) { e.preventDefault(); if (onTask) onTask(Number(m[1])); else openAppLink(`task=${m[1]}`); }
        else if (page) { e.preventDefault(); openAppLink(page); }
        else if (web) { e.preventDefault(); pop(String(href).trim()); }
        else if (pdf) { e.preventDefault(); setView((v) => !v); }
        else if (file) { e.preventDefault(); setErr(""); setSaved(""); saveFile({ url: raw }).then(setSaved, (x) => setErr(x.message)); }
      }}>
      {m && !bare ? `open TQ-${String(m[1]).padStart(4, "0")} →` : children}
    </a>
    {err && <span data-tq-file-error="" style={{ color: DIM, fontWeight: 400 }}> — {err}</span>}
    {saved && <span data-tq-file-saved="" style={{ color: DIM, fontWeight: 400 }}> — {saved}</span>}
    {view && <span data-tq-file-link-view="" style={{ display: "block" }}>
      <PdfView file={{ url: raw, name: fileName(raw) }} onClose={() => setView(false)} /></span>}
  </>);
};

const sx = {
  // a URL or a path longer than the column breaks where it must; it ran past the chat's edge and was cut (2026-10-06)
  textAlign: "left", color: INK, fontSize: 13.5, lineHeight: 1.55, overflowWrap: "break-word",
  "& h1, & h2, & h3, & h4": { fontWeight: 600, color: INK, lineHeight: 1.3, mt: 1.4, mb: 0.5 },
  "& h1": { fontSize: 17 }, "& h2": { fontSize: 15, pb: 0.35, borderBottom: `1px solid ${BORDER}` }, "& h3, & h4": { fontSize: 13.5 },
  "& p": { m: 0, mb: 0.75 }, "& ul, & ol": { m: 0, mb: 0.75, pl: 2.5 }, "& li": { mb: 0.25 },
  "& code": { ...mono, fontSize: 12, bgcolor: PANEL, px: 0.5, borderRadius: 0.5 },
  "& pre": { ...mono, fontSize: 12, bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 1, p: 1, overflowX: "auto" },
  "& pre code": { bgcolor: "transparent", p: 0 },
  "& blockquote": { m: 0, mb: 0.75, pl: 1.25, borderLeft: `3px solid ${BORDER}`, color: DIM },
  "& hr": { border: 0, borderTop: `1px solid ${BORDER}`, my: 1 },
  // a wide table scrolls inside its own box; the panel never grows sideways
  "& .tbl": { overflowX: "auto", mb: 0.75 },
  "& table": { borderCollapse: "collapse", fontSize: 12.5, minWidth: "100%" },
  // a cell never splits a word: an `anywhere` inherited from the card let the table shrink a column below its
  // longest word, so "11" stood on two lines and "JavaScript" broke after "JavaScri" (the owner, 2026-09-25).
  // break-word still breaks a word too long for any line; the table scrolls sideways in .tbl before that.
  "& th, & td": { border: `1px solid ${BORDER}`, px: 0.9, py: 0.45, textAlign: "left", verticalAlign: "top",
    overflowWrap: "break-word", wordBreak: "normal" },
  "& .ref": { whiteSpace: "nowrap" },
  "& th": { bgcolor: PANEL, fontWeight: 600, whiteSpace: "nowrap" },
  "& > :first-of-type": { mt: 0 }, "& > :last-child": { mb: 0 },
};

// A picture in markdown is never fetched: the text came from a model or a stranger, and loading it is a
// request to whatever server they named (the page's CSP refuses it too). It stays a link the owner can choose to open.
const Img = ({ src, alt }) => <A href={src}>{`[image${alt ? `: ${alt}` : ""}]`}</A>;

// A LOCAL PATH IS THE FILE (the owner, 2026-11-09: "this should be link"): inside a LocalFiles - a task's chat, {tid} - a whole path into that
// task's outputs folder (taskOutputs.localFile), in a code span or bare, is a link that opens it, and a picture is drawn small under it - a
// press opens it whole. Any other path stays the words it was: the server serves that folder alone (outputs.resolve)
export const LocalFiles = React.createContext(null);
const LocalPath = ({ f, children }) => {
  const [big, setBig] = React.useState(false), src = attUrl({ url: f.url });
  return (<>
    {/* ...a picture opens over the chat; any other file as a link to a file does (A: saved, a PDF read under it) */}
    {f.image ? <a href={src} data-tq-file-link="" onClick={(e) => { e.preventDefault(); setBig(true); }} style={{ color: "#55697a", fontWeight: 600, textDecoration: "none" }}>
      <code data-tq-local-path={f.rel}>{children}</code></a>
      : <A href={f.url}><code data-tq-local-path={f.rel}>{children}</code></A>}
    {f.image && <span data-tq-local-picture="" style={{ display: "block", margin: "4px 0 6px" }}>
      <img src={src} alt={f.name} onClick={() => setBig(true)} title="Open it whole"
        style={{ maxWidth: "100%", maxHeight: 220, objectFit: "contain", cursor: "zoom-in", border: `1px solid ${BORDER}`, borderRadius: 4, background: "#fff" }} /></span>}
    {big && <Dialog open onClose={() => setBig(false)} maxWidth="lg" data-tq-local-picture-big="">
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1, py: 1, fontSize: 14 }}>
        <span style={{ flex: 1, fontWeight: 600 }}>{f.name}</span>
        <IconButton size="small" aria-label="Close" onClick={() => setBig(false)}><CloseIcon fontSize="small" /></IconButton></DialogTitle>
      <DialogContent dividers sx={{ p: 1 }}><img src={src} alt={f.name} style={{ maxWidth: "100%", display: "block", margin: "0 auto" }} /></DialogContent>
    </Dialog>}
  </>);
};
const Code = ({ children, node, ...rest }) => {
  const at = React.useContext(LocalFiles), kids = React.Children.toArray(children);
  const f = at && kids.length === 1 && typeof kids[0] === "string" ? localFile(kids[0], at.tid) : null;
  return f ? <LocalPath f={f}>{children}</LocalPath> : <code {...rest}>{children}</code>;
};

const keepRefs = (kids) => React.Children.map(kids, (k) => typeof k !== "string" ? k
  : refParts(k).map((p, i) => i % 2 ? <span key={i} className="ref">{p}</span> : p));
const Td = ({ children, node, ...rest }) => <td {...rest}>{keepRefs(children)}</td>;

// ...a code block - a command, a prompt to paste somewhere - copies at its corner (CopyCorner)
const Pre = ({ children, node, ...rest }) => { const box = React.useRef(null);
  return <div className="tq-copy-host"><pre ref={box} {...rest}>{children}</pre><CopyCorner text={() => box.current?.innerText || ""} /></div>; };

// ...and one line of it, inline: a brief's bullet keeps its bold and its links without a paragraph around them (ReportBrief)
export const MdLine = ({ text }) => (
  <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: A, img: Img, p: ({ children }) => <>{children}</> }}>{plainCitations(text || "")}</ReactMarkdown>
);
export const Md = ({ text, onTask = null }) => {
  const at = React.useContext(LocalFiles), words = at ? codeLocalPaths(plainCitations(text || ""), at.tid) : plainCitations(text || "");
  return (
  <Box sx={sx}>
    <ReactMarkdown remarkPlugins={[remarkGfm]}
      components={{ a: onTask ? (p) => <A {...p} onTask={onTask} /> : A, img: Img, td: Td, pre: Pre, code: Code, table: ({ children }) => <div className="tbl"><table>{children}</table></div> }}>
      {/* a Codex citation marker reads as the file's name wherever an answer is shown; the chat makes it a file (taskOutputs.js) */}
      {/* ...and in the chat a task it names is a link that opens it (linkRefs); a path into the task's own folder, the file (Code) */}
      {onTask ? linkRefs(words) : words}
    </ReactMarkdown>
  </Box>
  );
};
