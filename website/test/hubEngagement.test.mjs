// The Hub is a forum: validated and discussed entries should look and sort like it. This guards
// the product-level defaults without coupling a test to MUI's generated DOM.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const hub = fs.readFileSync(path.join(process.cwd(), "src", "HubView.jsx"), "utf8");
const demo = fs.readFileSync(path.join(process.cwd(), "src", "demoApi.js"), "utf8");

test("the Hub opens on its most valuable entries", () => {
  assert.match(hub, /const \[sort, setSort\] = useState\("top"\)/);
  assert.match(hub, /<MenuItem value="top"[^>]*>most valuable<\/MenuItem>/);
});

test("every post names its vote score and exact comment count", () => {
  assert.match(hub, /const voteLabel =/);
  assert.match(hub, /\{commentCount\} comment\{commentCount === 1 \? "" : "s"\}/);
});

test("the demo uses discussion as the tie-breaker too", () => {
  assert.match(demo, /\(b\.Comments \|\| 0\) - \(a\.Comments \|\| 0\)/);
});
