// THE ASSISTANT SHOWS ITS STEPS THE WAY THE GENERAL AGENT DOES (the owner, 2026-10-23: "if we do that we need to see what it's thinking
// like general agent"): looking into the app's own trouble (taskuary/troubleshoot.py) streams `steps` and keeps them on the answer, and
// both are drawn by the one row the general agent's trail uses - never a second rendering.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { draftRequest } from "../src/bugReportOpen.js";

const read = (n) => fs.readFileSync(path.join(process.cwd(), "src", n), "utf8");

test("the general agent and the Assistant draw steps with the same rows", () => {
  const general = read("GeneralWorkspace.jsx"), chat = read("AssistantView.jsx");
  assert.match(general, /import \{ AgentSteps \} from "\.\/AgentStepRows\.jsx"/);
  assert.match(chat, /import \{ AgentSteps \} from "\.\/AgentStepRows\.jsx"/);
  assert.doesNotMatch(general, /const StepRow = /, "one StepRow, in AgentStepRows.jsx");
  assert.match(read("AgentStepRows.jsx"), /import "\.\/agentStepRows\.css"/);
  assert.match(read("agentStepRows.css"), /\.tq-aui-step \{/);
});

test("the stream's steps are drawn while it works, and the answer keeps them - read back from history too", () => {
  const chat = read("AssistantView.jsx");
  assert.match(chat, /ev\.type === "steps"/);
  assert.match(chat, /steps: data\.steps \|\| \[\]/);
  assert.match(chat, /m\.steps\?\.length \? m\.steps : m\.card\.steps/);
});

test("what the chat could not fix is reported from what it found, not the page's last error", () => {
  const snap = { screen: "Assistant", route: "/api/concierge/say", error: "Request failed (500)", stack: "Error at x", actions: [], at: "2026-10-24T09:00:00Z" };
  const report = { message: "WhatsApp is not working: the bridge is not answering", screen: "Assistant", route: "connector whatsapp" };
  const r = draftRequest(snap, report);
  assert.equal(r.error, report.message); assert.equal(r.route, "connector whatsapp"); assert.equal(r.stack, "");
  assert.match(read("AssistantView.jsx"), /openBugReport\(c\.report \|\| shownError\(c\.text\)\)/);
});
