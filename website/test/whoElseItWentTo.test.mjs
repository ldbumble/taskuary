// WHOM A MAIL WENT TO, on Came from (the owner, 2026-11-03: "there are 2 people on this email (though you don't see recipients of the email
// in came from) and the other person will take care of it"): a plain line under the sender, no new button.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { toLine } from "../src/taskSources.js";
import { fromStatus } from "../src/taskLayout.js";

const page = fs.readFileSync(new URL("../src/TaskPage.jsx", import.meta.url), "utf8");

test("the To and Cc lines by name, the owner as you", () => {
  assert.deepEqual(toLine({ to: ["you", "Gail Moreno"], cc: ["Ray Colton"], n: 3 }),
    { short: "to you, Gail Moreno · cc Ray Colton", full: "to you, Gail Moreno · cc Ray Colton" });
  assert.deepEqual(toLine({ cc: ["you"], to: ["Gail Moreno"], n: 2 }).short, "to Gail Moreno · cc you");
});

test("a long list says its first few and how many more; the whole of it is there too", () => {
  const rec = { to: ["you", "Gail Moreno", "Ray Colton", "Erin Blake", "Paula Vance"], cc: ["Omar Keller"], n: 20 };
  const w = toLine(rec);
  assert.equal(w.short, "to you, Gail Moreno, Ray Colton, Erin Blake and 16 more");
  assert.equal(w.full, "to you, Gail Moreno, Ray Colton, Erin Blake, Paula Vance · cc Omar Keller and 14 more", "names the server cut are counted");
});

test("nobody but the owner, or no lines at all, says nothing", () => {
  for (const r of [undefined, null, {}, { to: [], cc: [], n: 1 }]) assert.deepEqual(toLine(r), { short: "", full: "" });
});

test("the folded Came from tab carries it under its first line, and leaves it out when there is none", () => {
  assert.deepEqual(fromStatus({ channel: "Email", count: 1, to: "to you, Gail Moreno", msgs: [{ who: "Paula Vance", words: "Kindly adjust my role" }] }).lines,
    ["Email · 1 message", "to you, Gail Moreno", "Paula Vance: “Kindly adjust my role”"]);
  assert.deepEqual(fromStatus({ channel: "Email", count: 1 }).lines, ["Email · 1 message"]);
});

test("What came in and the stacked Came from draw the line, a plain text, never a button", () => {
  assert.match(page, /data-tq-came-in-to=""/);
  assert.match(page, /\{toWent\(\)\}/, "under the sender in What came in");
  assert.match(page, /\{!twoUp && toWent\(\)\}/, "and in the stacked Came from");
  assert.match(page, /to: toLine\(cameIn\?\.Recipients\)\.short/, "and in the folded tab");
  const at = page.indexOf("const toWent");
  assert.doesNotMatch(page.slice(at, page.indexOf("const fromFacts", at)), /<Button|<Link|onClick/);
});
