// SAVING AND REACHING A FILE - one road for every file the page offers: a mail's attachment, a file an agent made, a page it showed.
import { useState } from "react";
import api from "./api";

// An <img src> carries no headers: the server reads a file by the cookie it handed this page (token_gate's FILE_COOKIE) - never a token in
// the address, where history, a referer and a log keep it (the red team, 2026-11-24, T8c)
export const attUrl = (a, download) => {
  if (String(a.url || "").startsWith("data:")) return a.url;   // the static demo carries its own bytes
  const q = download ? "download=true" : "";
  return `${a.url}${q ? `${String(a.url).includes("?") ? "&" : "?"}${q}` : ""}`;   // a link that came with its own query keeps it
};

// what a refused file read said, from a JSON body or a Blob one (a preview asks for bytes, so its error comes back as a Blob too)
export const fileError = async (e, fallback) => {
  let d = e?.response?.data;
  if (typeof Blob !== "undefined" && d instanceof Blob) { try { d = JSON.parse(await d.text()); } catch { d = null; } }
  return (d && typeof d === "object" && d.detail) || fallback;
};

// SAVE A FILE, never navigate to it. A Download that was a plain link took the window to the file's address: a file moved or deleted
// left the owner on a raw JSON 404 - and the desktop window has no Back. The server is asked first (HEAD); a file that is there is
// saved by a link with `download`, so the page stays where it is; one that is not throws the server's own reason for the page to say.
// ...and in the desktop window it lands in the computer's Downloads folder, said in words (desktop.save_download): WebView2's own
// download opened a Save As box wherever it liked (the owner, 2026-11-02: "the download should go to the local computer download").
// Resolves to the line to show once saved there, or "" when the browser's own download took it.
export const savedLine = (r) => r?.name ? `Saved to ${r.folder || "Downloads"} as ${r.name}` : "";
export const saveFile = async (a, w = typeof window === "undefined" ? null : window) => {
  const href = attUrl(a, true), bridge = w?.pywebview?.api;
  if (typeof bridge?.save_download === "function" && !href.startsWith("data:")) {
    const r = await bridge.save_download(new URL(href, w.location.href).href);
    if (!r?.name) throw new Error(r?.error || "This file could not be saved - try again.");
    return savedLine(r);
  }
  if (!href.startsWith("data:") && typeof api.head === "function") {
    // no-cache: the browser answered a HEAD from the copy a preview had fetched, so a file deleted since was still "there"
    try { await api.head(a.url, { headers: { "Cache-Control": "no-cache" } }); }
    catch (e) {
      // a HEAD has no body to carry the reason: ask once more for it - a file that is gone answers in a few bytes
      let why = "";
      try { await api.get(a.url, { params: { download: true }, responseType: "blob", headers: { "Cache-Control": "no-cache" } }); }
      catch (e2) { why = await fileError(e2, ""); }
      throw new Error(why || (e?.response?.status === 404 ? "This file was moved or deleted." : "This file could not be saved - try again."));
    }
  }
  const el = document.createElement("a");
  // `download` empty: the server's Content-Disposition names it (a published page gets its .html there)
  el.href = href; el.download = ""; el.rel = "noopener"; el.style.display = "none";
  document.body.appendChild(el); el.click(); el.remove();
  return "";
};

// [error, save, saved]: a Download's press, the line it leaves when the file is not there, and where the desktop put it (both cleared
// by the next press)
export const useSave = () => {
  const [err, setErr] = useState(""), [saved, setSaved] = useState("");
  return [err, (a) => { setErr(""); setSaved(""); saveFile(a).then(setSaved, (e) => setErr(e.message)); }, saved];
};
