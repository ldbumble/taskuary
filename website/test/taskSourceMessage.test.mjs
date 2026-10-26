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
  // ...in full, and never a scroller inside the column that scrolls (the owner, 2026-10-26: "you can't see anything")
  assert.match(card, /data-tq-letter-body=""/);
  assert.doesNotMatch(card, /maxHeight|overflowY/);
  assert.doesNotMatch(card, /WebkitLineClamp/);
  assert.match(card, /r\.m\.ReadText \?\? r\.m\.BodyText/, "an email still shows its own words, not the quoted chain");
  assert.match(page, /onClick=\{\(\) => onOpen\(/, "a row in Came from opens its message in full under it");
  // ...and a task that came from ONE message reads it whole from the start (the redesign, 2026-10-21) - unless the ask under the title
  // is that message's own words, which are then read once (the task-view cleanup, owner-approved 2026-10-25)
  assert.match(page, /const askIsBody = sourceCount === 1 && sameWords\(askText, opener\?\.ReadText \|\| opener\?\.BodyText\);/);
  assert.match(page, /const shownMsg = openMsg !== undefined \? openMsg : sourceCount === 1 && !askIsBody \? sources\[0\]\?\.msgs\[0\]\?\.MessageId \?\? null : null;/);
});
