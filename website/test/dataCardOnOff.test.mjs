import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const cv = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");
const fn = (name) => { const at = cv.indexOf(`function ${name}(`); return cv.slice(at, cv.indexOf("\nfunction ", at + 10)); };

// #242: a data card's Save and "Use it" sent Active: true, so editing a card the owner had switched off turned it back on.
// Save saves the settings; the card's own switch is what turns it on - and since Save was the only way a data card ever
// came on, the switch sits on the Connection tab right under Save, so a first setup is not stranded off.
test("a data card's Save and Use it save settings, never switch the card on", () => {
  const dd = fn("DataDetail");
  assert.doesNotMatch(dd, /Active: true/, "no post of DataDetail's turns the card on by itself");
  assert.match(dd, /const body = \{ ConnectorId: conn\.ConnectorId, ConfigJson: JSON\.stringify\(cfg\) \};/);
  assert.match(dd, /api\.post\("\/api\/connectors", \{ ConnectorId: conn\.ConnectorId, ConfigJson: JSON\.stringify\(next\) \}\)/);
});

test("a data card has its own on/off switch, beside Save, saved on the press like a channel card's (splitNow)", () => {
  const dd = fn("DataDetail");
  assert.match(dd, /const setActive = \(on\) => draft\.ctx\.stageConn\(\{ ConnectorId: conn\.ConnectorId, Active: on \}\);/);
  assert.match(dd, /<Switch data-tq-card-on="" checked=\{!!conn\.Active\} disabled=\{draft\.flipping\} onChange=\{\(e\) => setActive\(e\.target\.checked\)\} \/>/);
  // on the Connection tab, after the Save row - where the person who just saved is looking
  const tab = dd.slice(dd.indexOf('{tab === "Connection" && ('));
  assert.ok(tab.indexOf("data-tq-card-on") > tab.indexOf('"Save"}</Button>'), "the switch comes after Save");
  assert.ok(tab.indexOf("data-tq-card-on") < tab.indexOf("<CloudObjects"), "...on the Connection tab");
});
