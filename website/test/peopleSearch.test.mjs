// FINDING A PERSON BY WHAT YOU REMEMBER (the owner, 2026-10-27): the server's ranked people lead the box, the model is asked only after
// an empty or descriptive plain answer and once per query, and an older query's answer never sits over a newer one. Invented people.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { describes, forgetAi, personLine, runSearch, wantsAi, withFound } from "../src/peopleSearch.js";

const DYN = [{ to: "vhale@dynamo.example", name: "Victor Hale", company: "Dynamo Freight" }, { to: "lortiz@dynamo.example", name: "Lena Ortiz", org: "dynamo" }];
const tick = (ms) => new Promise((r) => setTimeout(r, ms));

test("the server's people lead, local matches it did not name follow, and a stale answer is not shown", () => {
  const local = [{ to: "lortiz@dynamo.example", name: "Lena Ortiz" }, { to: "dynamo-billing@vendor.example", name: "" }];
  const out = withFound(local, { q: "dynamo", rows: DYN, ai: false }, "dynamo");
  assert.deepEqual(out.map((o) => o.to), ["vhale@dynamo.example", "lortiz@dynamo.example", "dynamo-billing@vendor.example"]);
  assert.equal(out[0].hint, "Dynamo Freight"); assert.equal(out[1].hint, "dynamo");
  assert.equal(withFound(local, { q: "dyn", rows: DYN }, "dynamo"), local, "an older query's answer");
  assert.equal(withFound(local, { q: "", rows: [] }, ""), local);
});

test("the model is wanted for nothing found or a description, and its picks say so", () => {
  assert.ok(wantsAi("zebra", [])); assert.ok(!wantsAi("ze", []));
  assert.ok(wantsAi("the dynamo billing person", DYN)); assert.ok(!wantsAi("dynamo", DYN));
  assert.ok(describes("billing at dynamo")); assert.ok(!describes("gail moreno"));
  assert.equal(personLine({ company: "Dynamo Freight", ai: true }), "Dynamo Freight · suggested by AI");
});

test("one search per pause; the model after it, once per query; no model when the plain answer fits", async () => {
  forgetAi();
  const calls = [], got = [];
  const get = async (u, { params }) => { calls.push(params); return { data: params.ai ? { data: [DYN[1]], ai: true } : { data: [] } }; };
  let stop = runSearch(get, "billing lady", "email", (f) => got.push(f), { wait: 5, aiWait: 5 });
  await tick(60); stop();
  assert.deepEqual(calls.map((p) => !!p.ai), [false, true]);
  assert.deepEqual(got.at(-1), { q: "billing lady", rows: [DYN[1]], ai: true });
  stop = runSearch(get, "billing lady", "email", (f) => got.push(f), { wait: 5, aiWait: 5 });
  await tick(60); stop();
  assert.equal(calls.filter((p) => p.ai).length, 1, "the model is asked once for the same words");
  const plain = async (u, { params }) => { calls.push(params); return { data: { data: DYN } }; };
  stop = runSearch(plain, "dynamo", "email", () => {}, { wait: 5, aiWait: 5 }); await tick(60); stop();
  assert.equal(calls.filter((p) => p.ai).length, 1);
  // typing on cancels the pending search
  const n = calls.length; stop = runSearch(plain, "dyna", "email", () => {}, { wait: 20 }); stop(); await tick(40);
  assert.equal(calls.length, n);
});

test("To, Cc and Hand-off search the server; the chat pickers and the email lists do too", () => {
  const ui = fs.readFileSync(new URL("../src/ui.jsx", import.meta.url), "utf8");
  const sheet = fs.readFileSync(new URL("../src/NewSheet.jsx", import.meta.url), "utf8");
  const handoff = fs.readFileSync(new URL("../src/Handoff.jsx", import.meta.url), "utf8");
  assert.match(ui, /const found = usePeopleSearch\(value, channel\)/);
  assert.match(handoff, /<ContactPicker[^>]*channel=\{channel\}/);
  assert.match(sheet, /const found = usePeopleSearch\(typed, "email"\)/);
  assert.match(sheet, /const found = usePeopleSearch\(typed, channel\)/);
});
