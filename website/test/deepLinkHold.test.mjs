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

test("while held, the spinner stands in for the conversation and the Advisor strip - nothing of the item before the link", () => {
  assert.match(src, /\{\(!state \|\| holding\) && !err && <Box[^\n]*<CircularProgress/);
  const at = src.indexOf("{!holding && <>"), end = src.indexOf("</>}", at);
  assert.ok(at > 0 && end > at, "the chat body's content is behind the hold");
  // ...the lines after the table's item drawn in the pop-up over it instead (the one-row chat bar, 2026-10-26)
  assert.ok(src.slice(at, end).includes("shown.map((m, i) => popOn && i > lastCardIdx ? null : <Line"), "the conversation, the table's item with it");
  // ...and the Advisor's mark (no strip since 2026-10-26) is not drawn for the item before the link either
  assert.match(src, /\{!firstRun && table\.speaks && !holding && !hostedRow && <>/);
});

test("a chat read sent before a turn began never puts its older table back over that turn's answer", () => {
  assert.match(src, /const turnOnce = useCallback\(async \(body\) => \{\n    turnsBegun\.current \+= 1;/);
  assert.match(src, /const turns = turnsBegun\.current, moves = tableMoves\.current, mid = turnFlight\.current;\n    const \{ data: st \} = await api\.get\("\/api\/concierge"\);/);
  assert.match(src, /if \(turns === turnsBegun\.current && \(said\?\.key \|\| null\) !== \(currentRef\.current\?\.key \|\| null\)\) putOnTable\(said, "sync"\);/);
});

// RING (the dead-end walk, 2026-10-20): a link to the task the page loaded with, pressed in the chat once Next had moved on, was taken for the
// reload of the address and opened nothing - the guard read the boot's answer (state.current), not what is on the table now
test("a task link is skipped as the page's own address only when that task is on the table now", () => {
  assert.match(src, /request\.fromUrl && !request\.start && !request\.act\n\s+&& Number\(currentRef\.current\?\.tid \?\? \/\^task:\(\\d\+\)\$\/\.exec\(currentRef\.current\?\.key \|\| cardRef\.current \|\| ""\)/);
  assert.doesNotMatch(src, /Number\(state\.current\?\.tid/);
});
