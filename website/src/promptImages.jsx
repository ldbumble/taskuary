// PICTURES WITH A PROMPT (the owner, 2026-09-30: "can't attach images ... to write this prompt?"). One picker for every box that
// writes to an agent - the New box, the chat line, Continue: paste, drop, or the paperclip. Each image is saved by the server
// (/api/prompt-image, the waitroom's bytes-as-body contract) and the prompt carries its PATH - a CLI agent reads a picture from a
// file, and the assistant's own model is handed the picture itself (server.prompt_images).
// ...AND ANY FILE, where the box asks for them (`files`; the owner, 2026-11-05: "does drop in the prompt box attach it in all prompt boxes?"):
// a PDF, a sheet, a log goes to /api/prompt-file under its own name, the same 12 MB cap, and is drawn as a chip with that name
import React, { useCallback, useRef, useState } from "react";
import { Box, IconButton, Tooltip } from "@mui/material";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import CloseIcon from "@mui/icons-material/Close";
import api from "./api";

export const IMAGE_TYPES = /^image\/(png|jpeg|gif|webp)$/;
export const MAX_IMAGES = 8;
const IMAGE_ACCEPT = "image/png,image/jpeg,image/gif,image/webp";
export const isImagePath = (p) => /\.(png|jpe?g|gif|webp)$/i.test(String(p || ""));

// one file to the server: a picture through the image road (its type check), anything else through the file road; { path, name, image }
export async function savePromptFile(f) {
  const image = IMAGE_TYPES.test(f.type);
  const { data } = image ? await api.post("/api/prompt-image", f, { headers: { "Content-Type": f.type } })
    : await api.post("/api/prompt-file", f, { headers: { "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(f.name || "file") } });
  return { path: data.path, name: f.name || (image ? "pasted image" : "file"), image };
}

export function usePromptImages({ files: anyFile = false } = {}) {
  const [imgs, setImgs] = useState([]);                 // [{ path, url, name, image }]
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const takes = useCallback((f) => anyFile || IMAGE_TYPES.test(f.type), [anyFile]);
  const add = useCallback(async (files) => {
    const list = [...(files || [])].filter(takes);
    if (!list.length) return false;
    setBusy(true); setErr("");
    try {
      for (const f of list.slice(0, MAX_IMAGES)) {
        const got = await savePromptFile(f);
        setImgs((cur) => (cur.length >= MAX_IMAGES ? cur : [...cur, { ...got, url: got.image ? URL.createObjectURL(f) : "" }]));
      }
    } catch (e) { setErr(e?.response?.data?.detail || (anyFile ? "the file did not upload" : "the image did not upload")); }
    finally { setBusy(false); }
    return true;
  }, [takes, anyFile]);
  const remove = useCallback((path) => setImgs((cur) => cur.filter((i) => i.path !== path)), []);
  const clear = useCallback(() => setImgs([]), []);
  // a paste that carries an image (or, with `files`, any file) is that, not text; anything else pastes as it always did
  const onPaste = useCallback((e) => {
    const files = [...(e.clipboardData?.files || [])].filter(takes);
    if (files.length) { e.preventDefault(); add(files); }
  }, [add, takes]);
  const onDrop = useCallback((e) => {
    const files = [...(e.dataTransfer?.files || [])].filter(takes);
    if (files.length) { e.preventDefault(); add(files); }
  }, [add, takes]);
  const onDragOver = useCallback((e) => { if ([...(e.dataTransfer?.types || [])].includes("Files")) e.preventDefault(); }, []);
  return { imgs, paths: imgs.map((i) => i.path), busy, err, add, remove, clear, files: anyFile, drop: { onPaste, onDrop, onDragOver } };
}

// the paperclip: opens the file picker - images only, or any file where the box takes them
export function AttachImage({ pics, size = 18, sx }) {
  const input = useRef(null), what = pics.files ? "a file" : "an image";
  return (
    <>
      <Tooltip title={pics.busy ? "Uploading…" : `Attach ${what} - or paste or drop one here`}>
        <span><IconButton size="small" aria-label={`Attach ${what}`} disabled={pics.busy} onClick={() => input.current?.click()}
          sx={{ width: 34, height: 34, p: 0, color: "#6e685f", ...sx }}><AttachFileIcon sx={{ fontSize: size }} /></IconButton></span>
      </Tooltip>
      <input ref={input} hidden type="file" accept={pics.files ? undefined : IMAGE_ACCEPT} multiple
        onChange={(e) => { pics.add(e.target.files); e.target.value = ""; }} />
    </>
  );
}

// the pictures waiting to go, as thumbnails with an x each - a file that is no picture a chip with its name.
// `cannot(i)`: what this box's road cannot do with that one, said on its chip instead of dropping it silently
export function ImageTray({ pics, sx, cannot = null }) {
  if (!pics.imgs.length && !pics.err && !pics.busy) return null;
  const x = (i, s) => <IconButton size="small" aria-label={`Remove ${i.name}`} onClick={() => pics.remove(i.path)} sx={s}><CloseIcon sx={{ fontSize: 12 }} /></IconButton>;
  return (
    <Box data-tq-image-tray sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 0.75, ...sx }}>
      {pics.imgs.map((i) => { const no = cannot?.(i) || ""; return i.image === false || !i.url ? (
        <Box key={i.path} data-tq-file-chip={i.name} data-tq-file-cannot={no || undefined} title={no ? `${i.name} - ${no}` : i.name}
          sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, maxWidth: "100%", minWidth: 0, height: 26, pl: 0.75, pr: 0.25, borderRadius: "13px",
            border: `1px solid ${no ? "#e2c9a8" : "#ddd6cb"}`, bgcolor: no ? "#fbf3e8" : "#f6f4f1", fontSize: 12, color: "#3d3a34" }}>
          <AttachFileIcon sx={{ fontSize: 13, color: "#6e685f", flexShrink: 0 }} />
          <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flexShrink: 0, maxWidth: 200 }}>{i.name}</Box>
          {no && <Box component="span" sx={{ color: "#8a5a1c", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0 }}>· {no}</Box>}
          {x(i, { width: 18, height: 18, p: 0, color: "#6e685f", flexShrink: 0 })}
        </Box>
      ) : (
        <Box key={i.path} title={no ? `${i.name} - ${no}` : i.name} data-tq-file-cannot={no || undefined} sx={{ position: "relative", width: 52, height: 52, borderRadius: "7px", overflow: "hidden",
          border: `1px solid ${no ? "#e2c9a8" : "#ddd6cb"}`, bgcolor: "#f6f4f1", flexShrink: 0 }}>
          <Box component="img" src={i.url} alt={i.name} sx={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
          {x(i, { position: "absolute", top: 1, right: 1, width: 17, height: 17, p: 0, bgcolor: "rgba(38,37,33,.7)", color: "#fff", "&:hover": { bgcolor: "rgba(38,37,33,.9)" } })}
        </Box>
      ); })}
      {pics.busy && <Box sx={{ fontSize: 11, color: "#a09889" }}>uploading…</Box>}
      {!!pics.err && <Box sx={{ fontSize: 11, color: "#7a2f3c" }}>{pics.err}</Box>}
    </Box>
  );
}

// the words, then the files: how a CLI agent is shown a picture or a file (server.with_images says it the same way)
export const withImages = (text, paths) => (paths?.length
  ? `${text || ""}\n\n${paths.every(isImagePath) ? "ATTACHED IMAGES" : "ATTACHED FILES"} (read these files)\n${paths.join("\n")}` : text || "");
