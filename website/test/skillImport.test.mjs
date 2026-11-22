import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { buildPayload, chosen, clashText, cutBy, isLink, reconcileImport, slug, toRows } from "../src/skillImport.js";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");
const wizard = read("SkillImport.jsx");


test("a link goes to /fetch and a path to /read, decided in one place", () => {
  assert.equal(isLink("https://github.com/anthropics/skills"), true);
  assert.equal(isLink(" HTTP://x/SKILL.md"), true);
  assert.equal(isLink("~/.claude/skills/x/SKILL.md"), false);
  assert.equal(isLink("C:/Users/me/SKILL.md"), false);
  assert.match(wizard, /isLink\(target\)/);
  assert.match(wizard, /"\/api\/skills\/fetch", \{ url: target, paths \}/);
  assert.match(wizard, /"\/api\/skills\/read", \{ path: target, paths \}/);
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


const row = (over) => ({ name: "My Skill", purpose: "p", body: "b", kind: "general", path: "/x",
  bytes: 10, include: true, enabled: true, replace: false, clash: null, imported: false, ...over });


test("nothing reaches the router unless it is ticked, and the label says what the tick does", () => {
  assert.equal(toRows([{ name: "x" }])[0].enabled, false);   // a proposal starts unticked, whatever door it came through
  assert.match(wizard, /Offer this worker to the router/);
  assert.match(wizard, /triage never picks it/);
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
