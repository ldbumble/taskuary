// THE ADVISOR'S LINE IS ONE LINE (the owner, 2026-10-20: the strip over the prompt box wrapped onto two lines - "never want that, it
// looks weird"). assistantView.css clamps every .tq-next-txt to one line with an ellipsis; the whole sentence is its tooltip, set here
// once for every place the strip is drawn (setup, the canvas, a task page) as the pointer reaches a line that was cut.
export const cut = (el) => !!el && el.scrollWidth > el.clientWidth + 1;
export const titleCut = (e) => {
  const el = e?.target?.closest?.(".tq-next-txt");
  if (!el) return;
  if (cut(el)) el.title = el.innerText; else el.removeAttribute("title");
};
export const installOneLine = (doc = globalThis.document) => {
  if (!doc || doc.__tqOneLine) return;
  doc.__tqOneLine = true;
  doc.addEventListener("mouseover", titleCut, true);
  doc.addEventListener("focusin", titleCut, true);
};
