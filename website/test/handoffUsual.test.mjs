// THE USUAL RECIPIENT, CHOSEN NOT SENT (the owner, 2026-10-25: "Hand it to a person" pre-fills the usual recipient): the drawer opens
// with the person this sender's asks were handed to before, says whose usual it is, never writes over a name already typed, and sends
// nothing until Send it is pressed. Nobody learned - or the ask failing - leaves the form as it was.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { usualHandWhy, usualLine } from "../src/taskFilter.js";

const src = readFileSync(new URL("../src/Handoff.jsx", import.meta.url), "utf8");

test("the usual recipient says whose usual it is, and nothing at all when there is none", () => {
  assert.equal(usualHandWhy({ to: "ray@northwind.example", from: "east.manager@northwind.example", n: 2, of: 2 }), "your usual for east.manager@northwind.example");
  for (const none of [{}, null, undefined, { to: "ray@northwind.example" }]) assert.equal(usualHandWhy(none), "");
});

test("the drawer fills To from the usual, never over a typed name, and only Send it sends", () => {
  assert.match(src, /api\.get\(`\/api\/tasks\/\$\{taskId\}\/handoff\/usual`\)/);
  assert.match(src, /setTo\(\(v\) => v \|\| data\.to\)/, "a name already typed stays");
  assert.match(src, /\.catch\(\(\) => \{\}\)/, "a failed ask changes nothing");
  const fill = src.slice(src.indexOf("/handoff/usual"), src.indexOf("const call = async"));
  assert.doesNotMatch(fill, /call\(|send\(|api\.post/, "chosen, not sent");
  assert.match(src, /usual && to === usual\.to && \(/, "the why stands only while the chosen person is still in To");
});

test("Remind me's day is read from a How you work line, said on hover", () => {
  assert.equal(usualLine({ line: "You put mail from renewals@payworth.example off to Friday" }), "How you work: You put mail from renewals@payworth.example off to Friday");
  assert.equal(usualLine({}), "");
  assert.match(readFileSync(new URL("../src/RemindMe.jsx", import.meta.url), "utf8"), /title=\{usualLine\(usual\)\}/);
});
