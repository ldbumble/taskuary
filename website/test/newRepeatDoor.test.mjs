// New has a Report tab and a Workflow tab (the owner, 2026-10-15: "we need 2, one for reports and one for workflows"):
// describe it, Build it, and the draft opens on Reports filled in - the same box Reports has, no second form.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { canvasRequestFromHash } from "../src/canvasLinks.js";
import { DRAFT_HASH, handDraft, onDraftHanded, takeDraft } from "../src/draftHandoff.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");


test("each draft opens on its own shelf, on the canvas too", () => {
  assert.deepEqual(canvasRequestFromHash(`#${DRAFT_HASH.workflow}`).state, { section: "workflows", open: "draft" });
  assert.deepEqual(canvasRequestFromHash(`#${DRAFT_HASH.report}`).state, { section: "reports", open: "draft" });
});

test("a draft waits for Reports, and an open Reports hears it at once - taken once", () => {
  handDraft("workflow", { title: "x" }, { explain: "y" });
  assert.deepEqual(takeDraft(), { kind: "workflow", config: { title: "x" }, meta: { explain: "y" } });
  assert.equal(takeDraft(), null);
  let heard = 0; const off = onDraftHanded(() => { heard += 1; });
  handDraft("report", {}, {}); off(); handDraft("report", {}, {});
  assert.equal(heard, 1);
  takeDraft();
  const view = read("ReportsView.jsx");
  assert.match(view, /take\(\);\s*\n\s*return onDraftHanded\(take\);/);
});


// STRAIGHT INTO THE BUILDER (owner-approved, 2026-11-12): "a routine that lists vendors with no invoice" came back as New's Routine card with
// Set up with AI and Set it up by hand - a middle card, and Set up with AI asked the Assistant the same thing again. A report, dashboard or
// routine the Assistant wrote up opens its builder with the setup already asked, once per line, through Set up with AI's own press
test("a report, dashboard or routine the Assistant wrote up goes straight into its builder, the setup asked once", async () => {
  const { REPEATS, goesStraight } = await import("../src/newTask.js");
  assert.deepEqual(REPEATS, ["report", "dashboard", "workflow"]);
  for (const k of REPEATS) assert.equal(goesStraight(k, 31), true, k);
  assert.equal(goesStraight("workflow", null), false, "a card nobody wrote up stays the card");
  assert.equal(goesStraight("agent", 31), false);
  const sheet = read("NewSheet.jsx"), door = read("SetupWithAi.jsx"), chat = read("AssistantView.jsx");
  // ...THE ASSISTANT BUILDS IT ON THAT PAGE (the owner, 2026-11-13): the words are handed to the builder, whose strip builds it there;
  // the chat is not asked and its window stays as it was
  assert.match(door, /if \(!goesStraight\(made\?\.kind, made\?\.line\)\) return false;\s*if \(firstPressOf\(made\.line\)\) \{ handTo\(made\.kind, made\.text \|\| ""\); onOpen\?\.\(\); openAppLink\(NEW_HASH\[made\.kind\]\); \}\s*return true;/);
  assert.doesNotMatch(door, /openHelp/, "no road through the chat");
  // ...one road from New's box and from the chat: the card is drawn only where it did not go (pressed at the card's mount, the chat's
  // road raced the canvas opening its New card, and the setup ask was typed into New's own box instead)
  assert.doesNotMatch(sheet, /goStraight/, "New's box starts an agent (/api/start) - it writes up no builder");
  assert.match(chat, /if \(data\.new && !goStraight\(data\.new\)\) browseRef\.current\?\.\("new", data\.new\);/);
});
