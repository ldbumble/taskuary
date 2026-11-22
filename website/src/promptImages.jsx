// PICTURES WITH A PROMPT (the owner, 2026-09-30: "can't attach images ... to write this prompt?"). One picker for every box that
// writes to an agent - the New box, the chat line, Continue: paste, drop, or the paperclip. Each image is saved by the server
// (/api/prompt-image, the waitroom's bytes-as-body contract) and the prompt carries its PATH - a CLI agent reads a picture from a
// file, and the assistant's own model is handed the picture itself (server.prompt_images).
// ...AND ANY FILE, where the box asks for them (`files`; the owner, 2026-11-05: "does drop in the prompt box attach it in all prompt boxes?"):
// a PDF, a sheet, a log goes to /api/prompt-file under its own name, the same 12 MB cap, and is drawn as a chip with that name
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Box, IconButton, Popover, Tooltip } from "@mui/material";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import CloseIcon from "@mui/icons-material/Close";
import api from "./api";
import { pastedFiles } from "./promptPaste.js";

export const IMAGE_TYPES = /^image\/(png|jpeg|gif|webp)$/;
export const MAX_IMAGES = 8;
export const IMAGE_ACCEPT = "image/png,image/jpeg,image/gif,image/webp";

// one file to the server: a picture through the image road (its type check), anything else through the file road; { path, name, image }
// ...IN A MINUTE OR TWO, or it says so (the owner, 2026-11-16: a paste's "Attaching..." never resolved and nothing was attached): an upload
// with no limit that stalled held the box's busy line for good
export const UPLOAD_MS = 120000;
export async function savePromptFile(f) {
  const image = IMAGE_TYPES.test(f.type), timeout = UPLOAD_MS;
  const named = f.name ? { "X-File-Name": encodeURIComponent(f.name) } : {};          // ...a picture under his name for it too, as any file
  const { data } = image ? await api.post("/api/prompt-image", f, { headers: { "Content-Type": f.type, ...named }, timeout })
    : await api.post("/api/prompt-file", f, { headers: { "Content-Type": "application/octet-stream", "X-File-Name": encodeURIComponent(f.name || "file") }, timeout });
  return { path: data.path, name: f.name || (image ? "pasted image" : "file"), image };
}

export function usePromptImages({ files: anyFile = false } = {}) {
  const [imgs, setImgs] = useState([]);                 // [{ path, url, name, image }]
  // ...EACH FILE IS ITS CHIP FROM THE PICK (the owner, 2026-11-18: pressing the paperclip again and again made the box jump): an upload drew
  // "uploading…" in the row, then took it away for the chip - the words stepped right twice per file, and on a phone the chips' line grew in two
  // steps, the paperclip with it. Now a picked file stands as its chip at once, faded until it is up, and the row reaches its size once
  const [pending, setPending] = useState([]);           // [{ key, url, name, image }] - picked, still uploading
  const [err, setErr] = useState("");
  const held = useRef({ imgs: 0, pending: 0 }), dropped = useRef(new Set()), seq = useRef(0);
  held.current = { imgs: imgs.length, pending: pending.length };
  const takes = useCallback((f) => anyFile || IMAGE_TYPES.test(f.type), [anyFile]);
  const add = useCallback(async (files) => {
    const list = [...(files || [])].filter(takes);
    if (!list.length) return false;
    const room = Math.max(0, MAX_IMAGES - held.current.imgs - held.current.pending), go = list.slice(0, room);
    const left = list.length - go.length;
    setErr(left ? `${MAX_IMAGES} go with one message - ${left} left out` : "");
    const mine = go.map((f) => ({ f, key: `up${++seq.current}`, name: f.name || (IMAGE_TYPES.test(f.type) ? "pasted image" : "file"), image: IMAGE_TYPES.test(f.type) }))
      .map((p) => ({ ...p, url: p.image ? URL.createObjectURL(p.f) : "" }));
    held.current.pending += mine.length;
    setPending((cur) => [...cur, ...mine.map(({ f, ...p }) => p)]);
    let i = 0;
    try {
      for (; i < mine.length; i++) {
        const { f, key, url } = mine[i], got = await savePromptFile(f);
        // ...the chip it stood as becomes the file, in one paint; one taken off while it uploaded stays off
        if (!dropped.current.delete(key)) setImgs((cur) => [...cur, { ...got, key, url }]);
        setPending((cur) => cur.filter((p) => p.key !== key));
      }
    } catch (e) {
      const off = new Set(mine.slice(i).map((p) => p.key));
      setPending((cur) => cur.filter((p) => !off.has(p.key)));
      setErr(e?.response?.data?.detail || (e?.code === "ECONNABORTED" ? "the upload took too long - try it again"
        : anyFile ? "the file did not upload - try it again" : "the image did not upload - try it again"));
    }
    return true;
  }, [takes, anyFile]);
  // a chip's x: a file that is up, by its path - or one still uploading, by its key, which then never lands
  const remove = useCallback((path) => {
    setImgs((cur) => cur.filter((i) => i.path !== path));
    setPending((cur) => { if (cur.some((p) => p.key === path)) dropped.current.add(path); return cur.filter((p) => p.key !== path); });
  }, []);
  // ...`cleared` counts the clears: a press held for files that a clear then took away is not made (useSendWhenUp)
  const [cleared, setCleared] = useState(0);
  const clear = useCallback(() => { setImgs([]); setErr(""); setCleared((n) => n + 1); setPending((cur) => { cur.forEach((p) => dropped.current.add(p.key)); return []; }); }, []);
  // ...and files a send could not take, put back in front of what was added since (a task chat's failed line)
  const put = useCallback((files) => setImgs((cur) => [...files.filter((f) => !cur.some((c) => c.path === f.path)), ...cur]), []);
  // a paste that carries an image (or, with `files`, any file) and no words is that file; anything else pastes as it always did (promptPaste)
  const onPaste = useCallback((e) => {
    const files = pastedFiles(e.clipboardData, takes);
    if (files.length) { e.preventDefault(); add(files); }
  }, [add, takes]);
  const onDrop = useCallback((e) => {
    const files = [...(e.dataTransfer?.files || [])].filter(takes);
    if (files.length) { e.preventDefault(); add(files); }
  }, [add, takes]);
  const onDragOver = useCallback((e) => { if ([...(e.dataTransfer?.types || [])].includes("Files")) e.preventDefault(); }, []);
  return { imgs, pending, paths: imgs.map((i) => i.path), busy: pending.length > 0, cleared, err, add, remove, clear, put, files: anyFile, drop: { onPaste, onDrop, onDragOver } };
}

// SEND WAITS FOR ITS FILES (2026-11-18): Enter pressed while a picked file was still uploading sent the words without it - the file then
// landed alone in the emptied box (a task's chat), or was dropped with New's closed box. One road for every box: a press while files upload is
// held, and goes once they are up, with them; an upload that failed leaves the words in the box under its error. `waiting`: a press is held
export function useSendWhenUp(pics, send) {
  const want = useRef(null), [waiting, setWaiting] = useState(false), busy = !!pics?.busy;
  useEffect(() => {
    if (want.current == null || busy) return;
    const held = want.current; want.current = null; setWaiting(false);
    // ...not when the upload failed, nor when the box was cleared under it (its task changed, or it closed)
    if (!pics?.err && held === pics?.cleared) send();
  }, [busy]);   // ...on the change alone: the send of that render reads what it holds then
  const go = useCallback(() => { if (busy) { want.current = pics?.cleared; setWaiting(true); return; } send(); }, [busy, send, pics?.cleared]);
  return { go, waiting };
}

// the paperclip: opens the file picker - images only, or any file where the box takes them
export function AttachImage({ pics, size = 18, sx }) {
  const input = useRef(null), what = pics.files ? "a file" : "an image";
  return (
    <>
      <Tooltip title={pics.busy ? "Uploading…" : `Attach ${what} - or paste or drop one here`}>
        <span><IconButton size="small" aria-label={`Attach ${what}`} disabled={pics.busy} onClick={() => input.current?.click()}
          sx={{ width: 34, height: 34, p: 0, color: "var(--tq-secondary, #6e685f)", ...sx }}><AttachFileIcon sx={{ fontSize: size }} /></IconButton></span>
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
      borderRadius: "12px", bgcolor: warn ? "var(--tq-panel, #fbf3e8)" : "var(--tq-inset, #e4e9ee)", border: `1px solid ${warn ? "var(--tq-edge-brass, #e2c9a8)" : "transparent"}`, fontSize: 12.5, color: "var(--tq-link, #2f3a42)",
      boxSizing: "border-box", textDecoration: "none", ...(opens ? { cursor: "pointer", "&:hover": { borderColor: "var(--tq-border, #b9c6d1)" } } : {}), ...sx }}>
    {thumb ? <Box component="img" src={thumb} alt="" sx={{ width: 18, height: 18, borderRadius: "50%", objectFit: "cover", flexShrink: 0 }} />
      : icon === false ? null : icon || <AttachFileIcon sx={{ fontSize: 13, color: "var(--tq-link, #55697a)", flexShrink: 0 }} />}
    {/* ...THE NAME BEFORE ITS SIZE (the design walk, 2026-11-20: a cramped chip read "Q... 44 KB"): the name keeps a few letters and the size
        gives way first */}
    <Box component="span" sx={{ minWidth: "min(7ch, 100%)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{name}</Box>
    {note && <Box component="span" sx={{ color: "var(--tq-link, #7d8a94)", fontSize: 11, whiteSpace: "nowrap", flexShrink: 1, minWidth: 0, overflow: "hidden" }}>{note}</Box>}
    {warn && <Box component="span" sx={{ color: "var(--tq-warning, #8a5a1c)", whiteSpace: "nowrap", flexShrink: 0 }}>· {warn.length > 24 ? "can't go" : warn}</Box>}
    {onRemove && <IconButton size="small" aria-label={`Remove ${name}`} onClick={(e) => { e.stopPropagation(); onRemove(e); }} sx={{ width: 18, height: 18, p: 0, color: "var(--tq-link, #55697a)", flexShrink: 0 }}>
      <CloseIcon sx={{ fontSize: 12 }} /></IconButton>}
  </Box>;
}
// ...in ONE line, however many: the row never grows the box (2026-10-31) - and never scrolls sideways (the owner, 2026-11-06): the first `few`
// chips, then "+N more", which opens the whole list. A chip cuts its name before the row would run past its width
export const ATTACH_FEW = 3;
export const attachSplit = (n, few = ATTACH_FEW) => (n > few + 1 ? few : n);   // how many chips stand in the row: "+1 more" is never worth its chip
const isChip = (c) => React.isValidElement(c) && c.type === AttachChip;
// ...a box hands its chips in fragments ({came}{his files}): read through them, or no chip was counted and "+N more" never came - the rest ran
// off the box's edge, out of sight and out of reach of their x
const flat = (children) => React.Children.toArray(children).flatMap((c) => (React.isValidElement(c) && c.type === React.Fragment ? flat(c.props.children) : [c]));
// ...INSIDE THE BOX, on its one line: left of the words, never more than a third of it, so the box stays one thin line (the owner, 2026-11-06)
export const INLINE_CHIPS = { flex: "0 1 auto", maxWidth: "34%", pb: 0 };

export function AttachRow({ children, sx, few = ATTACH_FEW, ...rest }) {
  const [at, setAt] = useState(null);
  const all = flat(children), chips = all.filter(isChip), other = all.filter((c) => !isChip(c)), k = attachSplit(chips.length, few), more = chips.slice(k);
  return <Box data-tq-attach-row="" {...rest} sx={{ display: "flex", flexWrap: "nowrap", alignItems: "center", gap: 0.5, minWidth: 0, maxWidth: "100%", overflow: "hidden",
    pb: 0.25, "& > .tq-attach-chip": { flexShrink: 1, minWidth: 96 }, "& > [data-tq-attach-more]": { flexShrink: 0 }, ...sx }}>
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
// the files waiting to go, as chips: `cannot(i)` says what this box's road cannot do with one. One still uploading is the same chip, faded - the
// same size it will have, so nothing moves when it is up
export const fileChips = (pics, cannot = null) => [
  ...pics.imgs.map((i) => <AttachChip key={i.key || i.path} data-tq-file-chip={i.name} data-tq-file-cannot={cannot?.(i) || undefined}
    name={i.name} thumb={i.image === false ? "" : i.url || ""} warn={cannot?.(i) || ""} onRemove={() => pics.remove(i.path)} />),
  ...(pics.pending || []).map((p) => <AttachChip key={p.key} data-tq-file-chip={p.name} data-tq-file-pending="" aria-busy="true" title={`${p.name} - uploading…`}
    name={p.name} thumb={p.url} onRemove={() => pics.remove(p.key)} sx={{ opacity: 0.55 }} />)];
export const fileState = (pics) => <>{!!pics.err && <Box component="span" sx={{ fontSize: 11, color: "var(--tq-danger, #7a2f3c)", flexShrink: 0 }}>{pics.err}</Box>}</>;
// a box that keeps its files OUTSIDE it (the dock, Continue, New): the same chips, the same one line
export function ImageTray({ pics, sx, cannot = null }) {
  if (!pics.imgs.length && !pics.err && !pics.busy) return null;
  return <AttachRow data-tq-image-tray="" sx={sx}>{fileChips(pics, cannot)}{fileState(pics)}</AttachRow>;
}

// the words, then the files: how a CLI agent is shown a picture or a file (server.with_images says it the same way)
// WHAT HE ATTACHED IS A FIELD BESIDE HIS WORDS (the design loop, 2026-11-20): every door sends `files` (the saved uploads, pics.paths) next to
// the words, and the server keeps them on the line or the task (store.files_json) - never a block written into the words, which ~40 readers
// parsed back and a door that wrote it slightly differently lost from his bubble. A prompt's block is built on the server, from the field
