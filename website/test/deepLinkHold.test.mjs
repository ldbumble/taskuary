// A cold #task=N link: the page's own reads and the link's pull race at load (the perf pass, 2026-10-20).
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const src = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");

test("a chat read sent before a turn began never puts its older table back over that turn's answer", () => {
  assert.match(src, /const turnOnce = useCallback\(async \(body\) => \{\n    turnsBegun\.current \+= 1;/);
  assert.match(src, /const turns = turnsBegun\.current;\n    const \{ data: st \} = await api\.get\("\/api\/concierge"\);/);
  assert.match(src, /if \(turns === turnsBegun\.current && \(said\?\.key \|\| null\) !== \(currentRef\.current\?\.key \|\| null\)\) putOnTable\(said, "sync"\);/);
});
