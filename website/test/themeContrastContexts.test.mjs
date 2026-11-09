import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
const read = (name) => readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("signature ink stays visible on its exported paper surface in either theme", () => {
  const src = read("HandSignature.jsx");
  assert.ok(/g\.strokeStyle = "#1d2a52"/.test(src));
  assert.ok(/aspectRatio:[^\n]*bgcolor: "#fff"/.test(src), "drawing canvas needs paper, not the night panel");
  assert.ok(/\{url \? <Box[^\n]*bgcolor: "#fff"/.test(src), "transparent saved signature needs paper too");
});

test("danger text uses readable ink while attention fills keep their solid colour", () => {
  for (const f of ["QueuedStart.jsx", "HeldStart.jsx", "TasksView.jsx", "TaskPage.jsx", "assistantCards.jsx"]) {
    assert.ok(!/color: ALERT\b/.test(read(f)), `${f}: dark solid is not a text colour`);
  }
});

test("Game hosts shared widgets on themed surfaces with matched text", () => {
  const game = read("AssistantGame.jsx"), item = read("gameItem.jsx");
  assert.ok(/bgcolor: "var\(--tq-panel, #f6f2ea\)"/.test(game), "live WorkLine panel");
  assert.ok(/bgcolor: "var\(--tq-panel, #f6f2ea\)"/.test(item), "RepoPicker host");
  assert.ok(!/mt: 1, color: "#262521"/.test(item), "AgentAsk host follows the palette");
});

test("contained actions with fixed solid fills declare a light foreground", () => {
  assert.ok(/color: "#fff", bgcolor: "#55697a"/.test(read("RemindMe.jsx")), "reminder action");
  assert.ok(/color: "#fff", bgcolor: "#8a7a5c"/.test(read("ui.jsx")), "queue action");
});
