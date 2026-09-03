import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("source-backed Assistant reports explain and display their isolated scope", () => {
  const reports = read("ReportsView.jsx");
  const feed = read("FeedView.jsx");
  assert.match(reports, /This report reads only those sources; the general Assistant and Morning digest are separate/);
  assert.match(reports, /not your inbox, calendar, tasks, Morning digest, or another Assistant report/);
  assert.match(reports, /rv\?\.scope === "sources"/);
  assert.match(feed, /rv\.scope === "sources"/);
  assert.match(reports, /configured data source/);
  assert.match(feed, /configured data source/);
});
