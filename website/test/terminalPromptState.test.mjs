import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

test("an accepted Devin prompt says it is waiting for the first response instead of looking frozen", () => {
  const terminal = read("TerminalView.jsx");
  assert.match(terminal, /typeof m\.promptPending === "boolean"/);
  assert.match(terminal, /Task sent to \{promptState\.cli/);
  assert.match(terminal, /waiting for first response/);

  // The same fact appears on every compact live-work surface, even before a witness has emitted
  // its first work object.
  assert.match(read("BoardView.jsx"), /run\.work \|\| run\.promptPending/);
  assert.match(read("WallView.jsx"), /statusWork \|\| waiting \|\| l\?\.promptPending \|\| s\.promptPending/);
  assert.match(read("StudioView.jsx"), /liveRow\?\.work \|\| liveRow\?\.promptPending/);
});
