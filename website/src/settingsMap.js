// THE MAP OF SETTINGS, IN ONE PLACE. The rail draws these as sub-entries under their page, the
// page stamps the same id on the matching heading, and a search hit reads the same path back to
// you ("Configuration → Triage & agents"). ONE DOCUMENT, scrolled to - not a second row of tabs,
// which is what ran off the right edge once there were eleven of them (the owner, 2026-09-18),
// and not seven documents either: scrolling off the end of Configuration used to stop dead
// instead of carrying on into Routing policies (the owner, 2026-09-22). Configuration's sections
// are the schema's groups, so adding a group there adds a rail entry, an anchor and a search
// crumb at once.
export const ABOUT_SECTIONS = ["You", "Per channel", "What the agents are told"];
export const AUDIT_SECTIONS = ["Verify the chain", "History"];
export const secId = (page, name) => `set-${page}-${String(name).toLowerCase().replace(/[^a-z0-9]+/g, "-")}`;
// A page's own heading. Every rail entry has one now, because every rail entry is a place you
// scroll to rather than a page that replaces the one before it.
export const pageId = (page) => `set-page-${page}`;

// How far under the sticky top bar a heading has to land to read as "at the top".
export const SCROLL_TOP = 74;
export const scrollToSection = (id, behavior = "smooth") => {
  const el = typeof document === "undefined" ? null : document.getElementById(id);
  if (!el) return false;
  window.scrollTo({ top: el.getBoundingClientRect().top + window.scrollY - SCROLL_TOP, behavior });
  return true;
};
// How far the heading still is from where it should sit, and whether the page has any room left
// to close that gap. A section near the bottom cannot reach the top bar, and that is landed too.
export const sectionOffset = (id) => {
  const el = typeof document === "undefined" ? null : document.getElementById(id);
  if (!el) return null;
  const off = el.getBoundingClientRect().top - SCROLL_TOP;
  const atEnd = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2;
  return { off, landed: Math.abs(off) < 4 || (atEnd && off > 0) };
};
