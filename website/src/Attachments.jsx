// What rode along with the message. Half the time the screenshot IS the ask ("see below"),
// so images are drawn right here in the panel rather than listed as filenames - and the
// spreadsheet, the PDF, the invoice are one click from where you are reading about them.
import React, { useEffect, useState } from "react";
import { Box, Button, CircularProgress, Dialog, Typography } from "@mui/material";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import DownloadIcon from "@mui/icons-material/Download";
import GraphicEqIcon from "@mui/icons-material/GraphicEq";
import api from "./api";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, mono } from "./theme.jsx";

// An <img src> carries no headers, so the token rides in the query string (see token_gate).
export const attUrl = (a, download) => {
  if (String(a.url || "").startsWith("data:")) return a.url;   // the static demo carries its own bytes
  const t = localStorage.getItem("taskuary_token");
  const q = [download ? "download=true" : "", t ? `token=${encodeURIComponent(t)}` : ""].filter(Boolean).join("&");
  return `${a.url}${q ? `?${q}` : ""}`;
};

const LOGO = 24 * 1024;
// A cid-referenced image smaller than a logo IS a signature, not the ask, so it gets a chip like
// any other file. SVG is exempt: nobody signs their mail in one, and Taskuary's own report charts
// are small by nature.
const chrome = (a) => a.inline && a.size && a.size < LOGO && a.content_type !== "image/svg+xml";
const drawable = (a) => a.is_image && a.url && !chrome(a);
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
  : Object.entries(KIND).find(([k]) => (a.content_type + " " + a.name).toLowerCase().includes(k))?.[1]
  || (a.name.split(".").pop() || "file").slice(0, 5).toUpperCase();
// where a chip opens: a file's own bytes here (with the token), a linked document at its own address (never with it) - and a file
// kept without its bytes (a cloud link Outlook attaches, one over the size limit) at the original message, where it still opens
// (TQ-1197: "can't click the link to open" - the chip was a greyed div pointing at an original nothing linked to)
const SAVE_MAX = 12 * 1024 * 1024;   // channels.ATT_BYTES
const hrefOf = (a, original) => a.link ? a.external_url : a.url ? attUrl(a, true) : original || undefined;
const unsaved = (a) => (a.size > SAVE_MAX ? `over ${kb(SAVE_MAX)}, so not saved here` : "no copy came with the mail - a cloud file's link, or a forwarded mail");
const titleOf = (a, original) => a.link ? `${a.kind} — ${a.note ? `not read: ${a.note}` : a.read ? (a.rows != null ? `read, ${a.rows} rows` : "read") : "opens where it lives"}`
  : a.url ? "open it" : `${unsaved(a)} — ${original ? "opens in the original message" : "open it from the mail in your mailbox"}`;

// a mail whose body points at a picture it does not carry ([image: ...], cid:) - worth a "look for attachments" offer
export const mentionsPicture = (body) => /\[(image|cid|inline image)|cid:/i.test(String(body || ""));

export const Attachments = ({ messageId, canFetch, dense, original }) => {
  const [items, setItems] = useState(null);
  const [big, setBig] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const load = () => api.get(`/api/messages/${messageId}/attachments`)
    .then(({ data }) => setItems(data.data || [])).catch(() => setItems([]));
  useEffect(() => { setItems(null); setBig(null); setErr(""); load(); }, [messageId]);
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
  if (!items.length) return canFetch ? (
    <Typography variant="caption" component="button" type="button" disabled={busy} onClick={fetchNow}
      // slate, 11.5px and a real target: the sage at 10.5px read 3.8:1 on the card and its hit box was 17px tall (the 2026-10-07
      // design pass)
      sx={{ appearance: "none", border: 0, bgcolor: "transparent", px: 0, py: 0.6,
        color: err ? FAINT : "#41525f", cursor: busy ? "default" : "pointer", display: "inline-flex",
        alignItems: "center", gap: 0.4, mt: 0.2, fontSize: 11.5, textDecoration: "underline", textDecorationColor: "#c7d2dc",
        textUnderlineOffset: "3px", "&:hover": { color: err ? FAINT : "#2f3d48", textDecorationColor: "currentColor" } }}>
      {busy ? <CircularProgress size={10} /> : <AttachFileIcon sx={{ fontSize: 12 }} />}
      {err || "look for attachments on this mail"}
    </Typography>
  ) : null;
  const imgs = items.filter(drawable);
  const clips = items.filter((a) => !drawable(a) && playable(a));
  const files = items.filter((a) => !drawable(a) && !playable(a));
  return (
    <Box sx={{ mt: 1 }}>
      {/* images are PART of the message ("see below" mail IS the screenshot, a report's chart
          IS the result) - drawn inline at reading size, not parked behind an attachment chip.
          Only non-image files get the Attached row. */}
      {imgs.length > 0 && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
          {imgs.map((a) => (
            <Box key={a.id} component="button" type="button" onClick={() => setBig(a)}
              title={`${a.name} · ${kb(a.size)} — click to enlarge`}
              sx={{ appearance: "none", p: 0, border: `1px solid ${BORDER}`, borderRadius: 1.5, overflow: "hidden", cursor: "zoom-in",
                bgcolor: "#fff", alignSelf: "flex-start", maxWidth: "100%",
                "&:hover": { borderColor: "#d8cfbe" } }}>
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
                <GraphicEqIcon sx={{ fontSize: 13, color: "#6f8a6e" }} />
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
        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mt: 0.5 }}>
          {files.map((a) => (
            <Box key={a.id} component={hrefOf(a, original) ? "a" : "div"} href={hrefOf(a, original)} data-tq-linked-doc={a.link ? "" : undefined}
              data-tq-unsaved={!a.link && !a.url ? "" : undefined}
              target="_blank" rel={a.link || !a.url ? "noopener noreferrer" : "noopener"} title={titleOf(a, original)}
              sx={{ display: "flex", alignItems: "center", gap: 0.6, px: 0.9, py: 0.4, borderRadius: 1.5,
                border: `1px solid ${BORDER}`, bgcolor: PANEL2, textDecoration: "none", maxWidth: 260,
                cursor: hrefOf(a, original) ? "pointer" : "default", opacity: hrefOf(a, original) ? 1 : 0.6,
                "&:hover": { borderColor: hrefOf(a, original) ? "#d8cfbe" : BORDER } }}>
              <Typography variant="caption" sx={{ ...mono, fontSize: 9, fontWeight: 600, color: "#55697a" }}>{kindOf(a)}</Typography>
              <Typography variant="caption" sx={{ color: INK, flex: 1, minWidth: 0 }} noWrap>{a.name}</Typography>
              {/* ...and a file it could not keep says so on the chip, not only on hover */}
              <Typography variant="caption" sx={{ color: FAINT, fontSize: 9.5, whiteSpace: "nowrap" }}>
                {a.link ? (a.note ? "not read" : "") : a.url ? kb(a.size) : original ? "in the original" : "not saved"}</Typography>
            </Box>
          ))}
        </Box>
        </Box>
      )}
      {/* full size, on top of everything - a screenshot of a spreadsheet is unreadable inline */}
      <Dialog open={!!big} onClose={() => setBig(null)} maxWidth="xl"
        PaperProps={{ sx: { bgcolor: PANEL, p: 1 } }}>
        {big && (
          <>
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}>
              <Typography variant="caption" sx={{ color: INK, fontWeight: 600, flex: 1 }}>{big.name}</Typography>
              <Typography variant="caption" sx={{ color: FAINT }}>{kb(big.size)}</Typography>
              <Button size="small" startIcon={<DownloadIcon sx={{ fontSize: 15 }} />} href={attUrl(big, true)}>Save</Button>
            </Box>
            <Box component="img" src={attUrl(big)} alt={big.name}
              sx={{ display: "block", maxWidth: "88vw", maxHeight: "82vh", objectFit: "contain" }} />
          </>
        )}
      </Dialog>
    </Box>
  );
};
