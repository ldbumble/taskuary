// What rode along with the message. Half the time the screenshot IS the ask ("see below"),
// so images are drawn right here in the panel rather than listed as filenames - and the
// spreadsheet, the PDF, the invoice are one click from where you are reading about them.
import React, { useEffect, useState } from "react";
import { Box, Button, CircularProgress, Dialog, Typography } from "@mui/material";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import DownloadIcon from "@mui/icons-material/Download";
import api from "./api";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, ACCENT2, mono } from "./theme.jsx";

// An <img src> carries no headers, so the token rides in the query string (see token_gate).
export const attUrl = (a, download) => {
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
const kb = (n) => (!n ? "" : n < 1024 ? `${n} B` : n < 1048576 ? `${Math.round(n / 1024)} KB` : `${(n / 1048576).toFixed(1)} MB`);
const KIND = { pdf: "PDF", sheet: "XLSX", excel: "XLSX", csv: "CSV", zip: "ZIP", word: "DOCX", document: "DOCX" };
const kindOf = (a) => Object.entries(KIND).find(([k]) => (a.content_type + " " + a.name).toLowerCase().includes(k))?.[1]
  || (a.name.split(".").pop() || "file").slice(0, 5).toUpperCase();

export const Attachments = ({ messageId, canFetch, dense }) => {
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
    <Typography variant="caption" onClick={busy ? undefined : fetchNow}
      sx={{ color: err ? FAINT : ACCENT2, cursor: busy ? "default" : "pointer", display: "inline-flex",
        alignItems: "center", gap: 0.3, mt: 0.5, fontSize: 10.5, "&:hover": { color: err ? FAINT : "#55697a" } }}>
      {busy ? <CircularProgress size={10} /> : <AttachFileIcon sx={{ fontSize: 12 }} />}
      {err || "look for attachments on this mail"}
    </Typography>
  ) : null;
  const imgs = items.filter(drawable);
  const files = items.filter((a) => !drawable(a));
  return (
    <Box sx={{ mt: 1 }}>
      {/* images are PART of the message ("see below" mail IS the screenshot, a report's chart
          IS the result) - drawn inline at reading size, not parked behind an attachment chip.
          Only non-image files get the Attached row. */}
      {imgs.length > 0 && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 0.75 }}>
          {imgs.map((a) => (
            <Box key={a.id} onClick={() => setBig(a)} title={`${a.name} · ${kb(a.size)} — click to enlarge`}
              sx={{ border: `1px solid ${BORDER}`, borderRadius: 1.5, overflow: "hidden", cursor: "zoom-in",
                bgcolor: "#fff", alignSelf: "flex-start", maxWidth: "100%",
                "&:hover": { borderColor: "#d8cfbe" } }}>
              <Box component="img" src={attUrl(a)} alt={a.name}
                sx={{ display: "block", maxHeight: dense ? 150 : 420, maxWidth: "100%", objectFit: "contain" }} />
            </Box>
          ))}
        </Box>
      )}
      {files.length > 0 && (
        <Box sx={{ mt: imgs.length ? 0.75 : 0, pt: 0.75, borderTop: `1px dashed ${BORDER}` }}>
          <Typography variant="caption" sx={{ color: DIM, fontWeight: 700, display: "flex", alignItems: "center", gap: 0.3 }}>
            <AttachFileIcon sx={{ fontSize: 12 }} /> Attached · {files.length}
          </Typography>
        <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mt: 0.5 }}>
          {files.map((a) => (
            <Box key={a.id} component={a.url ? "a" : "div"} href={a.url ? attUrl(a, true) : undefined}
              target="_blank" rel="noopener" title={a.url ? "open it" : "not saved here — open the original message"}
              sx={{ display: "flex", alignItems: "center", gap: 0.6, px: 0.9, py: 0.4, borderRadius: 1.5,
                border: `1px solid ${BORDER}`, bgcolor: PANEL2, textDecoration: "none", maxWidth: 260,
                cursor: a.url ? "pointer" : "default", opacity: a.url ? 1 : 0.6,
                "&:hover": { borderColor: a.url ? "#d8cfbe" : BORDER } }}>
              <Typography variant="caption" sx={{ ...mono, fontSize: 9, fontWeight: 700, color: "#55697a" }}>{kindOf(a)}</Typography>
              <Typography variant="caption" sx={{ color: INK, flex: 1, minWidth: 0 }} noWrap>{a.name}</Typography>
              <Typography variant="caption" sx={{ color: FAINT, fontSize: 9.5 }}>{kb(a.size)}</Typography>
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
              <Typography variant="caption" sx={{ color: INK, fontWeight: 700, flex: 1 }}>{big.name}</Typography>
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
