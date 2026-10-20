import { test } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { bandsOf, fyiTail, pileRows } from "../src/funnelPile.js";
import { summarize, gistOf } from "../src/walkSummary.js";

// the fields the server folds a held-back FYI row into (taskuary/funnel.py TAIL_FIELDS), read from the server's own file
const FIELDS = JSON.parse(readFileSync(fileURLToPath(new URL("../../taskuary/funnel.py", import.meta.url)), "utf8")
  .match(/^TAIL_FIELDS = \(([^)]*)\)/m)[1].replace(/'/g, '"').replace(/,\s*$/, "").replace(/^/, "[").concat("]"));
const people = ["Erin Blake", "Gail Moreno", "Paula Vance", "Ray Colton", "Marcus Reed", "Omar Keller"];
const fyi = (n) => ({ key: `msg:${n}`, lane: "fyi", order_band: 4, kind: "email", title: n % 7 ? `Status note ${n}` : "Weekly digest",
  who: people[n % people.length], shows: { who: people[n % people.length], state: "fyi" }, ref: "", tid: null,
  when: `2026-10-${String(1 + (n % 20)).padStart(2, "0")} 09:00:00`, category: n % 3 ? "info" : "promo", status: "new", channel: n % 4 ? "email" : "teams" });
const whole = { items: [{ key: "task:1", lane: "yours", order_band: 2, kind: "todo", title: "Sign the ledger close", who: "Alex Doyle" },
  ...Array.from({ length: 120 }, (_, n) => fyi(n + 10))] };
// the page's view of the same rail: the first 20 FYI whole, the rest folded the way funnel.page_fyi folds them
const paged = { items: whole.items.slice(0, 21), fyi_tail: { fields: FIELDS, lane: "fyi", order_band: 4,
  rows: whole.items.slice(21).map((i) => FIELDS.map((f) => (f === "shows_who" ? i.shows?.who : i[f]) ?? null)) } };

test("the FYI tail is counted as the rows it stands for", () => {
  assert.equal(fyiTail(paged).length, 100);
  assert.equal(pileRows(paged).length, whole.items.length);
  assert.deepEqual(pileRows(paged).map((i) => i.key), whole.items.map((i) => i.key));
  const view = (s) => ({ n: s.n, lead: s.lead, groups: s.groups.map((g) => [g.key, g.n, g.you, gistOf(g, 2), g.rows.slice(0, 6).map((r) => [r.key, r.count || 1])]) });
  assert.deepEqual(view(summarize(pileRows(paged))), view(summarize(whole.items)));
  assert.deepEqual(bandsOf(pileRows(paged)).map((b) => [b.level, b.items.length]), bandsOf(whole.items).map((b) => [b.level, b.items.length]));
});

test("a rail with no tail is its rows, and the same rows every time", () => {
  assert.equal(pileRows(whole), whole.items);
  assert.deepEqual(pileRows(null), []);
  assert.equal(fyiTail(paged), fyiTail(paged));                  // expanded once per answer, not on every render
});

test("whatever DRAWS reads the rows; whatever COUNTS reads the tail too", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
  assert.match(view, /<em>\{rows\.length \+ extra\}<\/em>/);                 // the heading says the whole band
  assert.match(view, /const hidden = rows\.length - shown\.length \+ extra;/); // ...and "N more fyi" the rest of it
  assert.match(view, /summarize\(railPile \? pileRows\(railPile\) : items\)/);
  assert.match(view, /fyi: fyiWant\.current/);                               // every read the page makes asks for its page
});
