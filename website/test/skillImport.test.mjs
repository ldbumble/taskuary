import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { buildPayload, chosen, clashText, cutBy, isLink, reconcileImport, slug, toRows } from "../src/skillImport.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
const wizard = read("SkillImport.jsx");
const docs = read("DocsView.jsx");
const agents = read("AgentsPanel.jsx");

test("a link goes to /fetch and a path to /read, decided in one place", () => {
  assert.equal(isLink("https://github.com/anthropics/skills"), true);
  assert.equal(isLink(" HTTP://x/SKILL.md"), true);
  assert.equal(isLink("~/.claude/skills/x/SKILL.md"), false);
  assert.equal(isLink("C:/Users/me/SKILL.md"), false);
  assert.match(wizard, /isLink\(target\)/);
  assert.match(wizard, /"\/api\/skills\/fetch", \{ url: target \}/);
  assert.match(wizard, /"\/api\/skills\/read", \{ path: target \}/);
});

test("you choose which ones: one skill starts chosen, a catalogue starts unchosen, only chosen rows are sent", () => {
  const one = toRows([{ name: "A", body: "b" }]);
  assert.equal(one[0].include, true); assert.equal(one[0].enabled, false);
  const many = toRows([{ name: "A" }, { name: "B" }, { name: "C" }]);
  assert.deepEqual(many.map((r) => r.include), [false, false, false]);
  many[1].include = true;
  assert.deepEqual(chosen(many).map((r) => r.name), ["b"]);
  assert.deepEqual(buildPayload(many).map((r) => r.name), ["b"]);       // A and C are never written
  assert.deepEqual(chosen([{ include: true, imported: true }, { include: true, imported: false }]).length, 1);
  // the markup: a tick per row, select all / none, Next needs at least one chosen
  assert.match(wizard, /<Checkbox checked=\{!!r\.include\}/);
  assert.match(wizard, /Select all/); assert.match(wizard, />None</);
  assert.match(wizard, /disabled=\{busy \|\| !pending\.length \|\| !allNamed\}/);
  assert.match(wizard, /rows\.map\(\(r, i\) => r\.include && \(/);     // step 3 lists only the chosen
});

test("Manage profiles can import skills too, beside Add profile", () => {
  assert.match(agents, /import SkillImport from "\.\/SkillImport\.jsx"/);
  assert.match(agents, /Add profile<\/Button>\s*<Button variant="outlined" onClick=\{\(\) => setImportSkills\(true\)\}/);
  assert.match(agents, /<SkillImport onClose=\{\(\) => setImportSkills\(false\)\} onImported=\{load\} \/>/);
});

const row = (over) => ({ name: "My Skill", purpose: "p", body: "b", kind: "general", path: "/x",
  bytes: 10, include: true, enabled: true, replace: false, clash: null, imported: false, ...over });

test("nothing is imported without the owner reading it", () => {
  // /read proposes, /import writes - a remote skill is a draft until a human says otherwise
  assert.match(wizard, /"\/api\/skills\/read"/);
  assert.match(wizard, /"\/api\/skills\/import"/);
  // the body is shown behind an expander, not just the one-line purpose
  assert.match(wizard, /Hide the body/);
  assert.match(wizard, /r\.body/);
});

test("nothing reaches the router unless it is ticked, and the label says what the tick does", () => {
  assert.equal(toRows([{ name: "x" }])[0].enabled, false);   // a proposal starts unticked, whatever door it came through
  assert.match(wizard, /Offer this worker to the router/);
  assert.match(wizard, /triage never picks it/);
});

test("a name clash offers a rename or a confirmed overwrite, and neither is silent", () => {
  assert.match(wizard, /clashText\(r\.clash\)/);
  assert.match(wizard, /Rename/);
  assert.match(wizard, /Overwrite it/);
  // Overwrite ASKS FIRST: a rules document has no history, so a mis-click is unrecoverable. The button
  // opens the confirm; only the confirm's onConfirm flags the row.
  assert.match(wizard, /onClick=\{\(\) => setOverwrite\(i\)\}>Overwrite it/);
  assert.match(wizard, /<Confirm open=\{overwrite !== null\}/);
  assert.match(wizard, /onConfirm=\{\(\) => \{ setRow\(overwrite, \{ replace: true, clash: null \}\); \}\}/);
  assert.doesNotMatch(wizard, /onClick=\{\(\) => setRow\(i, \{ replace: true/);   // no unconfirmed road left
});

test("a clash on an operator document is named as one, not as a profile", () => {
  assert.equal(clashText({ kind: "research", doc: "" }), 'clashes with an existing "research" profile');
  assert.equal(clashText({ kind: "general", doc: "triage" }), "would rewrite TRIAGE.md - an operator document, not a profile");
  const rows = [row({ name: "triage" })];
  const after = reconcileImport(rows, { imported: [], clashed: [{ name: "triage", kind: "general", doc: "triage" }] });
  assert.equal(after[0].clash.doc, "triage");
  assert.match(wizard, /Overwrite \$\{rows\[overwrite\]\.clash\.doc\.toUpperCase\(\)\}\.md\?/);   // the confirm names the document
});

test("the size warning is the seed's own cut, reported by the server - not a byte count", () => {
  // /api/skills/read sends `flat` (the body as a session receives it) and `doc_chars` (where the seed
  // cuts a rules document). The old rule warned "large" at 20,000 bytes while the real cut was under
  // 5,000 flattened, so most skills arrived truncated with nothing on screen saying so.
  assert.equal(cutBy({ flat: 6100 }, 5600), 500);
  assert.equal(cutBy({ flat: 5600 }, 5600), 0);
  assert.equal(cutBy({ flat: 9000 }, 0), 0);                // an older server sends no cut: no warning invented
  assert.match(wizard, /setDocChars\(data\.doc_chars/);
  assert.match(wizard, /past what a session is given - the end is cut/);
  assert.doesNotMatch(wizard, /LARGE|20000/);
  assert.match(wizard, /kb\(r\.bytes\)/);
});

test("the wizard names both doors - a link or a path - and the field takes either", () => {
  assert.match(wizard, /Paste a link/);
  assert.match(wizard, /label="Link or path"/);
  assert.doesNotMatch(wizard, /fetched from a link/);   // the old copy promised a door before it existed
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
  assert.equal(after[0].clash.kind, "research");
  assert.equal(after[0].imported, false);
});

test("slug matches the server's own rule (taskuary/skillimport.py's save())", () => {
  assert.equal(slug("My Skill"), "my-skill");
  assert.equal(slug("  --Weird__Name!! "), "weird-name");
  assert.equal(slug(""), "");
});

test("a profile row's roster state comes from the server, and the open profile shows the line triage reads", () => {
  // ONE implementation of "does triage see this worker" (agents.roster_line): the row counts members
  // the server gave a line, and the card shows that line - or the reason there is none - verbatim.
  assert.match(docs, /const seen = r\.roster \|\| /);
  assert.match(docs, /if \(seen\.line\) g\.onRoster \+= 1;/);
  assert.doesNotMatch(docs, /triage_enabled !== false\) g\.onRoster/);
  assert.match(docs, /WHAT TRIAGE SEES/);
  assert.match(docs, /not on the roster — \{why\}/);   // one line per REASON, however many members share it
});

test("an own profile can be deleted from Docs, and it asks first", () => {
  assert.match(docs, /setDeleteProf\(cur\.name\)/);
  assert.match(docs, /<ConfirmDelete open=\{!!deleteProf\}/);
  assert.match(docs, /api\.delete\(`\/api\/agents\/\$\{encodeURIComponent\(deleteProf\)\}`\)/);
  // never for the shared coding document: its workers are removed on Manage profiles
  assert.match(docs, /cur\.name !== "coder"/);
});

test("renaming out of a clash also clears replace, defensively", () => {
  assert.match(wizard, /setRow\(i, \{ name: slug\(`\$\{r\.name\}-imported`\), clash: null, replace: false \}\)/);
});
