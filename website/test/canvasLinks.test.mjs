import test from "node:test";
import assert from "node:assert/strict";
import { canvasRequestFromHash } from "../src/canvasLinks.js";

// Every link the app writes still lands once the tabs are gone (the canvas redesign, 2026-09-29).
test("each old link becomes a canvas request", () => {
  assert.deepEqual(canvasRequestFromHash("#task=123", 4), { kind: "task", tid: 123, n: 4 });
  assert.deepEqual(canvasRequestFromHash("#new-task"), { kind: "new", n: 0 });
  assert.deepEqual(canvasRequestFromHash("#report=17").state, { section: "reports", open: 17 });
  assert.deepEqual(canvasRequestFromHash("#report=new").state, { section: "reports", open: "new-report" });
  assert.deepEqual(canvasRequestFromHash("#report=workflows").state, { section: "workflows", open: null });
  assert.deepEqual(canvasRequestFromHash("#report=new-agent").state, { section: "workflows", open: "new-agent" });
  assert.equal(canvasRequestFromHash("#connector=gmail").area, "connections");
  assert.equal(canvasRequestFromHash("#cli-agents").area, "connections");
  assert.deepEqual(canvasRequestFromHash("#settings=config&group=Triage%20%26%20agents").state, { section: "config", open: "Triage & agents" });
  assert.deepEqual(canvasRequestFromHash("#settings=policies").state, { section: "policies", open: "policies" });
  assert.deepEqual(canvasRequestFromHash("#settings=docs").state, { section: "docs", open: null }, "Docs opens on its shelf of files");
  assert.deepEqual(canvasRequestFromHash("#playbook=weekly-close").state, { section: "playbooks", open: "docs" });
  assert.deepEqual(canvasRequestFromHash("#profiles").state, { section: "profiles", open: null }, "the Profiles section, every profile a card");
});

test("a link that is not a page is left alone", () => {
  assert.equal(canvasRequestFromHash("#msg=12"), null);   // the rail reads that one itself
  assert.equal(canvasRequestFromHash(""), null);
  assert.equal(canvasRequestFromHash("#report=nonsense").state.open, null, "an unknown report bucket opens the list, not a blank editor");
});

// the final review (2026-09-29): "#settings=foo" crashed the whole app, on every reload - a page the app does not have
// opens the Settings sections instead
test("a settings link to a page that does not exist opens the section list", () => {
  assert.deepEqual(canvasRequestFromHash("#settings=foo").state, { section: null, open: null });
  assert.deepEqual(canvasRequestFromHash("#settings=config&group=Renamed%20group").state, { section: "config", open: "Renamed group" },
    "a group is checked by the view, which knows the groups");
});
