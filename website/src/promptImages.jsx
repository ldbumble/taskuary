// PICTURES WITH A PROMPT (the owner, 2026-09-30: "can't attach images ... to write this prompt?"). One picker for every box that
// writes to an agent - the New box, the chat line, Continue: paste, drop, or the paperclip. Each image is saved by the server
// (/api/prompt-image, the waitroom's bytes-as-body contract) and the prompt carries its PATH - a CLI agent reads a picture from a
// file, and the assistant's own model is handed the picture itself (server.prompt_images).
import React, { useCallback, useRef, useState } from "react";
import { Box, IconButton, Tooltip } from "@mui/material";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import CloseIcon from "@mui/icons-material/Close";
import api from "./api";

export const IMAGE_TYPES = /^image\/(png|jpeg|gif|webp)$/;
export const MAX_IMAGES = 8;

export function usePromptImages() {
  const [imgs, setImgs] = useState([]);                 // [{ path, url, name }]
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const add = useCallback(async (files) => {
    const list = [...(files || [])].filter((f) => IMAGE_TYPES.test(f.type));
    if (!list.length) return false;
    setBusy(true); setErr("");
    try {
      for (const f of list.slice(0, MAX_IMAGES)) {
        const { data } = await api.post("/api/prompt-image", f, { headers: { "Content-Type": f.type } });
        setImgs((cur) => (cur.length >= MAX_IMAGES ? cur : [...cur, { path: data.path, url: URL.createObjectURL(f), name: f.name || "pasted image" }]));
      }
    } catch (e) { setErr(e?.response?.data?.detail || "the image did not upload"); }
    finally { setBusy(false); }
    return true;
  }, []);
  const remove = useCallback((path) => setImgs((cur) => cur.filter((i) => i.path !== path)), []);
  const clear = useCallback(() => setImgs([]), []);
  // a paste that carries an image is the image, not text; anything else pastes as it always did
  const onPaste = useCallback((e) => {
    const files = [...(e.clipboardData?.files || [])].filter((f) => IMAGE_TYPES.test(f.type));
    if (files.length) { e.preventDefault(); add(files); }
  }, [add]);
  const onDrop = useCallback((e) => {
    const files = [...(e.dataTransfer?.files || [])].filter((f) => IMAGE_TYPES.test(f.type));
    if (files.length) { e.preventDefault(); add(files); }
  }, [add]);
  const onDragOver = useCallback((e) => { if ([...(e.dataTransfer?.types || [])].includes("Files")) e.preventDefault(); }, []);
  return { imgs, paths: imgs.map((i) => i.path), busy, err, add, remove, clear, drop: { onPaste, onDrop, onDragOver } };
}

// the paperclip: opens the file picker, images only
export function AttachImage({ pics, size = 18, sx }) {
  const input = useRef(null);
  return (
    <>
      <Tooltip title={pics.busy ? "Uploading…" : "Attach an image - or paste or drop one here"}>
        <span><IconButton size="small" aria-label="Attach an image" disabled={pics.busy} onClick={() => input.current?.click()}
          sx={{ width: 34, height: 34, p: 0, color: "#6e685f", ...sx }}><AttachFileIcon sx={{ fontSize: size }} /></IconButton></span>
      </Tooltip>
      <input ref={input} hidden type="file" accept="image/png,image/jpeg,image/gif,image/webp" multiple
        onChange={(e) => { pics.add(e.target.files); e.target.value = ""; }} />
    </>
  );
}

// the pictures waiting to go, as thumbnails with an x each
export function ImageTray({ pics, sx }) {
  if (!pics.imgs.length && !pics.err && !pics.busy) return null;
  return (
    <Box data-tq-image-tray sx={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 0.75, ...sx }}>
      {pics.imgs.map((i) => (
        <Box key={i.path} title={i.name} sx={{ position: "relative", width: 52, height: 52, borderRadius: "7px", overflow: "hidden",
          border: "1px solid #ddd6cb", bgcolor: "#f6f4f1", flexShrink: 0 }}>
          <Box component="img" src={i.url} alt={i.name} sx={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }} />
          <IconButton size="small" aria-label={`Remove ${i.name}`} onClick={() => pics.remove(i.path)}
            sx={{ position: "absolute", top: 1, right: 1, width: 17, height: 17, p: 0, bgcolor: "rgba(38,37,33,.7)", color: "#fff",
              "&:hover": { bgcolor: "rgba(38,37,33,.9)" } }}><CloseIcon sx={{ fontSize: 12 }} /></IconButton>
        </Box>
      ))}
      {pics.busy && <Box sx={{ fontSize: 11, color: "#a09889" }}>uploading…</Box>}
      {!!pics.err && <Box sx={{ fontSize: 11, color: "#7a2f3c" }}>{pics.err}</Box>}
    </Box>
  );
}

// the words, then the files: how a CLI agent is shown a picture (server.with_images says it the same way)
export const withImages = (text, paths) => (paths?.length ? `${text || ""}\n\nATTACHED IMAGES (read these files)\n${paths.join("\n")}` : text || "");
