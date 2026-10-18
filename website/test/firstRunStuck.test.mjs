// "Successfully logged in", then straight back to Sign in (the owner, 2026-10-15): every failed check said "needs sign-in". Signed in and
// still failing says what the CLI said, and offers what can fix it - never the sign-in again.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const fr = readFileSync(new URL("../src/FirstRun.jsx", import.meta.url), "utf8");

test("signed in and failing shows the error and Update / Try again / Report this bug, not Sign in", () => {
  assert.match(fr, /const stuck = q === "ai" && \["update", "retry"\]\.includes\(fix\?\.fix\)/);
  assert.match(fr, /What it said: \{fix\.detail\}/);
  assert.match(fr, />Update \{fix\.title\}</);
  assert.match(fr, />\{btnLabel\("try_again"\)\}</);
  assert.match(fr, />\{btnLabel\("report_bug"\)\}</);
  assert.match(fr, /"Signed in · not answering"/);
});

test("a ChatGPT plan that failed its test offers Sign in again first - its login may simply have lapsed", () => {
  assert.match(fr, /fix\.key === planKey && <Button variant="contained" disableElevation onClick=\{\(\) => planSignin\(plan\)\}>Sign in again</);
});
