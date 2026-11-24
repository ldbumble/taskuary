// A TABLE NEVER WRAPS WHILE THERE IS ROOM (the owner, 2026-11-24, a report's table in the 640px frame - "elementalsoul/s" broken mid-word, tall
// rows, half the screen empty: "I hate wrapped text ... if items get shoved onto another row, make font smaller or make the report a little
// bigger"). ONE rule for every artifact's table, markdown or view, in this order: (1) its frame widens to the table's natural width, up to the
// chat's; (2) still too wide, its font steps down a notch; (3) then it wraps - at word boundaries only, a short or numeric column never;
// (4) last, it scrolls inside its frame. No per-report or per-agent sizing.
import { useLayoutEffect } from "react";

export const SMALLER = 12;                       // ...the one notch down (14 / 13.5 / 12.5 -> 12), never below it
// `need`: the table's width with nothing wrapped, at `font`; `least`: its width with every text column wrapped at its words; `room`: the frame's
// own width; `chat`: the most the frame may take. -> { width: what the frame takes (0: as it is), font, wrap, scroll }
export function fitTable({ need, least = need, room, chat, font }) {
  if (need <= room) return { width: 0, font, wrap: false, scroll: false };
  if (need <= chat) return { width: Math.ceil(need), font, wrap: false, scroll: false };
  const k = font > SMALLER ? SMALLER / font : 1, small = font * k;
  if (need * k <= chat) return { width: Math.ceil(need * k), font: small, wrap: false, scroll: false };
  return { width: Math.ceil(chat), font: small, wrap: true, scroll: least * k > chat };
}

// a short column - every cell a number, one word (a name, a slug, a link) or a few short words - is never wrapped: it shrinks to fit, the text columns take the rest
const NUM = /^\s*[-+]?[$€£¥]?\s*[\d.,]+\s*[%kKmMbB]?\s*$/;
export const shortColumn = (cells) => cells.every((c) => { const s = String(c ?? "").trim(); return !s || NUM.test(s) || !/\s/.test(s) || s.length <= 20; });

// ...measured where it is drawn: the table at its natural width, then with its text columns wrapped; its frame (.tq-turn-frame, else the
// chat's column) told the width it may take as --tq-fit-w, the table its font, and each short column marked no-wrap
export function useTableFit(ref, deps = []) {
  useLayoutEffect(() => {
    const wrap = ref.current, t = wrap?.querySelector("table");
    if (!t) return undefined;
    const fit = () => {
      const frame = wrap.closest(".tq-turn-frame"), chat = (frame?.parentElement || wrap.parentElement)?.clientWidth || wrap.clientWidth;
      const rows = [...t.rows], n = Math.max(0, ...rows.map((r) => r.cells.length));
      const short = Array.from({ length: n }, (_, i) => shortColumn(rows.slice(1).map((x) => x.cells[i]?.innerText)));
      rows.forEach((r) => [...r.cells].forEach((c, i) => c.toggleAttribute("data-tq-short", short[i])));
      if (!wrap.dataset.tqFit) wrap.dataset.tqFit = "fit";         // ...measured under the fit's own layout: under the chat's fixed one a table is its box's width
      t.style.fontSize = ""; const font = parseFloat(getComputedStyle(t).fontSize) || 13;
      t.style.width = "max-content"; t.style.maxWidth = "none"; t.style.minWidth = "0"; const need = t.offsetWidth;
      t.style.width = "min-content"; const least = t.offsetWidth; t.style.width = t.style.maxWidth = t.style.minWidth = "";
      const pad = (frame ? frame.offsetWidth - frame.clientWidth : 0) + (wrap.offsetLeft || 0) * 2;
      const room = wrap.clientWidth, f = fitTable({ need, least, room, chat: chat - pad, font });
      frame?.style.setProperty("--tq-fit-w", f.width ? `${f.width + pad}px` : "0px");
      if (f.font !== font) t.style.fontSize = `${f.font}px`;
      wrap.dataset.tqFit = f.scroll ? "scroll" : f.wrap ? "wrap" : "fit"; wrap.dataset.tqCols = String(n);
    };
    fit();
    // ...and again when the chat's column changes, or the table itself does (its font loaded after the first measure: a dark-theme shot measured
    // it in the fallback face, too narrow, and three rows wrapped)
    let live = true; document.fonts?.ready?.then(() => { if (live) fit(); });
    if (typeof ResizeObserver === "undefined") return () => { live = false; };
    const ro = new ResizeObserver(() => fit()), host = wrap.closest(".tq-turn-frame")?.parentElement || wrap.parentElement;
    if (host) ro.observe(host);
    ro.observe(t);
    return () => { live = false; ro.disconnect(); };
  }, deps);    // eslint-disable-line react-hooks/exhaustive-deps
}
