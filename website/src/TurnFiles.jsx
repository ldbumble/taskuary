// THE FILES A TURN MADE, DRAWN IN IT (the owner, 2026-11-05: "the post and images are as artifacts separate not inline???"): a picture as the
// picture, a report, sheet or document as its preview - each under the turn that made it (taskOutputs.turnFiles), its name and a press on the
// picture opening it over the chat (FileDialog), Download beside it
import React, { useState } from "react";
import { Button } from "@mui/material";
import api from "./api.js";
import { attUrl, useSave } from "./Attachments.jsx";
import { label as btn } from "./buttons.js";
import { copyText } from "./CopyCorner.jsx";
import { FileDialog, Preview } from "./PublishedPages.jsx";

const isPic = (f) => /^image\//.test(f?.content_type || "") && !/svg/.test(f?.content_type || "");

// ...and one that reads as text - a query, a script, a letter - copies whole at a press, to paste where it is wanted
const CopyFile = ({ f }) => {
  const [done, setDone] = useState(false);
  const press = () => api.get(f.url, { responseType: "text", transformResponse: (x) => x }).then((r) => copyText(r.data))
    .then(() => { setDone(true); setTimeout(() => setDone(false), 1500); }, () => {});
  return <Button size="small" data-tq-copy-file="" onClick={press}>{btn("copy", done ? "done" : undefined)}</Button>;
};

export default function TurnFiles({ files }) {
  const [viewing, setViewing] = useState(null), [err, save, saved] = useSave();
  if (!files?.length) return null;
  return (
    <div className="tq-published" data-tq-turn-files="">
      {files.map((f) => (
        <div key={f.path} className="tq-published-page" data-tq-turn-file={f.path}>
          <div className="tq-published-row">
            <button type="button" className="tq-published-name" onClick={() => setViewing(f)} title="Open it here">
              <b>{f.name}</b><span>{isPic(f) ? "picture" : f.preview || "file"} · open</span></button>
            {f.preview === "text" && <CopyFile f={f} />}
            <Button size="small" href={attUrl(f, true)} data-tq-download="" onClick={(e) => { e.preventDefault(); save(f); }}>Download</Button>
          </div>
          {isPic(f)
            ? <div className="tq-published-picture"><img src={attUrl(f)} alt={f.name} style={{ cursor: "zoom-in", maxHeight: 320, objectFit: "contain" }} onClick={() => setViewing(f)} /></div>
            : f.preview ? <Preview page={f} /> : null}
        </div>))}
      {err && <div className="tq-published-note" data-tq-file-error="">{err}</div>}
      {saved && <div className="tq-published-note" data-tq-file-saved="">{saved}</div>}
      <FileDialog file={viewing} onClose={() => setViewing(null)} />
    </div>
  );
}
