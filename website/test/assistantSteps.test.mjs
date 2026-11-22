// THE ASSISTANT SHOWS ITS STEPS THE WAY THE GENERAL AGENT DOES (the owner, 2026-10-23: "if we do that we need to see what it's thinking
// like general agent"): looking into the app's own trouble (taskuary/troubleshoot.py) streams `steps` and keeps them on the answer, and
// both are drawn by the one row the general agent's trail uses - never a second rendering.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { draftRequest } from "../src/bugReportOpen.js";

const read = (n) => fs.readFileSync(path.join(process.cwd(), "src", n), "utf8");


test("what the chat could not fix is reported from what it found, not the page's last error", () => {
  const snap = { screen: "Assistant", route: "/api/concierge/say", error: "Request failed (500)", stack: "Error at x", actions: [], at: "2026-10-24T09:00:00Z" };
  const report = { message: "WhatsApp is not working: the bridge is not answering", screen: "Assistant", route: "connector whatsapp" };
  const r = draftRequest(snap, report);
  assert.equal(r.error, report.message); assert.equal(r.route, "connector whatsapp"); assert.equal(r.stack, "");
  assert.match(read("AssistantView.jsx"), /openBugReport\(c\.report \|\| shownError\(c\.text\)\)/);
});
