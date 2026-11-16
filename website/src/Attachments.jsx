// What rode along with the message. Half the time the screenshot IS the ask ("see below"),
// so images are drawn right here in the panel rather than listed as filenames - and the
// spreadsheet, the PDF, the invoice are one click from where you are reading about them.
import React, { useEffect, useState } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import DownloadIcon from "@mui/icons-material/Download";
import GraphicEqIcon from "@mui/icons-material/GraphicEq";
import api from "./api";
import { attUrl, useSave } from "./fileSave.js";
import { bareLine } from "./mailLinks.js";
import { FileDialog, FileView } from "./PublishedPages.jsx";
import { AttachChip, AttachRow } from "./promptImages.jsx";
import { PANEL2, BORDER, DIM, FAINT, INK, mono } from "./theme.jsx";

const LOGO = 48 * 1024;   // a company logo in a signature runs 20-40 KB (24 KB let a 24.4 KB one draw as a picture)
// A cid-referenced image smaller than a logo IS a signature, not the ask, so it gets a chip like
// any other file. SVG is exempt: nobody signs their mail in one, and Taskuary's own report charts
// are small by nature.
// ...and only in MAIL (`mail`, server _att_row): a WhatsApp or Telegram photo is marked inline too, and IS the message - its 14 KB
// JPEG stood as a chip to click in the open message (the owner, 2026-10-29: "its images show inline")
export const chrome = (a) => a.mail !== false && !!a.inline && !!a.size && a.size < LOGO && a.content_type !== "image/svg+xml";
// drawn from our own bytes only - the attachment route (images inline, SVG never as a page) or the demo's data: image, never a remote address
const ownImage = (u) => /^\/api\//.test(String(u || "")) || /^data:image\//.test(String(u || ""));
export const drawable = (a) => !!a.is_image && ownImage(a.url) && !chrome(a);
// A voice note is the message, not a file about it: WhatsApp and Teams send audio where other
// people send a sentence, so it gets a player here rather than a download chip that opens some
// other app. content_type is the truth; the extension is the fallback for a bridge that sent none.
const AUDIO_EXT = /\.(ogg|opus|mp3|m4a|aac|wav|webm|flac|amr)$/i;
const playable = (a) => !!a.url && (a.is_audio || AUDIO_EXT.test(a.name || ""));
// ...and it is CALLED a voice note: the bridge names the file after the message's id ("3EB0C4...ogg"), which says nothing. A
// file someone named keeps its name; the stored name stays on hover and on the save.
const HASHED = /^[0-9a-f]{12,}\.[a-z0-9]{2,5}$/i;
export const clipName = (a) => (HASHED.test(a?.name || "") || !a?.name ? "Voice note" : a.name);
const kb = (n) => (!n ? "" : n < 1024 ? `${n} B` : n < 1048576 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`);
const KIND = { pdf: "PDF", sheet: "XLSX", excel: "XLSX", csv: "CSV", zip: "ZIP", word: "DOCX", document: "DOCX" };
// a LINKED document (linkdocs.py) says what it is by its kind - "Google Sheet" is SHEET, "GitHub issue" ISSUE
const LINK_KIND = [["sheet", "SHEET"], ["spreadsheet", "SHEET"], ["slides", "SLIDES"], ["presentation", "SLIDES"], ["pdf", "PDF"],
  ["issue", "ISSUE"], ["pull request", "PR"], ["folder", "FOLDER"], ["page", "PAGE"], ["doc", "DOC"]];
const kindOf = (a) => a.link ? (LINK_KIND.find(([k]) => String(a.kind || "").toLowerCase().includes(k))?.[1] || "LINK")
  // ...its name first: a .csv sent as application/vnd.ms-excel is a CSV, not an XLSX
  : [a.name, a.content_type].map((s) => Object.entries(KIND).find(([k]) => String(s || "").toLowerCase().includes(k))?.[1]).find(Boolean)
  || (a.name.split(".").pop() || "file").slice(0, 5).toUpperCase();
// where a chip opens: a file's own bytes here (with the token), a linked document at its own address (never with it) - and a file
// kept without its bytes (a cloud link Outlook attaches, one over the size limit) at the original message, where it still opens
// (TQ-1197: "can't click the link to open" - the chip was a greyed div pointing at an original nothing linked to)
const SAVE_MAX = 12 * 1024 * 1024;   // channels.ATT_BYTES
const hrefOf = (a, original) => a.link ? a.external_url : a.url ? attUrl(a, true) : original || undefined;
const unsaved = (a) => (a.size > SAVE_MAX ? `over ${kb(SAVE_MAX)}, so not saved here` : "no copy came with the mail - a cloud file's link, or a forwarded mail");
const titleOf = (a, original) => a.link ? `${a.kind} — ${a.note ? `not read: ${a.note}` : a.read ? (a.rows != null ? `read, ${a.rows} rows` : "read") : "opens where it lives"}`
  : a.url ? (a.preview ? "read it here" : "save a copy") : `${unsaved(a)} — ${original ? "opens in the original message" : "open it from the mail in your mailbox"}`;

// a mail whose body points at a picture it does not carry ([image: ...], cid:) - worth a "look for attachments" offer
export const mentionsPicture = (body) => /\[(image|cid|inline image)|cid:/i.test(String(body || ""));

// `asFiles`: the images the page already draws itself (a report's chart, drawn live from its rows - ReportRows) are chips, not pictures
// `bare`: { remote } when the message has no words of its own (mailLinks.bareLine) - a picture-only mail. Its pictures are the message, so
// a small inline one is drawn, not chipped as a signature's logo; and the panel says what it is, never a blank
export const Attachments = ({ messageId, canFetch, dense, original, asFiles = null, bare = null }) => {
  const [items, setItems] = useState(null);
  const [big, setBig] = useState(null), [open, setOpen] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [saveErr, save, saved] = useSave();
  const load = () => api.get(`/api/messages/${messageId}/attachments`)
    .then(({ data }) => setItems(data.data || [])).catch(() => setItems([]));
  useEffect(() => { setItems(null); setBig(null); setOpen(null); setErr(""); load(); }, [messageId]);
  // mail that arrived before Taskuary kept attachments - and the retry after a Graph hiccup
  const fetchNow = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/api/messages/${messageId}/attachments/fetch`, {});
      setItems(data.data || []);
      if (!data.fetched && !(data.data || []).length) setErr("nothing was attached to this one");
    } catch (e) { setErr(e?.response?.data?.detail || "could not fetch them"); }
    setBusy(false);
  };
  if (items === null) return null;
  const say = (line) => line ? <Typography variant="body2" data-tq-bare="" sx={{ color: DIM, lineHeight: 1.55 }}>{line}</Typography> : null;
  if (!items.length) return <>{bare && say(bareLine({ remote: bare.remote }))}{canFetch ? (
    <Typography variant="caption" component="button" type="button" disabled={busy} onClick={fetchNow}
      // slate, 11.5px and a real target: the sage at 10.5px read 3.8:1 on the card and its hit box was 17px tall (the 2026-10-07
      // design pass)
      sx={{ appearance: "none", border: 0, bgcolor: "transparent", px: 0, py: 0.6,
        color: err ? FAINT : "var(--tq-link, #41525f)", cursor: busy ? "default" : "pointer", display: "inline-flex",
        alignItems: "center", gap: 0.4, mt: 0.2, fontSize: 11.5, textDecoration: "underline", textDecorationColor: "#c7d2dc",
        textUnderlineOffset: "3px", "&:hover": { color: err ? FAINT : "var(--tq-link, #2f3d48)", textDecorationColor: "currentColor" } }}>
      {busy ? <CircularProgress size={10} /> : <AttachFileIcon sx={{ fontSize: 12 }} />}
      {err || "look for attachments on this mail"}
    </Typography>
  ) : null}</>;
  const drawn = (a) => (bare ? !!a.is_image && ownImage(a.url) : drawable(a)) && !asFiles?.(a);
  const imgs = items.filter(drawn);
  const clips = items.filter((a) => !drawn(a) && playable(a));
  const files = items.filter((a) => !drawn(a) && !playable(a));
  return (
    <Box sx={{ mt: 1 }}>
      {bare && say(bareLine({ drawn: imgs.length, files: clips.length + files.length, remote: bare.remote }))}
      {/* images are PART of the message ("see below" mail IS the screenshot, a report's chart
          IS the result) - drawn inline at reading size, not parked behind an attachment chip.
          Only non-image files get the Attached row. */}
      {imgs.length > 0 && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
          {imgs.map((a) => (
            <Box key={a.id} component="button" type="button" onClick={() => setBig(a)}
              title={`${a.name} · ${kb(a.size)} — click to enlarge`}
              sx={{ appearance: "none", p: 0, border: `1px solid ${BORDER}`, borderRadius: 1.5, overflow: "hidden", cursor: "zoom-in",
                bgcolor: "var(--tq-panel, #fff)", alignSelf: "flex-start", maxWidth: "100%",
                "&:hover": { borderColor: "var(--tq-border, #d8cfbe)" } }}>
              <Box component="img" src={attUrl(a)} alt={a.name}
                sx={{ display: "block", maxHeight: dense ? 150 : 420, maxWidth: "100%", objectFit: "contain" }} />
            </Box>
          ))}
        </Box>
      )}
      {/* play it where you are reading it - the browser decodes ogg/opus, which is what the
          WhatsApp and Teams bridges send. Transcription is a separate action on the message. */}
      {clips.length > 0 && (
        <Box sx={{ mt: imgs.length ? 0.75 : 0, display: "flex", flexDirection: "column", gap: 0.6 }}>
          {clips.map((a) => (
            <Box key={a.id} sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: PANEL2,
              px: 0.9, py: 0.7, maxWidth: 420 }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mb: 0.4 }}>
                <GraphicEqIcon sx={{ fontSize: 13, color: "var(--tq-success, #6f8a6e)" }} />
                <Typography variant="caption" sx={{ color: INK, flex: 1, minWidth: 0 }} noWrap title={a.name}>{clipName(a)}</Typography>
                <Typography variant="caption" sx={{ color: FAINT, fontSize: 9.5 }}>{kb(a.size)}</Typography>
                <Box component="a" href={attUrl(a, true)} title="save the audio"
                  sx={{ display: "inline-flex", color: FAINT, "&:hover": { color: INK } }}>
                  <DownloadIcon sx={{ fontSize: 14 }} />
                </Box>
              </Box>
              {/* preload="none": a day of chat rows must not pull every clip off disk on render */}
              <Box component="audio" controls preload="none" src={attUrl(a)}
                sx={{ display: "block", width: "100%", height: 32 }} />
            </Box>
          ))}
        </Box>
      )}
      {files.length > 0 && (
        <Box sx={{ mt: imgs.length || clips.length ? 0.75 : 0, pt: 0.75, borderTop: `1px dashed ${BORDER}` }}>
          <Typography variant="caption" sx={{ color: DIM, fontWeight: 600, display: "flex", alignItems: "center", gap: 0.3 }}>
            <AttachFileIcon sx={{ fontSize: 12 }} /> Attached · {files.length}
          </Typography>
        {/* ...the one attachment chip, in the one row: a few, then "+N more" with the whole list (promptImages AttachRow, the owner 2026-11-06) */}
        <AttachRow sx={{ mt: 0.5 }}>
          {files.map((a) => (
            <AttachChip key={a.id} component={hrefOf(a, original) ? "a" : "div"} href={hrefOf(a, original)} data-tq-linked-doc={a.link ? "" : undefined} data-tq-att={a.name}
              data-tq-unsaved={!a.link && !a.url ? "" : undefined} name={a.name}
              target="_blank" rel={a.link || !a.url ? "noopener noreferrer" : "noopener"} title={titleOf(a, original)}
              aria-expanded={!a.link && a.url && a.preview ? open?.id === a.id : undefined}
              /* ...READ IN PLACE, every kind the server can preview (outputs.preview_of): the viewer an agent's file opens in, Download beside it */
              onClick={!a.link && a.url ? (e) => { e.preventDefault(); a.preview ? setOpen(open?.id === a.id ? null : a) : save(a); } : undefined}
              icon={<Typography component="span" variant="caption" sx={{ ...mono, fontSize: 9, fontWeight: 600, color: "var(--tq-link, #55697a)", flexShrink: 0 }}>{kindOf(a)}</Typography>}
              /* ...and a file it could not keep says so on the chip, not only on hover */
              note={a.link ? (a.note ? "not read" : "") : a.url ? kb(a.size) : original ? "in the original" : "not saved"}
              sx={{ opacity: hrefOf(a, original) ? 1 : 0.6, cursor: hrefOf(a, original) ? "pointer" : "default" }} />
          ))}
        </AttachRow>
        {saveErr && <Typography variant="caption" data-tq-file-error="" sx={{ display: "block", mt: 0.5, color: DIM }}>{saveErr}</Typography>}
        {saved && <Typography variant="caption" data-tq-file-saved="" sx={{ display: "block", mt: 0.5, color: DIM }}>{saved}</Typography>}
        {open && files.some((a) => a.id === open.id) && <FileView key={open.id} file={open} onClose={() => setOpen(null)} />}
        </Box>
      )}
      {/* full size, on top of everything - a screenshot of a spreadsheet is unreadable inline - in the one file dialog (FileDialog) */}
      <FileDialog file={big} onClose={() => setBig(null)} />
    </Box>
  );
};
