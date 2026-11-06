// PICTURES WITH A PROMPT (the owner, 2026-09-30: "can't attach images ... to write this prompt?"). One picker for every box that
// writes to an agent - the New box, the chat line, Continue: paste, drop, or the paperclip. Each image is saved by the server
// (/api/prompt-image, the waitroom's bytes-as-body contract) and the prompt carries its PATH - a CLI agent reads a picture from a
// file, and the assistant's own model is handed the picture itself (server.prompt_images).
// ...AND ANY FILE, where the box asks for them (`files`; the owner, 2026-11-05: "does drop in the prompt box attach it in all prompt boxes?"):
// a PDF, a sheet, a log goes to /api/prompt-file under its own name, the same 12 MB cap, and is drawn as a chip with that name
import React, { useCallback, useRef, useState } from "react";
import { Box, IconButton, Popover, Tooltip } from "@mui/material";
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

// ONE ATTACHMENT LOOK (the owner, 2026-11-05, of the item chip on an Agent tab's box: make it the look everywhere): what goes with the words - an
// item it was sent from, a file from the paperclip, a dropped or pasted picture - is one chip: a mark (or the picture, small), the name cut with
// … and whole on hover, and its x. `warn`: why this box's road cannot take it, said on the chip instead of dropping it silently
// ...and EVERY ATTACHMENT IS THIS CHIP (the owner, 2026-11-06): a message's files and a draft's too. `note`: a faint word after the name (its size,
// "not saved"); `onClick` (or an `href` with component="a") opens it; `icon={false}` for none
export function AttachChip({ name, icon = null, thumb = "", warn = "", note = "", onRemove = null, title = "", sx, ...rest }) {
  const opens = !!(rest.onClick || rest.href);
  return <Box className="tq-attach-chip" {...rest} title={warn ? `${name} - ${warn}` : title || name}
    sx={{ display: "inline-flex", alignItems: "center", gap: 0.5, flexShrink: 0, maxWidth: 240, height: 24, pl: thumb ? 0.25 : 0.75, pr: onRemove ? 0.25 : 0.75,
      borderRadius: "12px", bgcolor: warn ? "#fbf3e8" : "#e4e9ee", border: `1px solid ${warn ? "#e2c9a8" : "transparent"}`, fontSize: 12.5, color: "#2f3a42",
      boxSizing: "border-box", textDecoration: "none", ...(opens ? { cursor: "pointer", "&:hover": { borderColor: "#b9c6d1" } } : {}), ...sx }}>
    {thumb ? <Box component="img" src={thumb} alt="" sx={{ width: 18, height: 18, borderRadius: "50%", objectFit: "cover", flexShrink: 0 }} />
      : icon === false ? null : icon || <AttachFileIcon sx={{ fontSize: 13, color: "#55697a", flexShrink: 0 }} />}
    <Box component="span" sx={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</Box>
    {note && <Box component="span" sx={{ color: "#7d8a94", fontSize: 11, whiteSpace: "nowrap", flexShrink: 0 }}>{note}</Box>}
    {warn && <Box component="span" sx={{ color: "#8a5a1c", whiteSpace: "nowrap", flexShrink: 0 }}>· {warn.length > 24 ? "can't go" : warn}</Box>}
    {onRemove && <IconButton size="small" aria-label={`Remove ${name}`} onClick={(e) => { e.stopPropagation(); onRemove(e); }} sx={{ width: 18, height: 18, p: 0, color: "#55697a", flexShrink: 0 }}>
      <CloseIcon sx={{ fontSize: 12 }} /></IconButton>}
  </Box>;
}
// ...in ONE line, however many: the row never grows the box (2026-10-31) - and never scrolls sideways (the owner, 2026-11-06): the first `few`
// chips, then "+N more", which opens the whole list. A chip cuts its name before the row would run past its width
export const ATTACH_FEW = 3;
export const attachSplit = (n, few = ATTACH_FEW) => (n > few + 1 ? few : n);   // how many chips stand in the row: "+1 more" is never worth its chip
const isChip = (c) => React.isValidElement(c) && c.type === AttachChip;
export function AttachRow({ children, sx, few = ATTACH_FEW, ...rest }) {
  const [at, setAt] = useState(null);
  const all = React.Children.toArray(children), chips = all.filter(isChip), other = all.filter((c) => !isChip(c)), k = attachSplit(chips.length, few), more = chips.slice(k);
  return <Box data-tq-attach-row="" {...rest} sx={{ display: "flex", flexWrap: "nowrap", alignItems: "center", gap: 0.5, minWidth: 0, maxWidth: "100%", overflow: "hidden",
    pb: 0.25, "& > .tq-attach-chip": { flexShrink: 1, minWidth: 56 }, "& > [data-tq-attach-more]": { flexShrink: 0 }, ...sx }}>
    {chips.slice(0, k)}
    {more.length > 0 && <AttachChip name={`+${more.length} more`} icon={false} component="button" type="button" data-tq-attach-more={more.length}
      aria-haspopup="dialog" aria-expanded={!!at} title={`Show all ${chips.length}`} onClick={(e) => setAt(e.currentTarget)}
      sx={{ font: "inherit", fontSize: 12.5, fontWeight: 600, appearance: "none" }} />}
    {other}
    <Popover open={!!at} anchorEl={at} onClose={() => setAt(null)} anchorOrigin={{ vertical: "top", horizontal: "left" }} transformOrigin={{ vertical: "bottom", horizontal: "left" }}
      slotProps={{ paper: { sx: { p: 1, maxWidth: 320, maxHeight: 320, overflowY: "auto" } } }}>
      <Box data-tq-attach-all="" sx={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 0.5, "& > .tq-attach-chip": { maxWidth: "100%" } }}>{chips}</Box>
    </Popover>
  </Box>;
}
// the files waiting to go, as chips: `cannot(i)` says what this box's road cannot do with one
export const fileChips = (pics, cannot = null) => pics.imgs.map((i) => <AttachChip key={i.path} data-tq-file-chip={i.name} data-tq-file-cannot={cannot?.(i) || undefined}
  name={i.name} thumb={i.image === false ? "" : i.url || ""} warn={cannot?.(i) || ""} onRemove={() => pics.remove(i.path)} />);
export const fileState = (pics) => <>{pics.busy && <Box component="span" sx={{ fontSize: 11, color: "#a09889", flexShrink: 0 }}>uploading…</Box>}
  {!!pics.err && <Box component="span" sx={{ fontSize: 11, color: "#7a2f3c", flexShrink: 0 }}>{pics.err}</Box>}</>;
// a box that keeps its files OUTSIDE it (the dock, Continue, New): the same chips, the same one line
export function ImageTray({ pics, sx, cannot = null }) {
  if (!pics.imgs.length && !pics.err && !pics.busy) return null;
  return <AttachRow data-tq-image-tray="" sx={sx}>{fileChips(pics, cannot)}{fileState(pics)}</AttachRow>;
}

// the words, then the files: how a CLI agent is shown a picture or a file (server.with_images says it the same way)
export const withImages = (text, paths) => (paths?.length
  ? `${text || ""}\n\n${paths.every(isImagePath) ? "ATTACHED IMAGES" : "ATTACHED FILES"} (read these files)\n${paths.join("\n")}` : text || "");
