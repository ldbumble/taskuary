// "Add a screenshot": the window as a picture with none of its words in it. No library - the page draws a copy of
// itself through an SVG foreignObject onto a canvas. The words are not blurred but REPLACED before drawing (every
// visible character becomes "x", then blurred), so no deblurring can bring back a name: what reaches the tracker is
// the layout, which is what a maintainer needs to see. Images, canvases and frames (avatars, terminals, the browser
// pane) are not carried: an SVG drawn as an image loads nothing from outside, and a canvas copies empty.
export const mask = (s) => String(s || "").replace(/\S/g, "x");
const BLUR = "*{color:transparent!important;text-shadow:0 0 6px rgba(60,60,60,.55)!important;caret-color:transparent!important}"
  + "img,video,canvas,iframe,svg image{visibility:hidden!important}";

function scrubbed(root) {
  const c = root.cloneNode(true), w = document.createTreeWalker(c, window.NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) n.nodeValue = mask(n.nodeValue);
  // a field's typed text is its live value, not the clone's: written back masked, or the field draws empty
  const live = root.querySelectorAll("input,textarea"), copy = c.querySelectorAll("input,textarea");
  copy.forEach((el, i) => { const v = mask(live[i]?.value); el.removeAttribute("placeholder");
    if (el.tagName === "TEXTAREA") el.textContent = v; else if (!/^(checkbox|radio|hidden)$/i.test(el.type)) el.setAttribute("value", v); });
  c.querySelectorAll("script,iframe,img,video,canvas,[title],[aria-label]").forEach((el) => {
    if (/^(SCRIPT|IFRAME|IMG|VIDEO)$/.test(el.tagName)) el.remove(); else { el.removeAttribute("title"); el.removeAttribute("aria-label"); } });
  return c;
}

// the page's own rules (emotion writes MUI's through the CSSOM, so a <style>'s text is empty); a cross-origin sheet
// (the web font) refuses to be read and is skipped - the text is masked, its face does not matter
const rules = () => [...document.styleSheets].flatMap((s) => { try { return [...s.cssRules].map((r) => r.cssText); } catch { return []; } }).join("\n");

export async function capture(root = document.getElementById("root")) {
  const W = window.innerWidth, H = window.innerHeight, b = getComputedStyle(document.body);
  const box = document.createElement("div"), st = document.createElement("style");
  st.textContent = `${rules()}\n${BLUR}`;
  box.setAttribute("style", `width:${W}px;height:${H}px;overflow:hidden;background:${b.backgroundColor};font:${b.font}`);
  box.append(st, scrubbed(root));
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}"><foreignObject width="100%" height="100%">`
    + `${new window.XMLSerializer().serializeToString(box)}</foreignObject></svg>`;
  const img = new Image();
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  await img.decode();
  const cv = document.createElement("canvas"), k = Math.min(window.devicePixelRatio || 1, 2);
  cv.width = W * k; cv.height = H * k;
  const g = cv.getContext("2d"); g.scale(k, k); g.drawImage(img, 0, 0);
  return await new Promise((ok, no) => cv.toBlob((x) => (x ? ok(x) : no(new Error("the screenshot could not be drawn"))), "image/png"));
}

// a Promise inside the ClipboardItem keeps the press's user activation alive while the picture draws; always a promise,
// so a browser without ClipboardItem lands in the caller's .catch instead of throwing past it
export const copyShot = (p) => Promise.resolve().then(() => navigator.clipboard.write([new window.ClipboardItem({ "image/png": p })]));
