// A POST, DRAWN AS THE POST IT WILL BE (the owner, 2026-11-05: "it's not showing the post and the image as a linkedin post and asking me if i want
// to post it in popup. I have linkedin connected"). The agent's run_tool on a posting connector (proposals.POSTS): who it posts as, the words -
// editable while it waits - and the picture inline, with "Post to LinkedIn" as its Approve. The press is the one decide road every proposal
// takes (/api/reviews/{id}/decide, verdicts.decide -> proposals.execute): nothing posts before it. Once posted it says so, with the link.
import React, { useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import api from "./api.js";
import { attUrl } from "./Attachments.jsx";
import { FileDialog } from "./PublishedPages.jsx";
import { postState } from "./reviewProposal.js";
import { outputRow } from "./taskOutputs.js";
import { hint, label } from "./buttons.js";
import { ACCENT, ALERT_INK, BORDER, DIM, FAINT, INK } from "./theme.jsx";

const initials = (s) => String(s || "").split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0].toUpperCase()).join("") || "in";

export default function PostCard({ row, tid, live = true, onChanged }) {
  const p = row?.post || {}, st = postState(row, live), [text, setText] = useState(String(p.text || ""));
  const [busy, setBusy] = useState(""), [err, setErr] = useState(""), [viewing, setViewing] = useState(null), [done, setDone] = useState(null);
  const pic = p.image ? outputRow(tid ?? row?.TaskId, p.image) : null;
  const go = done?.url ?? st.url, posted = !!done || st.posted;
  const decide = async (verb) => {
    setBusy(verb); setErr("");
    try {
      const { data } = await api.post(`/api/reviews/${row.ReviewId}/decide`, { verb, final_text: verb === "approve" ? text : null, note: null }, { timeout: 120000 });
      if (!data?.ok) { setErr(data?.send_error || "It didn't go through - nothing was posted. Try again."); return; }
      if (verb === "approve") setDone({ url: data.result?.url || "" });
      onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "It didn't go through - nothing was posted. Try again."); }
    finally { setBusy(""); }
  };
  return (
    <Box data-tq-post={row?.ReviewId} data-tq-post-state={posted ? "posted" : st.live ? "waiting" : "not-posted"}
      sx={{ mt: 1, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: "#fff", overflow: "hidden" }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.5, pt: 1.25, pb: 0.75 }}>
        <Box aria-hidden sx={{ width: 34, height: 34, borderRadius: "50%", bgcolor: "#dfe6ec", color: ACCENT, display: "grid", placeItems: "center", fontWeight: 700, fontSize: 13 }}>
          {initials(row?.as)}</Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography sx={{ fontSize: 13.5, fontWeight: 700, color: INK, lineHeight: 1.2 }}>{row?.as || `Your ${row?.network || ""} account`}</Typography>
          <Typography sx={{ fontSize: 11.5, color: FAINT }}>{[row?.network, String(p.visibility || "PUBLIC").toUpperCase() === "CONNECTIONS" ? "Connections" : "Anyone"].filter(Boolean).join(" · ")}</Typography>
        </Box>
      </Box>
      {st.live && !posted
        ? <Box component="textarea" data-tq-post-text="" value={text} onChange={(e) => setText(e.target.value)} disabled={!!busy} rows={Math.min(14, Math.max(3, text.split("\n").length + 1))}
            sx={{ display: "block", width: "100%", boxSizing: "border-box", resize: "vertical", border: 0, outline: 0, px: 1.5, py: 0.5, font: "inherit", fontSize: 13.5, lineHeight: 1.5, color: INK, bgcolor: "transparent" }} />
        : <Typography data-tq-post-text="" sx={{ px: 1.5, py: 0.5, fontSize: 13.5, lineHeight: 1.5, color: posted ? INK : DIM, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{p.text}</Typography>}
      {pic && <Box component="img" data-tq-post-image={p.image} src={attUrl(pic)} alt={p.alt || pic.name} onClick={() => setViewing(pic)}
        sx={{ display: "block", width: "100%", maxHeight: 320, objectFit: "contain", bgcolor: "#f6f4f1", mt: 0.75, cursor: "zoom-in", borderTop: `1px solid ${BORDER}`, borderBottom: `1px solid ${BORDER}` }} />}
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.5, py: 1, flexWrap: "wrap" }}>
        {posted ? <Typography data-tq-posted="" sx={{ fontSize: 13, color: "#47654a", fontWeight: 600 }}>✓ Posted
          {go && <> · <a href={go} target="_blank" rel="noopener noreferrer" style={{ color: ACCENT }}>See it on {row?.network}<OpenInNewIcon sx={{ fontSize: 12, ml: 0.25, verticalAlign: "-1px" }} /></a></>}</Typography>
          : st.live ? <>
            <Button size="small" variant="contained" disableElevation data-tq-post-press="" disabled={!!busy || !text.trim()} onClick={() => decide("approve")}
              title={hint("approve", "post")} startIcon={busy === "approve" ? <CircularProgress size={12} color="inherit" /> : null}>
              {busy === "approve" ? "Posting…" : label("approve", "post").replace("{network}", row?.network || "")}</Button>
            <Button size="small" disabled={!!busy} onClick={() => decide("reject")} data-tq-post-dismiss="">Dismiss</Button>
            <Typography sx={{ fontSize: 11.5, color: FAINT }}>Nothing is posted until you press it.</Typography></>
          : <Typography sx={{ fontSize: 12.5, color: FAINT }}>{st.said}</Typography>}
      </Box>
      {err && <Typography role="alert" sx={{ px: 1.5, pb: 1, fontSize: 12.5, color: ALERT_INK }}>{err}</Typography>}
      <FileDialog file={viewing} onClose={() => setViewing(null)} />
    </Box>
  );
}
