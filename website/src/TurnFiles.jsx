// THE FILES A TURN MADE, DRAWN IN IT (the owner, 2026-11-05: "the post and images are as artifacts separate not inline???"): a picture as the
// picture, a report, sheet or document as its preview - under the turn that made it (taskOutputs.turnFiles), its name and a press on the
// picture opening it over the chat (FileDialog), Download beside it.
// SEVERAL ARE ONE ARTIFACT (the owner, 2026-11-24: "it put in 9 files as cards? it should combine them" ... "like the bulk action card, same
// idea - one card showing all the items"): the count as its label (filesLabel), the bulk card's rows (Artifact Items) - each its name, kind and
// size, its Download - and ONE preview under them, of the row picked (the first until he picks another)
import React, { useState } from "react";
import { Box, Button } from "@mui/material";
import { attUrl, useSave } from "./fileSave.js";
import { CopyFile, FileDialog, isText, Preview } from "./PublishedPages.jsx";
import { fileGroups, fileKind, filesLabel, mediaFit, sizeWords } from "./taskOutputs.js";
import Artifact, { Items } from "./Artifact.jsx";
import { INK } from "./theme.jsx";

const isPic = (f) => /^image\//.test(f?.content_type || "") && !/svg/.test(f?.content_type || "");
const Download = ({ f, save, ...rest }) => <Button size="small" href={attUrl(f, true)} data-tq-download="" onClick={(e) => { e.preventDefault(); save(f); }} {...rest}>Download</Button>;

// ...what the file is, drawn: the picture itself or its preview - the one body a single file and a group's picked row both show. A group's
// row with no preview of its own (a deck, a workbook on an install with no openpyxl) shows what its "open" did before files were grouped -
// Preview's own line that there is none (walk 19: pressing the pptx and xlsx rows opened nothing)
const Body = ({ f, onView, picked }) => isPic(f)
  ? <div className="tq-published-picture" {...(mediaFit(f) ? { "data-tq-natural": "" } : {})}>
      <img src={attUrl(f)} alt={f.name} width={f.dims?.[0]} height={f.dims?.[1]} onClick={() => onView(f)}
        style={{ cursor: "zoom-in", objectFit: "contain", ...(mediaFit(f)?.media || { maxHeight: 320 }) }} /></div>
  : f.preview || picked ? <Preview key={f.path} page={f} /> : null;

// ONE CALL, ONE HAND-OVER (the card gallery, 2026-11-25: a chart and its workbook, each shown by its own call, stood as one "2 files"): what
// one `show` handed is one artifact, the next call's the next (taskOutputs.fileGroups)
export default function TurnFiles({ files }) { return fileGroups(files).map((g) => <Group key={g[0].path} files={g} />); }

function Group({ files }) {
  const [viewing, setViewing] = useState(null), [pick, setPick] = useState(null), [err, save, saved] = useSave();
  const one = files.length === 1, f = files.find((x) => x.path === pick) || files[0];
  const items = one ? [] : files.map((x) => ({ id: x.path, target: x.name, line: [fileKind(x), sizeWords(x.size)].filter(Boolean).join(" · "),
    picked: x === f, onPick: () => setPick(x.path), tail: <Download f={x} save={save} sx={{ minWidth: 0 }} /> }));
  return (
    <div className="tq-published" data-tq-turn-files="">
      {one
        ? <Artifact className="tq-published-page" data-tq-turn-file={f.path} style={mediaFit(f)?.box}>
            <div className="tq-published-row">
              <button type="button" className="tq-published-name" onClick={() => setViewing(f)} title="Open it here">
                <b>{f.name}</b><span>{isPic(f) ? "picture" : f.preview || "file"} · open</span></button>
              {isText(f) && <CopyFile f={f} />}
              <Download f={f} save={save} />
            </div>
            <Body f={f} onView={setViewing} />
          </Artifact>
        : <Artifact className="tq-published-page" data-tq-file-group={files.length} data-tq-turn-file={f.path}>
            <Box className="tq-published-list" sx={{ px: 1.25, pt: 1, pb: 0.75 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
                <Box data-tq-artifact-label="" sx={{ flex: 1, fontSize: 13.5, fontWeight: 700, color: INK }}>{filesLabel(files)}</Box>
                <Button size="small" data-tq-download-all="" onClick={() => files.forEach(save)}>Download all</Button>
              </Box>
              <Items items={items} />
            </Box>
            <Body f={f} onView={setViewing} picked />
          </Artifact>}
      {err && <div className="tq-published-note" data-tq-file-error="">{err}</div>}
      {saved && <div className="tq-published-note" data-tq-file-saved="">{saved}</div>}
      <FileDialog file={viewing} files={files} onClose={() => setViewing(null)} />
    </div>
  );
}
