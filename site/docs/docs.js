// The rail's behaviour, which is the Settings page's: collapse a page's sections, mark the section
// you are actually looking at, and search everything. Every rail entry is a real <a href>, so the
// docs work with this file absent - only the highlight and the search need it.
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const TOP = 74;   // how far under the sticky bar a heading has to land to read as "at the top"

  /* the chevrons: toggle just that entry, and never navigate */
  $$(".chev").forEach((b) => b.addEventListener("click", (e) => {
    e.preventDefault(); e.stopPropagation();
    const secs = b.parentElement.querySelector(".secs"), open = b.getAttribute("aria-expanded") === "true";
    b.setAttribute("aria-expanded", String(!open));
    b.setAttribute("aria-label", `${open ? "Show" : "Hide"} sections`);
    secs.hidden = open;
  }));

  /* WHICH SECTION YOU ARE IN: the last heading that has passed under the bar. Without it the rail
     marks the last thing you clicked and then quietly lies as you scroll past it. The final
     section is usually too short to reach the bar, so at the foot of the page it wins outright. */
  const links = $$(".entry.on .secs .sec");
  const heads = links.map((a) => document.getElementById(a.dataset.sec)).filter(Boolean);
  if (heads.length) {
    let queued = false;
    const measure = () => {
      queued = false;
      let cur = 0;
      heads.forEach((h, i) => { if (h.getBoundingClientRect().top <= TOP + 8) cur = i; });
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) cur = heads.length - 1;
      links.forEach((a, i) => a.classList.toggle("here", i === cur));
    };
    measure();
    addEventListener("scroll", () => { if (!queued) { queued = true; requestAnimationFrame(measure); } }, { passive: true });
    addEventListener("resize", measure, { passive: true });
  }

  /* search: one index, built beside the pages. A hit reads the way the rail reads
     ("Connections → Sources") and lands on the same anchor. */
  const box = $("#q"), out = $("#results"), entries = $("#entries");
  if (!box || !out || !entries) return;
  let index = null, loading = null;
  const load = () => (loading ||= fetch("./search.json").then((r) => r.json()).then((j) => (index = j)).catch(() => (index = [])));
  box.addEventListener("focus", load, { once: true });

  const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  const render = (q) => {
    const needle = q.trim().toLowerCase();
    if (!needle) { out.hidden = true; entries.hidden = false; out.innerHTML = ""; return; }
    entries.hidden = true; out.hidden = false;
    if (!index) { out.innerHTML = '<p class="none">Searching…</p>'; return; }
    const seen = new Set(), hits = [];
    for (const e of index) {
      if (hits.length >= 12) break;
      const inTitle = e.t && e.t.toLowerCase().includes(needle);
      if (!inTitle && !(e.x || "").toLowerCase().includes(needle)) continue;
      const key = e.u + (inTitle ? e.t : "");
      if (seen.has(key)) continue;
      seen.add(key);
      hits.push({ ...e, rank: inTitle ? 0 : 1 });
    }
    hits.sort((a, b) => a.rank - b.rank);
    out.innerHTML = hits.length
      ? hits.map((h) => `<a href="${esc(h.u)}"><span class="crumb">${esc(h.c)}</span>${esc(h.t || h.c)}</a>`).join("")
      : '<p class="none">Nothing here says that.</p>';
  };
  box.addEventListener("input", () => { load().then(() => render(box.value)); render(box.value); });
  box.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { box.value = ""; render(""); box.blur(); }
    if (e.key === "Enter") { const a = out.querySelector("a"); if (a) a.click(); }
  });
  addEventListener("keydown", (e) => {
    if (e.key === "/" && document.activeElement !== box && !/^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) {
      e.preventDefault(); box.focus();
    }
  });
})();
