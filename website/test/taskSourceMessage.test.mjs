import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const page = fs.readFileSync(path.join(process.cwd(), "src", "TaskPage.jsx"), "utf8");

test("where a task came from shows the whole message, not three lines of it", () => {
  // a report run was shown in full from 2026-09-30, an email still at three lines - "don't see the full email that
  // this task came from" (the owner, 2026-10-01). Every source message scrolls in full.
  const at = page.indexOf("WHERE IT CAME FROM IS THE WHOLE MESSAGE");
  assert.notEqual(at, -1);
  const card = page.slice(at, page.indexOf("</Box>", at));
  assert.match(card, /maxHeight: 420, overflowY: "auto"/);
  assert.doesNotMatch(card, /WebkitLineClamp/);
  assert.match(card, /m\.ReadText \?\? m\.BodyText/, "an email still shows its own words, not the quoted chain");
});
