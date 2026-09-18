// ONE CATALOGUE, in taskuary/connectorcatalog.json: the working cards and the planned ones, each with
// a group, a line and the words that mean that system. This page reads the planned ones from it; the
// Assistant report reads the same file on the server to suggest what to connect (connectorcatalog.py,
// assistant.connect_ideas) - which it could not do while the roadmap lived only here (2026-09-18).
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
