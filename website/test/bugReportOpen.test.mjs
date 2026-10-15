import test from "node:test";
import assert from "node:assert/strict";
import { bellError, draftRequest, howToOpen, rawError, shownError } from "../src/bugReportOpen.js";
import { mask } from "../src/shot.js";
import { mergeDurableTurns } from "../src/assistantTurns.js";

const snap = { screen: "Assistant", route: "/api/tasks/:id/notes", error: "Request failed (500: disk full)", stack: "Error: Request failed\n at x", actions: ["POST /api/tasks/:id/notes"], at: "2026-10-14T09:00:00Z" };

test("the Help icon sends the client's snapshot as it is", () => assert.deepEqual(draftRequest(snap, null), snap));

test("an error the page drew reads beside the failure the client recorded, route and stack kept", () => {
  const r = draftRequest(snap, shownError("Not done - Taskuary didn't answer."));
  assert.equal(r.error, "Not done - Taskuary didn't answer.\nRequest failed (500: disk full)");
  assert.equal(r.route, snap.route); assert.equal(r.stack, snap.stack); assert.deepEqual(r.actions, snap.actions);
  assert.equal(draftRequest(snap, shownError(snap.error)).error, snap.error);
});

test("a bell item stands alone: its own words, screen and time, none of the client's last failure", () => {
  const r = draftRequest(snap, bellError({ key: "connector:imap", title: "Mail is not coming in", detail: "The poll failed 3 times.", where: "Connections", since: "2026-10-14T08:00:00Z" }));
  assert.deepEqual(r, { ...snap, screen: "Connections", error: "Mail is not coming in\nThe poll failed 3 times.", stack: "", route: "problem connector:imap", at: "2026-10-14T08:00:00Z" });
});

test("a refused draft still lets the person copy the error itself", () => {
  assert.equal(rawError(snap), `${snap.error}\n\n${snap.stack}`);
  assert.equal(rawError({ error: "", stack: "" }), "No error was recorded.");
});

test("the desktop window asks the server to open the page; a browser opens a tab", () => {
  assert.equal(howToOpen({ pywebview: {} }), "app"); assert.equal(howToOpen({}), "tab"); assert.equal(howToOpen(undefined), "tab");
});

test("a screenshot carries no word of the page, only its shape", () => {
  const s = "Erin Blake, erin@northwind.example\n  42", m = mask(s);
  assert.equal(m.length, s.length); assert.match(m, /^[x\s]+$/); assert.equal(m.replace(/x/g, ""), s.replace(/\S/g, ""));
  assert.equal(mask(null), "");
});

test("an error receipt keeps its status when the server's copy of the turn arrives", () => {
  const { messages } = mergeDurableTurns([{ id: "r1", role: "receipt", status: "error", text: "That step didn't load." }],
    [{ id: 77, role: "assistant", text: "That step didn't load." }]);
  assert.equal(messages[0].status, "error"); assert.equal(messages[0].commentId, 77);
});

test("a browser with no ClipboardItem refuses the screenshot as a rejection, never a throw", async () => {
  const { copyShot } = await import("../src/shot.js");
  let p; assert.doesNotThrow(() => { p = copyShot(Promise.resolve(null)); });
  await assert.rejects(p);
});
