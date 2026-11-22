/* WHAT THE OWNER WOULD SEE GO WRONG, CAUGHT WHILE IT HAPPENS (the owner, 2026-11-22: "you have to look at it to see if it works, and nothing
   flickers"). A sampler inside the page reads every 100 ms what is on screen - each button, card, row and line Taskuary marks (data-tq-*) - and
   says, for one step of a walk:
   - flicker: a thing that showed for under 1.5 s and went, or came and went more than once
   - jump:    a thing that sat still, then moved more than 24 px while nobody scrolled
   - blank:   the chat emptied for a beat mid-step
   - junk:    words no person should read - a marker, an id, a traceback, "undefined"
   - twice:   the same card or row drawn two times at once
   - stall:   the page could not paint for over 400 ms (a freeze a person feels)
   Read with the step's screenshots: a finding here is a finding even where the step "worked". */

const SAMPLER = () => {
  if (window.__tqWatch) return;
  const JUNK = /\[\[|\]\]|TASKUARY-|Traceback|undefined|NaN|\[object Object\]|rv\d+|Exception:|Error: [A-Z]/;
  // ...each element by ITS OWN identity (the first goal walk read New's mic and the task's - one label - as one button that jumped 590 px)
  const ids = new WeakMap(); let next = 0;
  const w = window.__tqWatch = { t0: performance.now(), seen: new Map(), blank: [], junk: new Map(), twice: new Map(), stalls: [], last: 0, scrolledAt: -1e9 };
  addEventListener("wheel", () => { w.scrolledAt = performance.now(); }, { passive: true, capture: true });
  addEventListener("scroll", () => { w.scrolledAt = performance.now(); }, { passive: true, capture: true });
  const label = (el) => {
    const a = [...el.attributes].find((x) => x.name.startsWith("data-tq-"));
    return `${el.tagName.toLowerCase()}${a ? `[${a.name}]` : ""} ${(el.innerText || el.getAttribute("aria-label") || "").trim().replace(/\s+/g, " ").slice(0, 80)}`;
  };
  const tick = () => {
    const t = Math.round(performance.now() - w.t0), here = new Set(), texts = new Map();
    // ...a beat the page could not paint is a STALL, said as one - never read as everything flickering at once
    if (w.last && t - w.last > 300) w.stalls.push([w.last, t]);
    w.last = t;
    for (const el of document.querySelectorAll("button, [role=alert], [data-tq-task-page] [class*=card], [data-tq-summary], [data-tq-row], [data-tq-line-failed], [data-tq-act]")) {
      const r = el.getBoundingClientRect();
      if (r.width < 2 || r.height < 2 || r.bottom < 0 || r.top > innerHeight) continue;
      const lb = label(el); if (!lb.trim()) continue;
      if (!ids.has(el)) ids.set(el, ++next);
      const id = ids.get(el); here.add(id); texts.set(lb, (texts.get(lb) || 0) + 1);
      const s = w.seen.get(id) || { label: lb, spans: [], tops: [], open: false };
      if (s.open) s.spans.at(-1)[1] = t; else { s.spans.push([t, t]); s.open = true; }
      const top = Math.round(r.top); if (!s.tops.length || s.tops.at(-1)[1] !== top) s.tops.push([t, top]);
      w.seen.set(id, s);
    }
    for (const [id, s] of w.seen) if (s.open && !here.has(id)) s.open = false;      // ...gone only where a sample SAW it gone
    for (const [k, n] of texts) if (n > 1 && /\[data-tq-(act|row|summary)\]|alert|card/.test(k)) w.twice.set(k, Math.max(n, w.twice.get(k) || 0));
    const vp = document.querySelector("[data-tq-task-page] .tq-aui-viewport");
    if (vp && vp.innerText.trim().length < 20) w.blank.push(t);
    const text = document.body.innerText, m = text.match(JUNK);
    if (m) { const i = m.index, ctx = text.slice(Math.max(0, i - 60), i + 80).replace(/\s+/g, " "); if (!w.junk.has(ctx)) w.junk.set(ctx, t); }
  };
  w.timer = setInterval(tick, 100); tick();
};

const REPORT = () => {
  const w = window.__tqWatch; if (!w) return null;
  clearInterval(w.timer);
  const end = Math.round(performance.now() - w.t0), out = { flicker: [], jump: [], blank: [], junk: [], twice: [], stall: [] };
  // ...the same label coming and going is one thing flickering, whichever element drew it each time
  const byLabel = new Map();
  for (const s of w.seen.values()) byLabel.set(s.label, [...(byLabel.get(s.label) || []), ...s.spans]);
  for (const [k, spans] of byLabel) {
    const sp = spans.sort((a, b) => a[0] - b[0]), shut = sp.filter(([, b]) => b < end - 200);
    if (sp.length > 2 || shut.some(([a, b]) => b - a < 1500 && a > 300)) out.flicker.push({ what: k, spans: sp.slice(0, 6) });
  }
  for (const s of w.seen.values()) for (let i = 1; i < s.tops.length; i++) {
    const [ta, ya] = s.tops[i - 1], [tb, yb] = s.tops[i];
    if (Math.abs(yb - ya) > 24 && tb - ta > 300 && Math.abs(tb - w.scrolledAt) > 800) { out.jump.push({ what: s.label, at: tb, from: ya, to: yb }); break; }
  }
  for (let i = 1; i < w.blank.length; i++) if (w.blank[i] - w.blank[i - 1] <= 150 && !out.blank.includes(w.blank[i - 1])) out.blank.push(w.blank[i - 1]);
  out.junk = [...w.junk].map(([ctx, t]) => ({ at: t, ctx }));
  out.twice = [...w.twice].map(([what, n]) => ({ what, n }));
  out.stall = w.stalls.filter(([a, b]) => b - a > 400).map(([a, b]) => ({ at: a, ms: b - a }));
  delete window.__tqWatch;
  return out;
};

// watch(page) at a step's start; `await stop()` at its end -> the findings, [] of each kind when the step looked right
export async function watch(page) {
  await page.evaluate(SAMPLER);
  return { stop: async () => (await page.evaluate(REPORT)) || { flicker: [], jump: [], blank: [], junk: [], twice: [], stall: [] } };
}
export const clean = (f) => !Object.values(f).some((v) => v.length);
export const said = (f) => Object.entries(f).filter(([, v]) => v.length).map(([k, v]) => `${k}: ${v.slice(0, 4).map((x) => typeof x === "number" ? `${x}ms` : JSON.stringify(x)).join("; ")}`).join("\n");
