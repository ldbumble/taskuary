import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

// Browsing Connections, Settings, Reports and Hub in the canvas (the canvas redesign, 2026-09-29): sections -> list ->
// one, Back returns; every step client state, one detail mounted at a time, and the open card is the next turn's subject.
test("each of the four views draws through the canvas's frame when it is handed `browse`", () => {
  for (const [file, sig] of [["ConnectorsView.jsx", "export default function ConnectorsView({ onNavigate, browse = null, browseState = {}, onBrowseState = null })"],
    ["ReportsView.jsx", "export default function ReportsView({ browse = null, browseState = {}, onBrowseState = null })"],
    ["SettingsView.jsx", "export default function SettingsView({ onNavigate, browse = null, browseState = {}, onBrowseState = null })"],
    ["HubView.jsx", "export default function HubView({ onOpenTask, browse = null, browseState = {}, onBrowseState = null })"]]) {
    const s = src(file);
    assert.ok(s.includes(sig), file);
    assert.match(s, /return browse\(\{/, `${file} returns its frame`);
  }
});

test("Back and a section chip change only the line's own state - no fetch", () => {
  const frame = src("CanvasBrowse.jsx");
  assert.match(frame, /data-tq-browse-back="" onClick=\{onBack\}/);
  for (const file of ["ConnectorsView.jsx", "ReportsView.jsx", "SettingsView.jsx", "HubView.jsx"]) {
    const s = src(file), at = s.indexOf("return browse({");
    const block = s.slice(at, s.indexOf("\n    });", at));
    assert.match(block, /onBack:/, file);
    assert.doesNotMatch(block.slice(block.indexOf("onSection:"), block.indexOf("onSection:") + 200), /api\.|loadPile/, file);
  }
});

test("the sidebar posts a browse card; only the newest is live, so one detail is mounted", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /onGo=\{\(tab, key\) => browse\(key\)\}/);
  assert.match(view, /setMsgs\(\(m\) => \[\.\.\.m, \{ id, role: "browse", area, state \}\]\)/);
  assert.match(view, /if \(shown\[i\]\.role === "browse"\) return shown\[i\]\.id;/);
  assert.match(src("CanvasBrowse.jsx"), /if \(!live\) return frame\(\{ title: AREA_TITLES\[area\] \}\);/);
  // ...and the item on the table folds to its line while a browse card is open below it
  assert.match(view, /const foldedNow = !!canvas && live && !!m\.card && \(canvas\.folded === m\.card\.key \|\| !!canvas\.browsing\);/);
});

test("the card open in the canvas rides the next turn as its subject", () => {
  const view = src("AssistantView.jsx");
  assert.match(view, /open_card: openCardRef\.current/);
  assert.match(src("CanvasBrowse.jsx"), /useEffect\(\(\) => \{ if \(live\) onOpenCard\?\.\(detail \? openLabel : null\); \}/);
});
