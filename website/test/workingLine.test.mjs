// A REAL ANSWER COUNTS ITS SECONDS (the owner, 2026-10-20: "working... Ns"): a CLI brain took 4-51 s behind three silent dots,
// which read as hung. The count joins the dots on a typed ask's real answer - never the demo's script, never Next or the phone -
// and lives in its own component, so the chat around it does not redraw every second.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { workingLine } from "../src/agentWork.js";

const src = fs.readFileSync(path.join(import.meta.dirname, "../src/AssistantView.jsx"), "utf8");

test("nothing in the first second, then whole seconds that never run ahead", () => {
  assert.equal(workingLine(0), "");
  assert.equal(workingLine(999), "");
  assert.equal(workingLine(1000), "Working… 1s");
  assert.equal(workingLine(6999), "Working… 6s");
  assert.equal(workingLine(65400), "Working… 1m 05s");
});

test("the count rides beside the dots only where Stop does: a typed ask's real answer", () => {
  // the pending line's dots - not a held line's (Line), which draws the same dots without the clock (the owner, 2026-10-30)
  const at = src.indexOf('<span className="tq-typing"><i /><i /><i /></span>', src.indexOf("const pendingLine"));
  assert.ok(at > 0);
  const bubble = src.slice(at, src.indexOf("</div>", at));
  assert.match(bubble, /\{busy && answering\.current && !DEMO && <WorkingFor \/>\}/);
  assert.equal((src.match(/<WorkingFor \/>/g) || []).length, 1);
});

test("its clock is its own: the per-second state never reaches AssistantView", () => {
  const fn = src.slice(src.indexOf("function WorkingFor()"), src.indexOf("function AdvisorNotes"));
  assert.match(fn, /setInterval\(\(\) => setNow\(Date\.now\(\)\), 1000\)/);
  assert.match(fn, /clearInterval/);
  const view = src.slice(src.indexOf("export default function AssistantView"));
  assert.doesNotMatch(view, /workingLine\(/);
});
