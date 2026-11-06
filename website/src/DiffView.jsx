// THE DIFF AS AN EDITOR SHOWS IT (the owner, 2026-11-06: "i do like you can review the code diffs if you want... i like the editor that you can
// see the code"): each file a row that folds - its name, + and − - and under it the hunks, old and new line numbers down the side, the code
// coloured by its language (diffView.js; no highlighter library). One viewer for an edit in the chat and for the landing card's whole diff.
// With `marks` the owner reviews it: each part Keep or Revert, and the landing card takes the reverted ones back out before it lands.
import React, { useState } from "react";
import { headerOf, langOf, numbered, tokens } from "./diffView.js";
import "./diffView.css";

const Code = ({ text, lang }) => tokens(text, lang).map((x, i) => (x.t ? <span key={i} className={`tq-dv-${x.t}`}>{x.s}</span> : x.s));
const ROW = { "+": "add", "-": "del", "\\": "note", " ": "ctx" };

export function Hunk({ h, path, mark, onMark }) {
  const lang = langOf(path);
  return (
    <div className={`tq-dv-hunk${mark === "revert" ? " tq-dv-reverting" : ""}`} data-tq-hunk="">
      <div className="tq-dv-head">
        <span className="tq-dv-at">{h.head || headerOf(h)}</span>
        {onMark && <span className="tq-dv-marks" role="group" aria-label="Keep or revert this part">
          <button type="button" aria-pressed={mark !== "revert"} data-tq-hunk-keep="" onClick={() => onMark("keep")}>Keep</button>
          <button type="button" aria-pressed={mark === "revert"} data-tq-hunk-revert="" onClick={() => onMark("revert")}>Revert</button>
        </span>}
      </div>
      <table className="tq-dv-lines"><tbody>
        {numbered(h).map((r, i) => (
          <tr key={i} className={`tq-dv-${ROW[r.op] || "ctx"}`}>
            <td className="tq-dv-n">{r.old ?? ""}</td><td className="tq-dv-n">{r.new ?? ""}</td>
            <td className="tq-dv-op">{r.op === " " ? "" : r.op === "\\" ? "" : r.op}</td>
            <td className="tq-dv-code">{r.op === "\\" ? r.text.trim() : <Code text={r.text} lang={lang} />}</td>
          </tr>))}
      </tbody></table>
    </div>
  );
}

// one file: its row folds; `marks` {"path#index": "revert"} and `onMark(key, mark)` turn review on
export function FileDiff({ file, open, onToggle, marks, onMark }) {
  const n = Object.entries(marks || {}).filter(([k, v]) => v === "revert" && k.startsWith(`${file.path}#`)).length;
  return (
    <div className="tq-dv-file" data-tq-diff-file={file.path}>
      <button type="button" className="tq-dv-file-row" aria-expanded={open ? "true" : "false"} onClick={onToggle}>
        <span className="tq-dv-chev" aria-hidden>{open ? "▾" : "▸"}</span>
        <span className="tq-dv-path" title={file.path}>{file.path}</span>
        {!!n && <span className="tq-dv-marked">{n} to revert</span>}
        <span className="tq-dv-plus">+{file.plus}</span><span className="tq-dv-minus">−{file.minus}</span>
      </button>
      {open && (file.binary ? <div className="tq-dv-empty">A binary file - git says it changed; there is no text to show.</div>
        : !file.hunks.length ? <div className="tq-dv-empty">No lines changed (a rename or a mode change).</div>
        : file.hunks.map((h, i) => <Hunk key={i} h={h} path={file.path} mark={marks?.[`${file.path}#${h.index ?? i}`]}
            onMark={onMark ? (m) => onMark(`${file.path}#${h.index ?? i}`, m) : null} />))}
    </div>
  );
}

export default function DiffView({ files, marks, onMark }) {
  const [open, setOpen] = useState(() => new Set(files.length === 1 ? [files[0].path] : []));
  const flip = (p) => setOpen((s) => { const n = new Set(s); if (n.has(p)) n.delete(p); else n.add(p); return n; });
  if (!files.length) return <div className="tq-dv-empty">No diff to show.</div>;
  return (
    <div className="tq-dv" data-tq-diff-view="">
      {files.length > 1 && <div className="tq-dv-all">
        <button type="button" onClick={() => setOpen(new Set(files.map((f) => f.path)))}>Open all</button>
        <button type="button" onClick={() => setOpen(new Set())}>Fold all</button></div>}
      {files.map((f) => <FileDiff key={f.path} file={f} open={open.has(f.path)} onToggle={() => flip(f.path)} marks={marks} onMark={onMark} />)}
    </div>
  );
}
