// Every input to the bundle must be LF on disk, not just LF in git.
//
// .gitattributes normalises website/src on COMMIT and says why: "Vite preserves newlines in JSX
// string attributes. Keep build inputs and shipped text assets identical on Windows and Unix so
// chunk hashes are reproducible." What it cannot do is stop an editor writing CRLF back on disk
// afterwards - and then a Windows build produces a bundle CI can never reproduce, so build-web
// rejects it with a diff of deleted files that says nothing about newlines. That cost two red CI
// runs and a long hunt on 2026-09-14, with 37 of these files carrying CRLF by the end of the day.
//
// This is the cheap end of that: a local failure naming the file, before the bundle is built.
import test from "node:test";
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../src", import.meta.url));
const BUILT = /\.(jsx?|mjs|json|css)$/;

const walk = (dir) => readdirSync(dir).flatMap((name) => {
  const path = join(dir, name);
  return statSync(path).isDirectory() ? walk(path) : BUILT.test(name) ? [path] : [];
});

test("no build input carries CRLF on disk", () => {
  const crlf = walk(SRC)
    .map((path) => [path, (readFileSync(path, "utf8").match(/\r/g) || []).length])
    .filter(([, n]) => n > 0)
    .map(([path, n]) => `${path.slice(path.indexOf("src"))} · ${n} CR`);
  assert.deepStrictEqual(crlf, [], "these build from different bytes than CI checks out, so the "
    + "bundle they produce cannot be reproduced there:\n  " + crlf.join("\n  ")
    + "\n  Fix: git rm --cached -r --quiet website/src && git checkout -- website/src");
});
