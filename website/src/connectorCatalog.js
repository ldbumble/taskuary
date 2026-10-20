// ONE CATALOGUE, in taskuary/connectorcatalog.json: the working cards and the planned ones, each with
// a group, a line and the words that mean that system. This page reads the planned ones from it; the
// Assistant report reads the same file on the server to suggest what to connect (connectorcatalog.py,
// assistant.connect_evidence) - which it could not do while the roadmap lived only here (2026-09-18).
// Keeping the roadmap in data rather than scattering one-off cards through ConnectorsView makes it
// harder for a category to quietly become empty.
import catalogue from "../../taskuary/connectorcatalog.json" with { type: "json" };

const grouped = {};
for (const c of catalogue.cards) {
  if (!c.planned) continue;
  (grouped[c.group] ||= []).push({ type: c.type, title: c.title, desc: c.desc });
}
export const PLANNED_CONNECTORS = Object.freeze(grouped);
export const CATALOGUE = Object.freeze(catalogue.cards);
export const plannedFor = (category) => PLANNED_CONNECTORS[category] || [];
// ONE CARD PER SYSTEM: a planned card is dropped where a card for the same type is already on the page - a live one anywhere, or
// the same planned type earlier. The server's planned list (reports.PLANNED) and this catalogue are kept apart, and PointClickCare
// drew twice: once by its catalogue name under Corporate systems, once as a bare "pointclickcare" under Everything else (2026-10-19 UI walk)
export const onceEach = (groups) => {
  const live = new Set(groups.flatMap((g) => g.cards.filter((c) => !c.planned).map((c) => c.type || c.channel))), seen = new Set();
  return groups.map((g) => ({ ...g, cards: g.cards.filter((c) => {
    const t = c.type || c.channel;
    if (!c.planned) return true;
    if (live.has(t) || seen.has(t)) return false;
    seen.add(t); return true; }) }));
};
