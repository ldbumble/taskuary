// Downloads are the number the stats page exists for (the owner, 2026-10-14: "why does this not say how many people
// hit the download button, that's the most important number... it should be on top"). The landing page counts each
// Taskuary.exe click as cta/download. And the page is a dashboard in plain words (2026-10-15: "I have no idea what any of
// the data means right now").
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const page = fs.readFileSync(new URL("../../site/stats.html", import.meta.url), "utf8");

test("downloads lead, in the band above every other number, read from the cta/download events", () => {
  const band = page.indexOf(`'<section class="band">`);
  assert.ok(band > -1 && band < page.indexOf(`'<div class="kpis">'`));
  assert.match(page.slice(band, band + 200), /Downloads/);
  assert.match(page, /var downloads = what\(d, 'cta', 'download'\)/);
  assert.match(page, /x\.Kind === kind && \(name == null \|\| x\.What === name\)/);
});

test("every landing-page button is its own line, never folded into one 'pressed a button'", () => {
  assert.doesNotMatch(page, /pressed any button on the landing page/);
  for (const line of ["Clicked Try the demo", "Looked at the source", "Downloaded"]) assert.ok(page.includes(line), line);
});

test("the dashboard speaks plainly: no collector words as labels", () => {
  // 'row', 'verdict' and 'dwell' are what the collector calls them; the owner reads tasks opened, buttons pressed, time stayed
  for (const label of ["Opened a task", "Pressed a button in the app", "How long people stayed", "Where visitors come from"])
    assert.ok(page.includes(label), label);
  assert.doesNotMatch(page, /<h2>What they did<\/h2>|<h2>Which ones<\/h2>/);
});

test("visitors are split by the door they came in, so the site's count and the total never read as two answers", () => {
  assert.match(page, /How visitors came in/);
  for (const door of ["Only the site", "The site, then the demo", "Straight to the demo"]) assert.ok(page.includes(door), door);
  assert.match(page, /var visitors = d\.paths \? sum\(d\.paths/);
  assert.doesNotMatch(page, /From visit to download/);             // not a funnel: each next step is its own choice
});

test("the landing page counts a visit once, under the demo's own tab id", () => {
  const landing = fs.readFileSync(new URL("../../site/index.html", import.meta.url), "utf8");
  assert.equal((landing.match(/track\('open', 'landing'\)|send\('open', 'landing'\)/g) || []).length, 1);
  assert.match(landing, /KEY = 'tq_demo_sid'/);
  assert.doesNotMatch(landing, /tq_site_sid/);
});
