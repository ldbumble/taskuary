// A BAR OF BUTTONS IS ONE LINE (the owner, 2026-10-23: "the buttons turned into 2 rows ... NEVER do that"): the Tasks tab's bar at the
// view's foot wrapped like the canvas row did. Its buttons fold, lowest rank first, into one ▾ at its end until the line fits; a
// button with no rank (Mark done, Remind me) never folds. The canvas row's own fold is actionRow.js foldsOf - this is the same rule
// for a bar of fixed buttons.
import { useLayoutEffect, useRef, useState } from "react";

// items: [{ id, w, rank }] in drawn order - rank 1 folds first, 0 never. The ids to fold so the rest and the ▾ fit `avail`.
export function barFolds(items, avail, gap, more) {
  const total = (xs) => xs.reduce((a, x) => a + x.w, 0) + gap * Math.max(0, xs.length - 1);
  if (!(avail > 0) || total(items) <= avail) return [];
  const ranks = [...new Set(items.map((x) => x.rank).filter(Boolean))].sort((a, b) => a - b);
  for (let k = 1; k <= ranks.length; k++) {
    const gone = new Set(ranks.slice(0, k));
    if (total(items.filter((x) => !gone.has(x.rank))) + gap + more <= avail) return items.filter((x) => gone.has(x.rank)).map((x) => x.id);
  }
  return items.filter((x) => x.rank).map((x) => x.id);
}

// ref goes on the bar; each foldable child carries data-tq-bar-item={id} (ranks[id] its fold order), the ▾ data-tq-bar-more.
// Index ids (`#2`) are only stable while the children are: a bar whose fixed children change passes a new `key`.
// A folded child stays mounted, hidden, so its width is the one measured while it was drawn. `key` re-measures on a label change.
export function useFoldBar(ranks, key = "") {
  const [box, setBox] = useState(null), [folded, setFolded] = useState([]), w = useRef({});
  useLayoutEffect(() => {
    if (!box) return undefined;
    const fit = () => {
      const px = (cs, k) => parseFloat(cs[k]) || 0, width = (el) => { const cs = getComputedStyle(el); return Math.ceil(el.getBoundingClientRect().width + px(cs, "marginLeft") + px(cs, "marginRight")); };
      // every child counts - one with no id (Mark done, Remind me) by its width and never folds
      const kids = [...box.children].filter((el) => !el.hasAttribute("data-tq-bar-more")), more = box.querySelector("[data-tq-bar-more]");
      const els = kids.map((el, i) => ({ el, id: el.dataset.tqBarItem || `#${i}` }));
      els.forEach(({ el, id }) => { if (el.getClientRects().length) w.current[id] = width(el); });
      if (more?.getClientRects().length) w.current["▾"] = width(more);
      const cs = getComputedStyle(box), avail = box.clientWidth - px(cs, "paddingLeft") - px(cs, "paddingRight");
      const next = barFolds(els.map(({ id }) => ({ id, w: w.current[id] || 0, rank: ranks[id] || 0 })),
        avail, px(cs, "columnGap"), w.current["▾"] || 40);
      setFolded((f) => (f.join() === next.join() ? f : next));
    };
    fit();
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(fit);
    ro.observe(box);
    return () => ro.disconnect();
  }, [box, key, folded.length > 0, ranks]);   // ...and once the ▾ is drawn, by its real width
  return { ref: setBox, folded, shown: (id) => !folded.includes(id) };
}
