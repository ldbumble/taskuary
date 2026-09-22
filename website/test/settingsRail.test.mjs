// THE RAIL IS THE MAP OF SETTINGS. Configuration used to be one page behind a strip of eleven
// pills, and eleven pills do not fit across a 980px page - "Display" was cut in half by the right
// edge, and the answer to "there will be more settings" was a strip that could hold fewer of them
// (the owner, 2026-09-18). So every group is a section of one scrolling page, the rail lists them
// under Configuration, and picking one scrolls to it. These tests pin the three things that have
// to agree: what the rail draws, what the page stamps an id on, and what search says the path is.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import schema from "../../taskuary/settings_schema.json" with { type: "json" };

const read = (f) => fs.readFileSync(path.join(process.cwd(), "src", f), "utf8");
const src = read("SettingsView.jsx"), about = read("AboutYou.jsx"), map = read("settingsMap.js");
const secNames = (name) => [...(new RegExp(`export const ${name} = \\[([^\\]]*)\\]`).exec(map) || [, ""])[1]
  .matchAll(/"([^"]+)"/g)].map((m) => m[1]);

test("a section's name, its anchor and its crumb come from one place", () => {
  assert.match(map, /export const secId = /, "one function builds the id both sides use");
  assert.match(src, /const SECTIONS = \{ about: ABOUT_SECTIONS, config: GROUPS, audit: AUDIT_SECTIONS \};/,
    "Configuration's sections ARE the schema's groups - adding a group must not mean editing a rail by hand");
  assert.ok(secNames("ABOUT_SECTIONS").length === 3 && secNames("AUDIT_SECTIONS").length === 2);
});

test("every section the rail offers is a heading the page actually stamps", () => {
  // A rail entry whose anchor nobody renders scrolls nowhere and highlights nothing.
  assert.match(src, /const cfgGroups = GROUPS\.filter\(\(g\) => panels\[g\] \|\| rowsOf\(g\)\.length\);/,
    "Configuration draws every group that has something in it, in the schema's order");
  assert.match(src, /\{cfgGroups\.map\(\(g\) => \(/);
  assert.match(src, /<SectionHead page="config" name=\{g\} \/>/);
  assert.match(src, /<SectionHead page="audit" name=\{AUDIT_SECTIONS\[0\]\} \/>/);
  assert.match(src, /<SectionHead page="audit" name=\{AUDIT_SECTIONS\[1\]\} \/>/);
  assert.equal((about.match(/id=\{secId\("about", /g) || []).length, secNames("ABOUT_SECTIONS").length,
    "About you stamps one id per section it declares");
});

test("Configuration is one page, not a strip of tabs", () => {
  assert.ok(!/FilterPills/.test(src), "the pill strip is gone - it was the thing that ran off the edge");
  assert.ok(!/cfgTab/.test(src), "and so is the state that remembered which tab you were on");
  for (const g of ["Triage & agents", "Notifications", "Assistant on your phone"]) {
    assert.ok(src.includes(`"${g}":`), `${g} still gets its panel above its knobs`);
  }
  assert.ok(schema.groups.length > 8, "the point of the change: there are a lot of them, and more coming");
});

test("picking a section scrolls to it - it does not swap the page out", () => {
  const at = src.indexOf("const goTo = useCallback");
  assert.notEqual(at, -1);
  const go = src.slice(at, at + 420);
  assert.ok(go.includes("setJump(secId(pg, section))"), "a section asks for its anchor");
  assert.ok(go.includes('window.scrollTo({ top: 0'), "and a bare page goes back to the top");
  // the rows arrive from the server after the page renders and push the anchor back down, so the
  // scroll is corrected until the heading stops moving
  assert.match(src, /const at = sectionOffset\(jump\);/);
  assert.match(src, /if \(settled > 2 \|\| \+\+tries > 40\) \{ setJump\(""\); return; \}/,
    "the scroll must survive a page whose content has not finished loading");
  assert.match(map, /landed: Math\.abs\(off\) < 4 \|\| \(atEnd && off > 0\)/,
    "a section at the bottom of the page cannot reach the top bar - that counts as landed");
});

test("the rail's sections collapse, and each page remembers", () => {
  assert.match(src, /const \[open, setOpen\] = useState\(\{ \[NAV\[0\]\]: true \}\)/,
    "the page you land on is open; the rest are closed until you ask");
  assert.match(src, /setOpen\(\(o\) => \(\{ \.\.\.o, \[k\]: !shown \}\)\)/, "the chevron toggles just that entry");
  assert.match(src, /e\.stopPropagation\(\)/, "and toggling must not also navigate");
});

test("the rail says which section you are actually looking at", () => {
  // Without this it would highlight the last thing you clicked and then lie as you scrolled past.
  assert.match(src, /el\.getBoundingClientRect\(\)\.top <= SCROLL_TOP \+ 8/);
  assert.match(src, /window\.addEventListener\("scroll", onScroll, \{ passive: true \}\)/);
  assert.match(src, /return \(\) => window\.removeEventListener\("scroll", onScroll\)/, "and lets go of it");
  assert.match(src, /if \(window\.innerHeight \+ window\.scrollY >= document\.documentElement\.scrollHeight - 2\) cur = names\[names\.length - 1\];/,
    "the last section is short enough that its heading never reaches the bar - at the foot of the page it still wins");
});

test("a search hit reads like the rail and lands on the same anchor", () => {
  assert.match(src, /crumb: `Configuration → \$\{meta\(s\.Name\)\.group\}`/, "a knob says which section holds it");
  assert.match(src, /go: \(\) => \{ setQ\(""\); onJump\("config", meta\(s\.Name\)\.group\); \}/,
    "and clicking it scrolls there, rather than dropping you at the top of the page");
  assert.match(src, /crumb: `\$\{PAGES\[pg\]\.title\} → \$\{n\}`/, "the sections themselves are searchable");
  assert.ok(!/crumb: "Agent memory"/.test(src), "one vocabulary: the crumb is the rail's own name for the page");
});

test("one hash link opens a page and a section, and is consumed once", () => {
  // Every in-app link to a knob is #settings=config&group=<encoded group> (ReportsView's judge,
  // the walk, setup.py, the assistant's health card). They must keep working.
  assert.match(src, /const m = \/settings=\(\[\\w-\]\+\)\/\.exec\(hash\)/);
  assert.match(src, /const g = \/group=\(\[\^&\]\+\)\/\.exec\(hash\)/);
  assert.match(src, /goTo\(m\[1\], \(SECTIONS\[m\[1\]\] \|\| \[\]\)\.includes\(want\) \? want : ""\)/,
    "a group name that is not a section of that page must not send the page hunting for it");
  assert.equal((src.match(/window\.history\.replaceState/g) || []).length, 1,
    "the hash is consumed in exactly one place - two effects raced and the child won");
});

test("the rail offers only the sections the page will actually draw", () => {
  // "Other" is a group with no knobs of its own: it catches a stray key, and on an install with
  // no stray key Configuration does not draw it. A rail entry for it would scroll nowhere.
  assert.equal(schema.knobs && Object.values(schema.knobs).filter((k) => k.group === "Other").length, 0,
    "Other is empty in the schema by design - it is a catch-all, not a page");
  assert.match(src, /useEffect\(\(\) => \{ onSections\(cfgKey \? cfgKey\.split\("\|"\) : \[\]\); \}, \[cfgKey, onSections\]\);/,
    "the page tells the rail what it drew");
  assert.match(src, /const sectionsOf = useCallback\(\(k\) => \(k === "config" && cfgSecs\)/,
    "the rail, the scroll-spy and the search crumbs all read one list");
  assert.match(src, /\|\| \(k === "docs" \? docsTree\(docCat\) : null\) \|\| SECTIONS\[k\] \|\| \[\], \[cfgSecs, docCat\]\);/,
    "...and Docs contributes its tree to that same list");
  // Docs is the one page whose entries SWITCH the document instead of scrolling to a heading, so
  // it is the one page the scroll-spy must sit out - it has no headings to measure.
  assert.match(src, /const names = q \|\| page === "docs" \? \[\] : sectionsOf\(page\);/,
    "the scroll-spy skips the page that has nothing to scroll to");
});
