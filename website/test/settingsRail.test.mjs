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


test("Configuration is one page, not a strip of tabs", () => {
  assert.ok(!/FilterPills/.test(src), "the pill strip is gone - it was the thing that ran off the edge");
  assert.ok(!/cfgTab/.test(src), "and so is the state that remembered which tab you were on");
  // (Notifications lost its panel with the notify pushes, 2026-10-02 - its sound and desktop switches are plain rows)
  // (the phone's panel moved to Settings > Phone & chats with its knobs, 2026-11-06)
  assert.ok(src.includes(`"How mail is sorted":`), "How mail is sorted still gets its panel above its knobs");
  assert.match(src, /assistant=\{<><PhoneDoorways [^>]*\/>\{rowsOf\(PHONE_GROUP\)\.map\(knobRow\)\}/, "the phone's panel sits above its knobs on Phone & chats");
  assert.ok(schema.groups.length > 8, "the point of the change: there are a lot of them, and more coming");
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
  // it contributes its page heading to the scroll-spy and nothing else - its entries are objects,
  // not heading names, and there is nothing under them to measure.
  assert.match(src, /\.\.\.\(k === "docs" \? \[\] : sectionsOf\(k\)\.map\(\(n\) => \(\{ page: k, section: n, id: secId\(k, n\) \}\)\)\)/,
    "the scroll-spy skips the entries that have nothing to scroll to");
});
