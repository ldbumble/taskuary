import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

test("every close icon button has an accessible name", () => {
  const src = path.join(process.cwd(), "src");
  for (const name of fs.readdirSync(src).filter((file) => file.endsWith(".jsx"))) {
    const body = fs.readFileSync(path.join(src, name), "utf8");
    for (const button of body.match(/<IconButton\b[\s\S]*?<\/IconButton>/g) || []) {
      if (!button.includes("<CloseIcon")) continue;
      assert.match(button.slice(0, button.indexOf("<CloseIcon")), /\baria-label=/, `${name}: ${button}`);
    }
  }
});
