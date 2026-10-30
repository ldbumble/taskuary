// The Amazon card's API dots: one Login-with-Amazon app can hold seller roles, Amazon Business roles or both, and the
// API it has no role for answers 403. The card shows a dot per API; Test fills the ones that answered, and the owner
// can tick them too (the owner, 2026-10-30: "maybe make little fillable dots which api you have access to").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (name) => readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");
const cv = read("ConnectorsView.jsx");
const fn = (name) => { const at = cv.indexOf(`function ${name}(`); return cv.slice(at, cv.indexOf("\nfunction ", at + 10)); };

test("the Amazon card names both APIs as dots, in the server's keys", () => {
  assert.match(cv, /apis: \[\["sp", "Seller reports \(SP-API\)"\], \["business", "Amazon Business reconciliation"\]\]/);
  const dd = fn("DataDetail");
  assert.match(dd, /\{meta\.apis && <ApiDots apis=\{meta\.apis\} cfg=\{cfg\} setCfg=\{setCfg\} \/>\}/);
});

test("a dot is a checkbox the owner can tick, saved with the card's config", () => {
  const dots = fn("ApiDots");
  assert.match(dots, /role="checkbox" aria-checked=\{on\.includes\(k\)\}/);
  assert.match(dots, /setCfg\(\{ \.\.\.cfg, apis: /);
});

test("Test fills the dots from what answered, without waiting for a reload", () => {
  const dd = fn("DataDetail");
  assert.match(dd, /if \(Array\.isArray\(t\?\.apis\)\) setCfg\(\(c\) => \(\{ \.\.\.c, apis: t\.apis \}\)\);/);
});

test("Amazon Business purchases is a report on the Amazon card", () => {
  const rv = read("ReportsView.jsx"), words = read("reportWords.js");
  assert.match(rv, /amazon_business_transactions: \[\["days back \(by feed date\)", "days"/);
  assert.match(rv, /amazon_business_transactions: "amazon_sp"/);
  assert.match(rv, /"amazon_marketplaces", "amazon_business_transactions", "metric"/);
  assert.match(words, /amazon_business_transactions: "Amazon \\u2014 Business purchases"/);
  assert.match(cv, /"amazon_marketplaces", "amazon_business_transactions"\],/);
});
