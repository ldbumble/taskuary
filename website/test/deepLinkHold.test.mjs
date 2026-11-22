// A cold #task=N link: the page's own reads and the link's pull race at load (the perf pass, 2026-10-20). It draws that task first: the
// conversation's last item on the table drew whole for the link's pull, then gave way (the previous task was drawn first in 8 of 9 cold
// links). The page holds its spinner until the pull lands.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");

test("only a task link from the address holds the page, and it lets go once its pull is over, before paint", () => {
  assert.match(src, /useState\(\(\) => \(request\?\.kind === "task" && request\.fromUrl \? request\.n : 0\)\)/);
  assert.match(src, /useLayoutEffect\(\(\) => \{ if \(linkHold && \(doneReq\.current === linkHold \|\| request\?\.n !== linkHold\) && !turnFlight\.current\) setLinkHold\(0\); \}\);/);
  // an error or setup is never held behind a spinner
  assert.match(src, /const holding = !!linkHold && !err && !firstRun;/);
});

test("while held, the spinner stands in for the conversation and the row's mark - nothing of the item before the link", () => {
  assert.match(src, /\{\(!state \|\| holding\) && !err && <Box[^\n]*<CircularProgress/);
  const at = src.indexOf("{!holding && <>"), end = src.indexOf("</>}", at);
  assert.ok(at > 0 && end > at, "the chat body's content is behind the hold");
  // ...the conversation's lines drawn in the chat window instead, the cards on the canvas (the chat window, 2026-10-28)
  assert.ok(src.slice(at, end).includes("shown.map((m, i) => inWin.has(m.id) || gone.has(m.id) ? null : <Line"), "the conversation, the table's item with it");
  // ...and the mark of what is filled (no strip since 2026-10-26) is not drawn for the item before the link either
  assert.match(src, /\{!firstRun && table\.speaks && !holding && !hostedRow && readFor\?\.key === table\.key/);
});

// RING (the dead-end walk, 2026-10-20): a link to the task the page loaded with, pressed in the chat once Next had moved on, was taken for the
// reload of the address and opened nothing - the guard read the boot's answer (state.current), not what is on the table now
