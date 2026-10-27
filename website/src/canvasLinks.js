// EVERY OLD LINK STILL LANDS (the canvas redesign, docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md):
// the tabs are gone, so a link that named one - a notification, the digest, a card's "change the judge", a bookmark -
// becomes a request for the assistant canvas: open this task's view, or post this browse card at this place.
// Pure, so test/canvasLinks.test.mjs can hold every link the app writes. `n` numbers the request; null = not ours.
const REPORT_BUCKETS = ["workflows", "new-invoices", "new-agent"];
// Settings' pages (SettingsView NAV): a link to any other opens the section list - "#settings=foo" crashed the app on
// every reload (the final review, 2026-09-29)
export const SETTINGS_PAGES = ["about", "docs", "config", "policies", "audit", "updates"];

export function canvasRequestFromHash(hash, n = 0) {
  const h = String(hash || "");
  let m;
  if ((m = /^#task=(\d+)/.exec(h))) return { kind: "task", tid: Number(m[1]), n };
  // a message by id - a card's "<name>'s message", a bell, the setup list, a digest line: ITS card on the table, the one the walk shows
  // for it (AssistantView.openMsgCard pulls msg:N). It opened a second view of the row - Summary / Message / Triage / Agent - that the
  // owner had taken for gone (2026-10-20: "it should not take you there regardless"); there is no other place a message opens.
  if ((m = /^#(?:msg|message)=(\d+)/.exec(h))) return { kind: "msg", mid: Number(m[1]), n };
  if (/^#new-task/.test(h)) return { kind: "new", n };
  if ((m = /^#report=([^&]+)/.exec(h))) {
    const v = decodeURIComponent(m[1]);
    // a draft New built (draftHandoff): its kind's shelf, the draft open
    const state = v === "new" ? { section: "reports", open: "new-report" }
      : v === "draft" ? { section: "reports", open: "draft" } : v === "draft-workflow" ? { section: "workflows", open: "draft" }
      // the dashboards' shelf: the list, a new one being described, or a draft New built (dashboards.py)
      : v === "dashboards" ? { section: "dashboards", open: null } : v === "new-dashboard" ? { section: "dashboards", open: "new-dashboard" }
      : v === "draft-dashboard" ? { section: "dashboards", open: "draft" }
      : v === "workflows" ? { section: "workflows", open: null } : v === "playbooks" ? { section: "playbooks", open: null }
        // ...and New playbook asked for (New's Playbook tab): the shelf, its dialog open - `newPb` numbers the ask, so a second one opens it again
        : v === "new-playbook" ? { section: "playbooks", open: null, newPb: n + 1 }
        : REPORT_BUCKETS.includes(v) ? { section: "workflows", open: v }
          : /^\d+$/.test(v) ? { section: "reports", open: Number(v), ...(/&fix=(\d+)/.test(h) ? { fix: Number(/&fix=(\d+)/.exec(h)[1]) } : {}) }
            : { section: "reports", open: null };
    return { kind: "browse", area: "reports", state, n };
  }
  // THE LINK CARRIES ITS TARGET (the 2026-10-19 UI walk): the connector rode in the hash, and its card read the hash once, when it
  // loaded - a link followed while Connections was already open opened nothing. `connector` is the card asked for; the view opens it
  if (/^#cli-agents$/.test(h)) return { kind: "browse", area: "connections", state: { section: null, open: null, connector: "cli-agents" }, n };
  // ...and &step=1: the Assistant brought it up to connect it - the card lights its first step (connectorStep.js)
  if ((m = /^#connector=([\w-]*)/.exec(h))) return { kind: "browse", area: "connections", state: { section: null, open: null, ...(m[1] ? { connector: m[1] } : {}),
    ...(m[1] && /&step=1\b/.test(h) ? { step: true } : {}) }, n };
  // one section of Connections, its cards open ("#connections=AI — voice": the crossed-out mic's Set up voice AI)
  if ((m = /^#connections=([^&]+)/.exec(h))) return { kind: "browse", area: "connections", state: { section: decodeURIComponent(m[1]), open: null }, n };
  if (/^#connections$/.test(h)) return { kind: "browse", area: "connections", state: { section: null, open: null }, n };
  if (/^#settings$/.test(h)) return { kind: "browse", area: "settings", state: { section: null, open: null }, n };
  // ...and a topic and an open post on it (#hub=<topic>&post=<id>): Back from an opened post left the Hub entirely - the address said
  // #hub whatever was open, so the post's opening was no step of history (2026-10-26)
  if ((m = /^#hub(?:=([^&]*))?(?:&post=(\d+))?$/.exec(h))) {
    const section = m[1] ? decodeURIComponent(m[1]) : "", open = m[2] ? Number(m[2]) : null;
    return { kind: "browse", area: "hub", state: section || open != null ? { section, open } : {}, n };
  }
  // one document, and the view to open it on (the opening screen's "learned this week" -> LEARNED.md, What changed)
  if ((m = /^#settings=docs&doc=(\w+)(?:&view=(\w+))?/.exec(h))) return { kind: "browse", area: "settings", state: { section: "docs", open: `d:${m[1]}`, ...(m[2] ? { view: m[2] } : {}) }, n };
  if ((m = /^#settings=([^&]*)(?:&group=([^&]*))?/.exec(h))) {
    const page = decodeURIComponent(m[1] || "config") || "config", group = m[2] ? decodeURIComponent(m[2]) : "";
    // Profiles is a section of its own (2107f0d2): its link opens that section's list. PLAYBOOKS LEFT SETTINGS for the Reports page
    // (the owner, 2026-10-21) - an old link to them still lands, on their new shelf
    if (page === "playbooks") return { kind: "browse", area: "reports", state: { section: "playbooks", open: null }, n };
    if (page === "profiles") return { kind: "browse", area: "settings", state: { section: page, open: null }, n };
    // ...and the old Verdicts & notes page is LEARNED.md now (the owner, 2026-10-27): its old link lands there
    if (page === "memory") return { kind: "browse", area: "settings", state: { section: "docs", open: "d:learned" }, n };
    if (!SETTINGS_PAGES.includes(page)) return { kind: "browse", area: "settings", state: { section: null, open: null }, n };
    // Docs is a shelf of files: its link opens the shelf, not whichever document happens to be first
    // ...and &key=<knob>: the one setting the Assistant brought the page up for (concierge._route), outlined and in view
    // ...and on a page of its own, its one button (#settings=updates&key=update: "update taskuary" brings Updates up with its button lit)
    const knob = (page !== "config" || group) && /&key=([^&]+)/.test(h) ? decodeURIComponent(/&key=([^&]+)/.exec(h)[1]) : "";
    return { kind: "browse", area: "settings", state: { section: page, open: page === "config" ? (group || null) : page === "docs" ? null : page, ...(knob ? { knob } : {}) }, n };
  }
  // a connector card's "new playbook for this connection" (#playbook=new:<type>): the Playbooks shelf, its New playbook asked for that card
  if ((m = /^#playbook=new:([\w-]+)/.exec(h))) return { kind: "browse", area: "reports", state: { section: "playbooks", open: null, newFor: m[1] }, n };
  // a playbook: Reports -> Playbooks, that one open in its editor (#playbook=new is a new one)
  if ((m = /^#playbook=([\w.-]+)/.exec(h))) return { kind: "browse", area: "reports", state: { section: "playbooks", open: `pb:${m[1]}` }, n };
  // "Manage profiles": the Profiles section, where every profile is a card beside Manage profiles and + New profile
  if (/^#profiles(?:$|=)/.test(h)) return { kind: "browse", area: "settings", state: { section: "profiles", open: null }, n };
  return null;
}

// THE ADDRESS OF A PLACE ON THE CANVAS - canvasRequestFromHash read backwards (the 2026-10-19 UI walk: the URL was never written, so
// the browser's Back left the app and a reload reopened a task the walk had moved past). What it cannot name - an open document on
// the Profiles shelf, a guide card - is written as the section it sits in; reading the address back lands there.
const enc = encodeURIComponent;
export function hashFor(area, s = {}) {
  s = s || {};
  if (area === "new") return "#new-task";
  if (area === "hub") return `#hub${s.section ? `=${enc(s.section)}` : ""}${s.open != null && /^\d+$/.test(String(s.open)) ? `${s.section ? "" : "="}&post=${s.open}` : ""}`;
  if (area === "connections") return s.connector === "cli-agents" ? "#cli-agents" : s.connector ? `#connector=${s.connector}`
    : s.section ? `#connections=${enc(s.section)}` : "#connections";
  if (area === "settings") {
    const p = s.section;
    if (!p) return "#settings";
    if (p === "docs") return /^d:\w+$/.test(String(s.open || "")) ? `#settings=docs&doc=${s.open.slice(2)}${s.view ? `&view=${s.view}` : ""}` : "#settings=docs";
    if (p === "config") return s.open ? `#settings=config&group=${enc(s.open)}${s.knob ? `&key=${enc(s.knob)}` : ""}` : "#settings=config";
    return `#settings=${p}${s.knob ? `&key=${enc(s.knob)}` : ""}`;
  }
  if (area === "reports") {
    if (s.section === "workflows") return s.open === "draft" ? "#report=draft-workflow" : REPORT_BUCKETS.includes(s.open) ? `#report=${s.open}` : "#report=workflows";
    if (s.section === "playbooks") return /^pb:[\w.-]+$/.test(String(s.open || "")) ? `#playbook=${s.open.slice(3)}` : "#report=playbooks";
    if (s.section === "dashboards") return typeof s.open === "number" ? `#report=${s.open}` : s.open === "draft" ? "#report=draft-dashboard"
      : s.open === "new-dashboard" ? "#report=new-dashboard" : "#report=dashboards";
    // ...a run's Fix with AI (&fix=) is an act the link asks for once, not a place: Back to it must not ask again
    return typeof s.open === "number" ? `#report=${s.open}` : s.open === "new-report" ? "#report=new"
      : s.open === "draft" ? "#report=draft" : "#report=reports";
  }
  return "";
}
// the one place an address names - "#connector=" and "#connections" are both the Connections landing, "#playbook=x" is Playbooks -
// so two spellings of the same place are never two steps of history; "" for an address that is no place of the canvas
// ...and the Board, the one full-screen view, by its own address (BOARD): no canvas request, so nothing else reads it as a page
export const BOARD = "#board";
export function placeOf(hash) {
  if (String(hash || "").trim() === BOARD) return BOARD;
  const r = canvasRequestFromHash(hash);
  return !r ? "" : r.kind === "task" ? `#task=${r.tid}` : r.kind === "msg" ? `#msg=${r.mid}` : r.kind === "new" ? "#new-task" : hashFor(r.area, r.state);
}
