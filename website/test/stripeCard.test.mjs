// The Stripe card: a data card for reports, dashboards and agents, never the rail (the owner, 2026-11-01: "just for
// reports/connectors for now"). Its reads are listed on the card, offered on the Reports tab under Corporate systems, and
// spend the card's key - one name for each of them in every place that lists them.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { oneOf } from "../src/connectorCatalog.js";

const read = (name) => readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");
const TYPES = ["stripe_balance", "stripe_balance_transactions", "stripe_charges", "stripe_payments", "stripe_payouts", "stripe_refunds",
  "stripe_disputes", "stripe_customers", "stripe_subscriptions", "stripe_invoices"];

test("the card is a Corporate system with a write-only key and no other field", () => {
  const cv = read("ConnectorsView.jsx");
  assert.match(cv, /dataCards\(\["intacct", "quickbooks", "zoho_invoice", "amazon_sp", "stripe"\]\)/);
  const card = cv.slice(cv.indexOf("  stripe: { title: \"Stripe\","), cv.indexOf("SETUP DONE", cv.indexOf("  stripe: { title")));
  assert.match(card, /fields: \[\], secretLabel: "restricted API key \(write-only\)/);
  for (const t of TYPES) assert.ok(card.includes(`"${t}"`), t);
  assert.match(read("logos.jsx"), /stripe: \(p\) => <T p=\{p\} bg="#635BFF"/);
  assert.equal(oneOf("stripe"), "Stripe account");
});

test("every read is a report with a label, a form and the Stripe card behind it", () => {
  const rv = read("ReportsView.jsx"), words = read("reportWords.js");
  for (const t of TYPES) {
    assert.match(rv, new RegExp(`\\n  ${t}: \\[`), `${t} has no form`);
    assert.match(words, new RegExp(`${t}: "Stripe \\\\u2014 `), `${t} has no label`);
  }
  assert.match(rv, /\.map\(\(t\) => \[`stripe_\$\{t\}`, "stripe"\]\)/);
  assert.match(rv, /"metric", "metric_check",\n    "stripe_balance",/);
});
