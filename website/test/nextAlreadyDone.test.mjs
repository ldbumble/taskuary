// A NEXT THAT ALREADY HAPPENED IS NOT A FAILURE (the email walk, 2026-10-29): "Remove - not a task" came back with a red 409, "This
// navigation already completed. Review the current conversation." The server refuses a selection token it has spent
// (processing_navigation.reserve) - the move was made. The page reads the conversation and the table as the server has them, puts
// nothing back, and says nothing; every other refusal still puts the table back and says why.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const src = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
const surface = src.slice(src.indexOf("const surface = useCallback"), src.indexOf("useEffect(() => { surfaceRef.current = surface; }"));

test("a spent token reads the conversation again instead of saying it failed", () => {
  assert.match(surface, /done = guard\?\.reason === "already_completed";/);
  assert.match(surface, /if \(!done\) setErr\(errText\(e\)\);/);
  assert.match(surface, /if \(!done && leftItem\) \{ unleave\(leftItem\); putOnTable\(leftItem, "sync"\); \}/);
  assert.match(surface, /if \(done\) readChatOnce\(chatEpoch\.current\)\.catch\(\(\) => \{\}\);/);
  assert.match(surface, /\}, \[[^\]]*readChatOnce[^\]]*\]\);$/m);
});
