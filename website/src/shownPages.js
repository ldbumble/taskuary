// What a chat published or SHOWED the owner (PublishedPages.jsx), the parts with no React in them.

// NO NETWORK for a page (PublishedPages.SANDBOX gives it an opaque origin, which can still fetch): a page could carry what it was given - the task's figures - to any
// server, or knock on this app's own port. The policy goes in first and a script cannot lift it. Libraries may still load
// from the public CDNs Claude's own artifacts use; a request to one carries nothing anybody else reads.
const CDNS = "https://cdnjs.cloudflare.com https://cdn.jsdelivr.net https://unpkg.com";
export const CSP = `default-src 'none'; script-src 'unsafe-inline' 'unsafe-eval' data: blob: ${CDNS}; `
  + `style-src 'unsafe-inline' data: ${CDNS} https://fonts.googleapis.com; font-src data: ${CDNS} https://fonts.gstatic.com; `
  + "img-src data: blob:; media-src data: blob:; connect-src 'none'; form-action 'none'; base-uri 'none'";
// after a doctype (before it the page would fall into quirks mode), ahead of everything the page says
export const lockDown = (html) => {
  const meta = `<meta http-equiv="Content-Security-Policy" content="${CSP}">`;
  const m = /^\s*<!doctype[^>]*>/i.exec(html || "");
  return m ? m[0] + meta + html.slice(m[0].length) : meta + (html || "");
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
