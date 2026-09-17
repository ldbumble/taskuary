import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { buildPayload, reconcileImport, slug } from "../src/skillImport.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
const wizard = read("SkillImport.jsx");
const docs = read("DocsView.jsx");

const row = (over) => ({ name: "My Skill", purpose: "p", body: "b", kind: "general", path: "/x",
  bytes: 10, enabled: true, replace: false, clash: null, imported: false, ...over });

test("nothing is imported without the owner reading it", () => {
  // /read proposes, /import writes - a remote skill is a draft until a human says otherwise
  assert.match(wizard, /"\/api\/skills\/read"/);
  assert.match(wizard, /"\/api\/skills\/import"/);
  // the body is shown behind an expander, not just the one-line purpose
  assert.match(wizard, /Hide the body/);
  assert.match(wizard, /r\.body/);
});

test("nothing reaches the router unless it is ticked, and the label says what the tick does", () => {
  assert.match(wizard, /enabled: false/);   // /read's proposals start unticked
  assert.match(wizard, /Offer this worker to the router/);
  assert.match(wizard, /triage never picks it/);
});

test("a name clash offers a rename or a confirmed overwrite, and neither is silent", () => {
  assert.match(wizard, /clashes with an existing/);
  assert.match(wizard, /Rename/);
  assert.match(wizard, /Overwrite it/);
  assert.match(wizard, /replace: true/);
});

test("each row shows its byte size, so a large harness-shaped skill is visibly different", () => {
  assert.match(wizard, /kb\(r\.bytes\)/);
  assert.match(wizard, /large - may name tools this CLI lacks/);
});

test("Docs opens the wizard from Profiles, beside Add profile", () => {
  assert.match(docs, /Import skills/);
  assert.match(docs, /setImportSkills\(true\)/);
  assert.match(docs, /<SkillImport onClose=\{\(\) => setImportSkills\(false\)\}/);
});

test("the profiles list already scrolls, and a row says whether it reaches the router", () => {
  // R5: this list already had overflowY - this asserts it stayed, not that it was just added
  assert.match(docs, /section === "profiles"[\s\S]{0,1200}overflowY: "auto"/);
  // a row not on the roster must say so where the list already is, not just inside the open document
  assert.match(docs, /const rosterChip = \(pr\) => /);
  assert.match(docs, /"not routed"/);
  assert.match(docs, /"on the roster"/);
});

// Fix round 1: the server slugifies a name before writing it and echoes back the slug, but a row
// used to match on the raw, freely-typed field - so "My Skill" imported fine server-side and then
// sat in `pending` forever, because "My Skill" !== "my-skill". These exercise the actual behaviour
// (buildPayload/reconcileImport) rather than grepping for the slug rule's pattern.
test("a human-friendly name imports, matches the response, and reaches Done", () => {
  const rows = [row()];
  assert.equal(slug(rows[0].name), "my-skill");
  const payload = buildPayload(rows);
  assert.equal(payload[0].name, "my-skill");                 // what the server actually receives
  // the server slugifies too and echoes the slug back - simulate exactly that response
  const after = reconcileImport(rows, { imported: ["my-skill"], clashed: [] });
  assert.equal(after[0].imported, true);
  assert.equal(after[0].name, "my-skill");                   // the row now names what really exists
  assert.equal(after.every((r) => r.imported), true);        // nothing left in pending - Done reachable
});

test("a clash is matched on the slug too, and stays reported rather than silently resolved", () => {
  const rows = [row({ name: "Researcher", kind: "research" })];
  const after = reconcileImport(rows, { imported: [], clashed: [{ name: "researcher", kind: "research" }] });
  assert.equal(after[0].clash, "research");
  assert.equal(after[0].imported, false);
});

test("slug matches the server's own rule (taskuary/skillimport.py's save())", () => {
  assert.equal(slug("My Skill"), "my-skill");
  assert.equal(slug("  --Weird__Name!! "), "weird-name");
  assert.equal(slug(""), "");
});

test("renaming out of a clash also clears replace, defensively", () => {
  assert.match(wizard, /setRow\(i, \{ name: slug\(`\$\{r\.name\}-imported`\), clash: null, replace: false \}\)/);
});
