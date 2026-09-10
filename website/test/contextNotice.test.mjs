// The "new messages came in" notice is its own stream event, shown before the assistant's answer and
// never twice for the same turn (PW-052/057).
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

const src = fs.readFileSync(path.join(process.cwd(), "src", "AssistantView.jsx"), "utf8");

test("a context_update stream event is rendered as it arrives", () => {
  const reader = src.slice(src.indexOf("for await (const ev of readNdjson"), src.indexOf("throw new Error(\"The assistant stopped without an answer.\")"));
  assert.match(reader, /ev\.type === "context_update"/);
  assert.match(reader, /role: "assistant", text: ev\.say/);
});

test("the done payload's copy of the notice is not shown a second time", () => {
  assert.match(src, /noticedRef\.current !== data\.context_update/);
  assert.match(src, /noticedRef\.current = ev\.say/);
});
