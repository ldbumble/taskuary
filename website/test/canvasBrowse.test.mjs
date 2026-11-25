import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

// Browsing Connections, Settings, Reports and Hub in the canvas (the canvas redesign, 2026-09-29): sections -> list ->
// one, Back returns; every step client state, one detail mounted at a time, and the open card is the next turn's subject.
test("each of the four views draws through the canvas's frame when it is handed `browse`", () => {
  for (const [file, sig] of [["ConnectorsView.jsx", "export default function ConnectorsView({ onNavigate, browse = null, browseState = {}, onBrowseState = null })"],
    ["ReportsView.jsx", "export default function ReportsView({ onOpenTask = null, browse = null, browseState = {}, onBrowseState = null })"],
    ["SettingsView.jsx", "export default function SettingsView({ onNavigate, browse = null, browseState = {}, onBrowseState = null, area = \"settings\" })"],
    ["HubView.jsx", "export default function HubView({ onOpenTask, browse = null, browseState = {}, onBrowseState = null })"]]) {
    const s = src(file);
    assert.ok(s.includes(sig), file);
    assert.match(s, /return browse\(\{/, `${file} returns its frame`);
  }
});

test("Back and a section chip change only the line's own state - no fetch", () => {
  const frame = src("CanvasBrowse.jsx");
  assert.doesNotMatch(frame, /data-tq-browse-back/, "no crumb: the bar's Back is the one");
  for (const file of ["ConnectorsView.jsx", "ReportsView.jsx", "SettingsView.jsx", "HubView.jsx"]) {
    const s = src(file), at = s.indexOf("return browse({");
    const block = s.slice(at, s.indexOf("\n    });", at));
    assert.doesNotMatch(block, /onBack:|noBack:/, file);
    assert.doesNotMatch(block.slice(block.indexOf("onSection:"), block.indexOf("onSection:") + 200), /api\.|loadPile/, file);
  }
});

test("the sidebar posts a browse card; only the newest is live, so one detail is mounted", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /onGo=\{\(tab, key\) => browse\(key\)\}/);
  assert.match(view, /return \[\.\.\.m, \{ id, role: "browse", area, state \}\];/);
  // ...and the area already open moves its own card rather than posting a second
  assert.match(view, /if \(live\?\.role === "browse" && live\.area === area\) return m\.map\(\(x\) => \(x\.id === live\.id \? \{ \.\.\.x, state, down: false \} : x\)\);/);
  assert.match(view, /const browsing = useMemo\(\(\) => liveBrowseId\(shown\), \[shown\]\);/); assert.match(process.getBuiltinModule("node:fs").readFileSync(new URL("../src/funnelPile.js", import.meta.url), "utf8"), /if \(shown\[i\]\.role === "browse"\) return shown\[i\]\.down \? null : shown\[i\]\.id;/);
  assert.match(src("CanvasBrowse.jsx"), /if \(!live\) return null;/);
  // ...and the item on the table folds to its line while a browse card is open below it
  assert.match(view, /const foldedNow = !!canvas && live && !!m\.card && \(foldsAs\(canvas\.folded, m\.card\.key\) \|\| !!canvas\.browsing\);/);
});

test("the card open in the canvas rides the next turn as its subject", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /open_card: openCardRef\.current/);
  assert.match(src("CanvasBrowse.jsx"), /useEffect\(\(\) => \{ if \(live\) onOpenCard\?\.\(detail \? openLabel : where\); \}/);
});

// the final review (2026-09-29): the tabs are gone, so what only they offered must be on the browse cards - "with today's
// controls" (the spec)
test("each browse card carries the controls its tab had", () => {
  assert.match(src("CanvasBrowse.jsx"), /\{!folded && tools\}/);   // ...stepping aside while a card is open
  // ...and a tab whose list is rows keeps them rows (the fix pass: report rows were crushed into a 240px card grid)
  assert.match(src("ReportsView.jsx"), /title: "Reports", wide: true,/);
  assert.match(src("HubView.jsx"), /title: "Hub", wide: true,/);
  const reports = src("ReportsView.jsx"), hub = src("HubView.jsx"), settings = src("SettingsView.jsx");
  const r = reports.slice(reports.indexOf("return browse({"));
  for (const want of ["Run due now", "<SetupWithAi", '"new-invoices"', '"new-agent"']) assert.ok(r.slice(0, 5000).includes(want), `Reports: ${want}`);
  const h = hub.slice(hub.indexOf("return browse({"));
  for (const want of ["Write one", "setSort", "setKind", "setRemoved", "<NewEntry"]) assert.ok(h.slice(0, 5000).includes(want), `Hub: ${want}`);
  const st = settings.slice(settings.indexOf("return browse({"));
  for (const want of ["<AssistantChanges", "Search settings"]) assert.ok(st.slice(0, 5000).includes(want), `Settings: ${want}`);
});

// the final review: "#report=999" opened an empty editor whose Save aimed at a missing id; "#connector=gone" said nothing
test("a link to a report or a connection that is gone says so, and opens nothing empty", () => {
  const reports = src("ReportsView.jsx"), conns = src("ConnectorsView.jsx");
  assert.match(reports, /const missing = typeof browseState\.open === "number" && !sources\.some\(\(x\) => x\.SourceId === browseState\.open\);/);
  assert.match(reports, /detail: browseState\.open != null && !missing \?/);
  assert.match(conns, /if \(!agents && !direct\) \{\s*setErr\(`That connection \(\$\{want\}\) is not here any more.*\s*setOpen\(null\); onBrowseState\?\.\(\{ \.\.\.browseState, open: null \}\); return;/,
    "...said over the list, not over the card that was open before (verify, 2026-10-19)");
  assert.match(conns, /note: err \|\| \(q \?/);
});

// the owner, 2026-09-29: "I don't see the rest of the docs ... we need sub settings to see all the files soul.md/counsel"
// - on the tab the rail listed every document; in the canvas Docs was one card showing only the first
test("Docs in the canvas lists every document the tab's rail did, and opens the one picked", () => {
  const s = src("SettingsView.jsx");
  const b = s.slice(s.indexOf("if (browse) {"), s.indexOf("return browse({", s.indexOf("if (browse) {")));
  assert.match(b, /docsTree\(docCat\)/, "the same tree the rail drew: documents, people, How it works");
  assert.match(s, /setDocSel\(e\.sel\.action \? \{ \.\.\.e\.sel, n: Date\.now\(\) \} : e\.sel\)/);
  assert.match(s, /<DocsView onCatalog=\{onCatalog\} catalogOnly \/>/, "the people pages are listed before any document is opened");
});

// the sidebar and "Run a report or workflow" hand no state: the page opened on three chips and no list (the UX walk, 2026-10-22)
test("Reports opened with no shelf named shows the reports", () => {
  const s = src("ReportsView.jsx");
  assert.match(s, /: sectionOr\(browseState\.section, \["reports", "dashboards", "workflows", "playbooks"\]\);/);
  assert.doesNotMatch(s, /browseState\.section \?\? null/);
});

// GOING TO A PAGE REPLACES THE VIEW (the owner's ruling, 2026-11-20): every page and task visited stayed over the one in front as a folded bar.
// A page or an item left behind is not drawn; only a LIVE browse card is, across the canvas's width.
test("a page or task left behind is not drawn; the canvas holds one view", async () => {
  const { pastView } = await import("../src/funnelPile.js");
  const shown = [{ id: "b1", role: "browse", area: "settings" }, { id: 2, role: "assistant", card: { kind: "task", key: "task:1" } },
    { id: "b3", role: "browse", area: "reports" }, { id: 4, role: "assistant", card: { kind: "task", key: "task:4" } },
    { id: 5, role: "assistant", proposal: { title: "a question" }, card: { kind: "proposal" } }, { id: 6, role: "user", text: "hi" }];
  const drawn = (o) => shown.filter((m, i) => !pastView(m, i, o)).map((m) => m.id);
  assert.deepEqual(drawn({ browsing: null, live: 3 }), [4, 5, 6], "the task in front, a waiting question and the chat's own lines");
  assert.deepEqual(drawn({ browsing: "b3", live: 3 }), ["b3", 5, 6], "a page open over a task replaces it");
  const view = src("AssistantView.jsx");
  assert.match(view, /if \(m\.role === "browse" && canvas\?\.browsing !== m\.id\) return null;/);
  assert.match(view, /inWin\.has\(m\.id\) \|\| gone\.has\(m\.id\) \? null :/);
  assert.match(view, /<div className="tq-browse-line tq-canvas-live" data-tq-browse-line=\{m\.area\}>/);
});

// THE DESIGN WALK (2026-11-20): About you, Settings and Connections opened on their chips over a blank page, and an open connection card sat
// under all 21 chips. A page opens on its first section; a card open collapses the picker to its lit chip, which is the list again.
test("a page opens on its first section", async () => {
  const { sectionOr } = await import("../src/browseSection.js");
  assert.equal(sectionOr(null, ["config", "policies"]), "config");
  assert.equal(sectionOr("policies", ["config", "policies"]), "policies");
  assert.equal(sectionOr("gone", ["config"]), "config");
});
