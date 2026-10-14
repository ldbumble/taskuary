// Downloads are the number the stats page exists for (the owner, 2026-10-14: "why does this not say how many people
// hit the download button, that's the most important number... it should be on top"). The landing page already
// counts each Taskuary.exe click as cta/download; the page folded it into one "pressed a button" card with the demo
// and the repo, so the one number that matters could not be read.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const page = fs.readFileSync(new URL("../../site/stats.html", import.meta.url), "utf8");

test("the first card is the downloads, read from the cta/download events", () => {
  const cards = page.slice(page.indexOf("'<div class=\"cards\">'"));
  const first = cards.slice(0, cards.indexOf("</div>'"));
  assert.match(first, /downloads/);
  assert.match(page, /Kind === 'cta' && x\.What === 'download'/);
});

test("the button card says it counts every button, not only the download", () => {
  assert.doesNotMatch(page, /<span>pressed a button on the landing page<\/span>/);
  assert.match(page, /any button on the landing page/);
});
