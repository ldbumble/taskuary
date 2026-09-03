import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const source = readFileSync(fileURLToPath(new URL("../src/DocsView.jsx", import.meta.url)), "utf8");

test("playbooks have a separate Docs section from operator identity", () => {
  assert.match(source, /\["documents", "Operator documents"\]/);
  assert.match(source, /\["playbooks", `Playbooks/);
  assert.match(source, /section === "documents"[\s\S]+<OwnerCard \/>[\s\S]+\) : \([\s\S]+Search \$\{books\.length\} playbook/);
});

test("a large playbook library is searchable and scrolls inside its own shelf", () => {
  assert.match(source, /const visibleBooks = books\.filter/);
  assert.match(source, /maxHeight: \{ xs: "min\(52vh, 520px\)", md: "calc\(100vh - 260px\)" \}/);
  assert.match(source, /overflowY: "auto"/);
});

test("a playbook deep link switches into the Playbooks section", () => {
  assert.match(source, /const openPb[\s\S]+setSection\("playbooks"\)/);
  assert.match(source, /playbook=\(\[\\w:\.-\]\+\)[\s\S]+openPb\(what, type \|\| ""\)/);
});
