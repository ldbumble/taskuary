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

// Three buttons, two of them bare text, wrapping mid-label: "Add" over "profile" read as a menu of
// unrelated things rather than as two choices (the owner, 2026-09-17: "just have 2 clear buttons ..
// make them look like buttons.. make it look normal").
test("the Profiles shelf offers two real buttons and one door to a new worker", () => {
  const shelf = source.slice(source.indexOf('section === "profiles"'), source.indexOf("Used by "));
  assert.ok(shelf.length > 200 && shelf.length < 4000, `the Profiles shelf slice looks wrong (${shelf.length} chars)`);
  assert.match(shelf, /variant="contained"[\s\S]{0,140}>New profile</);
  assert.match(shelf, /variant="outlined"[\s\S]{0,140}>Manage profiles</);
  // ...and Import skills is not a third one here: it lives on the screen those buttons open
  assert.doesNotMatch(shelf, /setImportSkills\(true\)/);
  assert.doesNotMatch(shelf, /flexWrap: "wrap"/);
});

test("the manage screen names both roads to a worker", () => {
  const panel = readFileSync(fileURLToPath(new URL("../src/AgentsPanel.jsx", import.meta.url)), "utf8");
  assert.match(panel, />Add profile manually</);
  assert.match(panel, />Import skills</);
});

// "not routed" was one word for four situations, and for the commonest it said the opposite of what
// happens: every coding task goes to CODER.md (the owner, 2026-09-17: "why does coder.md say not
// routed? it is but default for coding tasks").
test("a worker routed by kind says so, and is not dressed as a fault", () => {
  assert.match(source, /coding: "all coding tasks"/);
  assert.match(source, /off: "switched off"/);
  assert.match(source, /not_offered: "not offered to triage"/);
  assert.match(source, /no_purpose: "no purpose set"/);
  // the code comes from the server, because reading its prose would be a second implementation
  assert.match(source, /pr\.seen\.find\(\(m\) => m\.code\)/);
  // ...and a coding worker keeps the ordinary chip rather than the muted one
  assert.match(source, /const isRouted = \(pr\) => pr\.onRoster > 0 \|\| pr\.seen\.some\(\(m\) => m\.code === "coding"\)/);
  assert.match(source, /every coding task comes here/);
});
