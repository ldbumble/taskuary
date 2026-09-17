import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const read = (name) => readFileSync(fileURLToPath(new URL(`../src/${name}`, import.meta.url)), "utf8");

// "Pointing is not setting up" held while a step was one field. The AI row grew a CLI picker, an
// installer, a sign-in pane and a key form - a worse copy of the page that owns them, kept in step
// by hand. One form survives, because two text boxes have nowhere better to be.
test("only the owner's two fields are still done in the panel", () => {
  const w = read("SetupWizard.jsx");
  assert.match(w, /const OwnerForm/);
  for (const gone of ["BrainForm", "MailboxForm", "SyncForm", "HistoryForm", "SoulForm", "AgentForm", "CliPicker"]) {
    assert.doesNotMatch(w, new RegExp(`const ${gone}`), gone);
  }
  assert.match(w, /const FORMS = \{ owner: OwnerForm \}/);
});

test("every other row is a link to the page that owns the work", () => {
  const w = read("SetupWizard.jsx");
  assert.match(w, /s\.goto/);
  assert.doesNotMatch(w, /s\.where/);
});

test("the counter is finished rather than hidden", () => {
  const w = read("SetupWizard.jsx");
  // SetupChip already returns null on complete; what must go is the second tier it counted
  assert.doesNotMatch(w, /guide_done|guide_total/);
  assert.doesNotMatch(w, /state\.ready/);
});
