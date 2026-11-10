// FINDING A PLACE IN SETTINGS BY ITS NAME OR BY WHAT IT HOLDS (the owner, 2026-11-10: "do not see agent permissions in settings just
// searched for it", "don't see the vault settings either for saved passwords. where is it?"). The search box the Settings list draws
// read only the knobs' own words, so a section was found by no word of its name, and what a section draws as a PANEL - the saved
// sign-ins, the tools that send - by no word at all. Both Settings searches ask this one function; the panels' words are
// settings_schema.json's `panels`, which the top search (search.py) and Connections' Saved sign-ins card read too.

// every word typed is somewhere in the text, in any order: "saved sign" finds "Saved sign-ins", "password vault" the vault
export const words = (q) => String(q || "").toLowerCase().split(/\s+/).filter(Boolean);
export const matches = (q, ...parts) => { const t = parts.join(" ").toLowerCase(), ws = words(q); return !!ws.length && ws.every((w) => t.includes(w)); };

// The places that answer `q`, sections and pages first: { key, label, crumb, page, section, knob? }. `sections` maps a page to the
// sections it stacks (a page with none is one place, found by its title); `pages` names them; `schema.panels` are the panels.
export const placeHits = (q, { schema, sections, pages }) => !words(q).length ? [] : [
  ...Object.entries(pages).flatMap(([pg, p]) => (sections[pg]?.length
    ? sections[pg].filter((n) => matches(q, n, p.title)).map((n) => ({ key: `s:${pg}:${n}`, label: n, crumb: `${p.title} → ${n}`, page: pg, section: n }))
    : matches(q, p.title) ? [{ key: `s:${pg}`, label: p.title, crumb: p.title, page: pg, section: "" }] : [])),
  // a panel sits in a Configuration section; the hit opens that section and scrolls to the panel (its wrapper carries its id as a knob)
  ...Object.entries(schema.panels || {}).filter(([, p]) => matches(q, p.title, p.group, p.words))
    .map(([k, p]) => ({ key: k, label: p.title, crumb: `${pages.config?.title || "Configuration"} → ${p.group}`, page: "config", section: p.group, knob: k })),
];
