import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

test("Cancel and Dismiss button labels are capitalized", () => {
  const files = [
    "../src/RepoPicker.jsx",
    "../src/ui.jsx",
    "../src/TaskPage.jsx",
  ];

  for (const file of files) {
    const source = readFileSync(
      fileURLToPath(new URL(file, import.meta.url)),
      "utf8",
    );

    assert.doesNotMatch(
      source,
      />\s*(cancel|dismiss)\s*<\/Button>/,
      `${file} contains a lowercase button label`,
    );
  }
});