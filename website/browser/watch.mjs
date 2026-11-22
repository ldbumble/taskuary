/* WHAT THE OWNER WOULD SEE GO WRONG, CAUGHT WHILE IT HAPPENS (the owner, 2026-11-22: "you have to look at it to see if it works, and nothing
   flickers"). A sampler inside the page reads every 100 ms what is on screen - each button, card, row and line Taskuary marks (data-tq-*) - and
   says, for one step of a walk:
   - flicker: a thing that showed for under 1.5 s and went, or came and went more than once
   - jump:    a thing that sat still, then moved more than 24 px while nobody scrolled
   - blank:   the chat emptied for a beat mid-step
   - junk:    words no person should read - a marker, an id, a traceback, "undefined"
   - twice:   the same card or row drawn two times at once
   Read with the step's screenshots: a finding here is a finding even where the step "worked". */

const SAMPLER = () => {
  if (window.__tqWatch) return;
  const JUNK = /\[\[|\]\]|TASKUARY-|Traceback|\bundefined\b|\bNaN\b|\[object Object\]|\brv\d+\b|\bTQ-\d{4}\b.*\bTQ-\d{4}\b|Exception:|Error: [A-Z]/;
  const w = window.__tqWatch = { t0: performance.now(), seen: new Map(), blank: [], junk: new Map(), twice: new Map(), scrolledAt: -1e9 };
  addEventListener("wheel", () => { w.scrolledAt = performance.now(); }, { passive: true, capture: true });
  addEventListener("scroll", () => { w.scrolledAt = performance.now(); }, { passive: true, capture: true });
  const keyOf = (el) => {
    const a = [...el.attributes].find((x) => x.name.startsWith("data-tq-"));
    return `${el.tagName.toLowerCase()}${a ? `[${a.name}]` : ""} ${(el.innerText || el.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 80)}`;
  };
  const tick = () => {
    const t = Math.round(performance.now() - w.t0), now = new Map();
    for (const el of document.querySelectorAll("button, [role=alert], [data-tq-task-page] [class*=card], [class*=tq-][data-tq-on-you], [data-tq-summary], [data-tq-row], [data-tq-line-failed]")) {
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > innerHeight) continue;
      const k = keyOf(el); if (!k.trim()) continue;
      now.set(k, (now.get(k) || 0) + 1);
      const s = w.seen.get(k) || { spans: [], tops: [] };
      const last = s.spans.at(-1);
      if (!last || last[1] < t - 150) s.spans.push([t, t]); else last[1] = t;
      const top = Math.round(r.top), pt = s.tops.at(-1);
      if (!pt || pt[1] !== top) s.tops.push([t, top]);
      w.seen.set(k, s);
    }
    for (const [k, n] of now) if (n > 1 && /card|row|alert|summary/.test(k)) w.twice.set(k, Math.max(n, w.twice.get(k) || 0));
    const vp = document.querySelector("[data-tq-task-page] .tq-aui-viewport");
    if (vp) { const len = vp.innerText.trim().length; if (len < 20) w.blank.push(t); }
    const text = document.body.innerText, m = text.match(JUNK);
    if (m) { const i = m.index, ctx = text.slice(Math.max(0, i - 60), i + 80).replace(/\s+/g, " "); if (!w.junk.has(ctx)) w.junk.set(ctx, t); }
  };
  w.timer = setInterval(tick, 100); tick();
};

const REPORT = () => {
  const w = window.__tqWatch; if (!w) return null;
  clearInterval(w.timer);
  const end = Math.round(performance.now() - w.t0), out = { flicker: [], jump: [], blank: [], junk: [], twice: [] };
  for (const [k, s] of w.seen) {
    const shown = s.spans.filter(([a, b]) => b < end - 200);         // ...a span still open at the end is the step's result, not a flicker
    if (s.spans.length > 2 || shown.some(([a, b]) => b - a < 1500 && a > 300)) out.flicker.push({ what: k, spans: s.spans.slice(0, 6) });
    for (let i = 1; i < s.tops.length; i++) {
      const [ta, ya] = s.tops[i - 1], [tb, yb] = s.tops[i];
      if (Math.abs(yb - ya) > 24 && tb - ta > 300 && Math.abs(tb - w.scrolledAt) > 800) { out.jump.push({ what: k, at: tb, from: ya, to: yb }); break; }
    }
  }
  // ...a blank beat is two or more empty samples in a row, after the chat had words
  for (let i = 1; i < w.blank.length; i++) if (w.blank[i] - w.blank[i - 1] <= 150 && !out.blank.includes(w.blank[i - 1])) out.blank.push(w.blank[i - 1]);
  out.junk = [...w.junk].map(([ctx, t]) => ({ at: t, ctx }));
  out.twice = [...w.twice].map(([what, n]) => ({ what, n }));
  delete window.__tqWatch;
  return out;
};

// watch(page) at a step's start; `await stop()` at its end -> the findings, [] of each kind when the step looked right
export async function watch(page) {
  await page.evaluate(SAMPLER);
  return { stop: async () => (await page.evaluate(REPORT)) || { flicker: [], jump: [], blank: [], junk: [], twice: [] } };
}
export const clean = (f) => !Object.values(f).some((v) => v.length);
export const said = (f) => Object.entries(f).filter(([, v]) => v.length).map(([k, v]) => `${k}: ${v.slice(0, 4).map((x) => typeof x === "number" ? `${x}ms` : JSON.stringify(x)).join("; ")}`).join("\n");
