// WHAT RIDES WITH THE REPLY.
//
// A draft read "Attached are the PTO accrual files for the 8/31 payroll" and the card showed
// nothing, because nothing in Taskuary could attach a file at all - approving it would have sent an
// external recipient a mail promising two workbooks and carrying none (the owner, 2026-09-14: "we
// need UI to show the attachment here... otherwise it looks like it sends without attachment").
//
// So the card says what is going: every file by name and size, one click to take one off, one to add
// one - and when its writer said the words promise an attachment that is not there (filesPromised), a line saying so. It never
// blocks the send; the owner can always mean "attached in my last mail".
import React, { useRef, useState } from "react";
import { label, hint } from "./buttons.js";
import { Box, Button, Chip, CircularProgress, Typography } from "@mui/material";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import api from "./api.js";
import { ALERT_INK, DIM } from "./theme.jsx";
import { sizeText } from "./replyFiles.js";
import { useVerbs } from "./actionRow.js";
import { FileDialog } from "./PublishedPages.jsx";
// a file on the reply as the viewer reads it: its preview by its kind, read back from the reply itself (server review_attachment_read)
const EXT_PREVIEW = { csv: "text", txt: "text", md: "text", json: "text", xlsx: "sheet", xls: "sheet", docx: "document", pdf: "pdf", png: "picture",
  jpg: "picture", jpeg: "picture", gif: "picture", webp: "picture" };
const asViewed = (rid, f) => { const e = String(f.name).split(".").pop().toLowerCase(), u = `/api/reviews/${rid}/attachment?name=${encodeURIComponent(f.name)}`;
  return { id: `reply:${rid}:${f.name}`, name: f.name, path: f.name, kind: "output", preview: EXT_PREVIEW[e] || null, url: u,
    content_type: e === "csv" ? "text/csv" : e === "pdf" ? "application/pdf" : "", size: f.size }; };

export default function ReplyFiles({ reviewId, files = [], promised = false, short = [], channel = "email", onChanged, toRow = false, disabled = false }) {
  const pick = useRef(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState(""), [viewing, setViewing] = useState(null);
  const mail = String(channel || "email").toLowerCase() === "email";

  const add = async (chosen) => {
    if (disabled) return;
    const list = [...(chosen || [])];
    if (!list.length) return;
    setErr(""); setBusy("adding");
    // ...each file on its own: one refused says which, by name, and the rest still go on (the owner, 2026-11-04: "can't attach more things")
    const no = [];
    try {
      for (const file of list) {
        try {
          await api.post(`/api/reviews/${reviewId}/attachment`, file,
            { params: { name: file.name }, headers: { "Content-Type": file.type || "application/octet-stream" } });
        } catch (e) { no.push(`Not attached: ${file.name} — ${e?.response?.data?.detail || "it could not be attached"}.`); }
      }
      if (no.length < list.length) onChanged?.();
      setErr(no.join(" "));
    } finally { setBusy(""); if (pick.current) pick.current.value = ""; }
  };
  const drop = async (name) => {
    if (disabled) return;
    setErr(""); setBusy(name);
    try {
      await api.delete(`/api/reviews/${reviewId}/attachment`, { params: { name } });
      onChanged?.();
    } catch (e) { setErr(e?.response?.data?.detail || "Could not remove that file"); }
    finally { setBusy(""); }
  };

  const missing = !files.length && promised;
  // in the row above the chat line the button is one of its More verbs: the same hidden file input opens
  useVerbs(`attach:${reviewId}`, [{ id: "attach", group: "more", tone: "s", label: label("attach", files.length ? "more" : null), disabled: disabled || busy === "adding",
    run: () => pick.current?.click(), title: hint("attach") }], toRow && mail);
  return (
    <Box sx={{ mb: 0.75 }}>
      <FileDialog file={viewing} onClose={() => setViewing(null)} />
      <Box sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 0.75 }}>
        {files.map((f) => (
          <Chip key={f.name} size="small" icon={<AttachFileIcon sx={{ fontSize: 14 }} />}
            label={`${f.name} · ${sizeText(f.size)}`} disabled={disabled || busy === f.name}
            onDelete={() => drop(f.name)} onClick={() => setViewing(asViewed(reviewId, f))} title="Open it"
            data-tq-reply-file={f.name} sx={{ maxWidth: 320, cursor: "pointer" }} />
        ))}
        {mail && toRow ? null : mail ? (
          <Button size="small" onClick={() => pick.current?.click()} disabled={disabled || busy === "adding"}
            startIcon={busy === "adding" ? <CircularProgress size={11} /> : <AttachFileIcon sx={{ fontSize: 14 }} />}
            sx={{ color: DIM, textTransform: "none", fontSize: 11.5 }}>
            {busy === "adding" ? "Attaching…" : label("attach", files.length ? "more" : null)}
          </Button>
        ) : (promised || files.length) ? (
          // ...a draft that PROMISES one says so in the alert colour: sent here, the words would arrive without it (U17). A chat draft that
          // promises none says nothing - "a Teams message cannot carry a file" under every chat draft was a line, not a button (2026-10-22)
          <Typography variant="caption" sx={{ color: ALERT_INK }}>
            {`This reply mentions a file, and a ${channel} message cannot carry one — reply by email with the file instead.`}
          </Typography>
        ) : null}
        <input ref={pick} hidden type="file" multiple disabled={disabled} onChange={(e) => add(e.target.files)} />
      </Box>
      {missing && mail && (
        <Typography variant="caption" sx={{ display: "block", mt: 0.5, color: ALERT_INK }}>
          This draft mentions an attachment and nothing is attached — it will send with the words only.
        </Typography>
      )}
      {mail && short.map((line) => <Typography key={line} variant="caption" data-tq-not-attached sx={{ display: "block", mt: 0.5, color: ALERT_INK }}>{line}</Typography>)}
      {err && <Typography variant="caption" sx={{ display: "block", mt: 0.5, color: ALERT_INK }}>{err}</Typography>}
    </Box>
  );
}
