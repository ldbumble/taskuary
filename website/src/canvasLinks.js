// EVERY OLD LINK STILL LANDS (the canvas redesign, docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md):
// the tabs are gone, so a link that named one - a notification, the digest, a card's "change the judge", a bookmark -
// becomes a request for the assistant canvas: open this task's view, or post this browse card at this place.
// Pure, so test/canvasLinks.test.mjs can hold every link the app writes. `n` numbers the request; null = not ours.
const REPORT_BUCKETS = ["workflows", "new-invoices", "new-agent"];
// Settings' pages (SettingsView NAV): a link to any other opens the section list - "#settings=foo" crashed the app on
// every reload (the final review, 2026-09-29)
export const SETTINGS_PAGES = ["about", "docs", "config", "policies", "memory", "audit", "updates"];

export function canvasRequestFromHash(hash, n = 0) {
  const h = String(hash || "");
  let m;
  if ((m = /^#task=(\d+)/.exec(h))) return { kind: "task", tid: Number(m[1]), n };
  if (/^#new-task/.test(h)) return { kind: "new", n };
  if ((m = /^#report=([^&]+)/.exec(h))) {
    const v = decodeURIComponent(m[1]);
    const state = v === "new" ? { section: "reports", open: "new-report" }
      : v === "workflows" ? { section: "workflows", open: null }
        : REPORT_BUCKETS.includes(v) ? { section: "workflows", open: v }
          : /^\d+$/.test(v) ? { section: "reports", open: Number(v) } : { section: "reports", open: null };
    return { kind: "browse", area: "reports", state, n };
  }
  // the connector's own card reads the hash when it loads (ConnectorsView), so the link opens its detail in place
  if (/^#(?:connector=|cli-agents)/.test(h)) return { kind: "browse", area: "connections", state: {}, n };
  if ((m = /^#settings=([^&]*)(?:&group=([^&]*))?/.exec(h))) {
    const page = decodeURIComponent(m[1] || "config") || "config", group = m[2] ? decodeURIComponent(m[2]) : "";
    if (!SETTINGS_PAGES.includes(page)) return { kind: "browse", area: "settings", state: { section: null, open: null }, n };
    // Docs is a shelf of files: its link opens the shelf, not whichever document happens to be first
    return { kind: "browse", area: "settings", state: { section: page, open: page === "config" ? (group || null) : page === "docs" ? null : page }, n };
  }
  // a playbook: the words live in Settings -> Playbooks, edited in the Docs page (DocsView reads the hash itself and opens it)
  if (/^#playbook=/.test(h)) return { kind: "browse", area: "settings", state: { section: "playbooks", open: "docs" }, n };
  // "Manage profiles": the Profiles section, where every profile is a card beside Manage profiles and + New profile
  if (/^#profiles(?:$|=)/.test(h)) return { kind: "browse", area: "settings", state: { section: "profiles", open: null }, n };
  return null;
}
