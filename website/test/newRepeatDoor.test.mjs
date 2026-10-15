// New has a door for a job that repeats, and it opens the one place reports and workflows are set up (2026-10-15).
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { canvasRequestFromHash } from "../src/canvasLinks.js";

const src = fs.readFileSync(new URL("../src/NewSheet.jsx", import.meta.url), "utf8");

test("Report or workflow is a door on New, with no form of its own", () => {
  assert.match(src, /key: "repeat", mark: "🔁", label: "Report or workflow"/);
  assert.match(src, /if \(kind === "repeat"\) \{ onClose\?\.\(\); window\.location\.hash = REPEAT_TO\[repeat\]; return; \}/);
  assert.match(src, /\{kind !== "repeat" && <Box>/);              // no words box: those are typed on the Reports page
});

test("each choice lands on its own setup page, on the canvas too", () => {
  const to = Object.fromEntries([...src.matchAll(/(report|workflow): "(report=[^"]+)"/g)].map((m) => [m[1], m[2]]));
  assert.deepEqual(canvasRequestFromHash(`#${to.workflow}`).state, { section: "workflows", open: "new-agent" });
  assert.deepEqual(canvasRequestFromHash(`#${to.report}`).state, { section: "reports", open: "new-report" });
});
