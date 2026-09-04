import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const source = await readFile(new URL("../src/ReportsView.jsx", import.meta.url), "utf8");

test("Run now is owned by the server and survives leaving the Reports tab", () => {
  const start = source.indexOf("const runNow = async (sid)");
  const block = source.slice(start, source.indexOf("const syncNow", start));
  assert.match(block, /\/api\/reports\/\$\{sid\}\/rerun/);
  assert.doesNotMatch(block, /\/api\/sources\/\$\{sid\}\/run/);
  assert.match(block, /running in the background/);
  assert.match(block, /leave this tab/);
});

test("an existing report has a visible top-level Delete button", () => {
  const wizard = source.slice(source.indexOf("function ReportWizard"));
  const header = wizard.slice(wizard.indexOf("return ("), wizard.indexOf("<Stepper"));
  assert.match(header, /Delete \{workflow \? "workflow" : "report"\}/);
  assert.match(header, /setConfirmDel\(true\)/);
  assert.match(wizard, /api\.delete\(`\/api\/sources\/\$\{cur\.SourceId\}`\)/);
});
