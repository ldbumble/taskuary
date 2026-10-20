// THE RING IS IN VIEW (the 2026-10-19 UI walk): Next put a report on the table while its row sat 100px under the rail's fold, so the
// rail ringed something nobody could see. After each change of what is on the table the rail scrolls by the least that shows the
// ringed rows whole - under their band's sticky heading, clear of the bottom fade - and does nothing when they already are.

// px to scroll the rail by: `view` the scroller's {top, bottom}, `rows` the ringed rows' {top, bottom} (union), `head` the sticky heading
// over them, `fade` the bottom fade's height. Rows taller than the room show from their top.
export const revealBy = (view, rows, head = 0, fade = 0) => {
  const top = view.top + head, bottom = view.bottom - fade;
  if (rows.top < top) return rows.top - top;
  if (rows.bottom > bottom) return Math.min(rows.bottom - bottom, rows.top - top);
  return 0;
};

// the DOM half: the rail under `wrap`, its ringed rows (the one on the table, or a batch's bracketed members)
export function revealRing(wrap) {
  const sc = wrap?.closest("[data-tq-rail]");
  const rows = [...(wrap?.querySelectorAll(".tq-pile-row.current, .tq-pile-row.inbatch") || [])];
  if (!sc || !rows.length) return 0;
  const rs = rows.map((r) => r.getBoundingClientRect());
  const box = { top: Math.min(...rs.map((r) => r.top)), bottom: Math.max(...rs.map((r) => r.bottom)) };
  const head = rows[0].closest(".tq-pile-band")?.querySelector(".tq-pile-head")?.getBoundingClientRect().height || 0;
  // half the fade: its upper half is still mostly see-through (FeedView draws it transparent to solid)
  const fade = (sc.parentElement?.querySelector("[data-tq-bottom-fade]")?.getBoundingClientRect().height || 0) / 2;
  const by = revealBy(sc.getBoundingClientRect(), box, head, fade);
  if (Math.abs(by) > 1) sc.scrollTop += by;          // the rail alone scrolls - scrollIntoView moved the page as well
  return by;
}
