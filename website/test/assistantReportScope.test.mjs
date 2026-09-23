import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("source-backed Assistant reports explain and display their isolated scope", () => {
  const reports = read("ReportsView.jsx");
  const feed = read("FeedView.jsx");
  assert.match(reports, /This report reads only those sources; the general Advisor and Morning digest are separate/);
  // Taskuary's own cards sit in that same list since 2026-09-20, so the scope sentence names the list, not the inbox
  assert.match(reports, /This check reads only the sources below/);
  assert.match(reports, /rv\?\.scope === "sources"/);
  assert.match(feed, /rv\.scope === "sources"/);
  assert.match(reports, /configured data source/);
  assert.match(feed, /configured data source/);
});
