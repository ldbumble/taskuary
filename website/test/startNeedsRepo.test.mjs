// START CODING SESSION WITH NO REPOSITORY (the owner, 2026-10-01): the button was greyed out and said nothing about why. It
// says "Pick a repo first" now, with the repo picker's own chip beside it - and the start that asked is the start that resumes
// once a repository is chosen (resumeAfterRepo { dispatch: true }), so picking is starting.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const page = readFileSync(fileURLToPath(new URL("../src/TaskPage.jsx", import.meta.url)), "utf8");

test("a Start coding session held for a repository says so and offers the picker beside it", () => {
  const at = page.indexOf('"Start new coding session" : "Start coding session"');
  const start = page.slice(at, page.indexOf("Use non-coding agent", at));
  assert.match(start, /startRepo === "" && <>/, "only while no repository is chosen");
  assert.match(start, /Pick a repo first/);
  assert.match(start, /onClick=\{\(\) => \{ setRepoPick\(true\); setResumeAfterRepo\(\{ dispatch: true \}\); \}\}/, "the pick starts the session");
});
