// "it should be a distinct setup mode vs regular operations mode" (the owner, 2026-10-15): while setting up, the rail is the steps,
// the canvas is setup alone, the chat box and the Advisor line are off, and Finish is the owner's press in the row.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the steps say what is done and what is next", async () => {
  const { stepsOf } = await import("../src/setupSteps.js");
  const at = (st) => stepsOf(st).find((r) => r.current)?.key;
  assert.equal(at({ step: "ai" }), "ai");
  assert.equal(at({ step: "email", brain: { name: "Claude" } }), "mail");
  assert.equal(at({ step: "reading", about_done: false }), "about");
  assert.equal(at({ step: "done", about_done: true }), "finish");
});

test("setup mode: the steps for a rail, setup alone on the canvas, no chat box, no Advisor line", () => {
  const av = read("AssistantView.jsx");
  assert.match(av, /setupMode=\{firstRun\} setupRail=\{firstRun \? <SetupSteps \/> : null\}/);
  assert.match(av, /\{firstRun \? state && welcome\(\) : state && !shown\.length && !busy && welcome\(\)\}/);
  assert.match(av, /\{!firstRun && shown\.map/);
  assert.match(av, /className="tq-compose-box" style=\{firstRun \? \{ display: "none" \} : undefined\}/);
  assert.match(av, /const shownAdvice = setupOn\.current \? null : adviceShown/);
  assert.match(read("FeedView.jsx"), /display: setupMode \? "none" : "flex"/);
});

test("Finish setup and Walk me through my tasks are row verbs, and both finish setup on the server", () => {
  const fr = read("FirstRun.jsx");
  assert.match(fr, /useVerbs\("setup", \[/);
  assert.match(fr, /id: "setup:walk", label: "Walk me through my tasks"/);
  assert.match(fr, /id: "setup:finish", label: reopened \? "Back to my day" : "Finish setup"/);
  assert.match(fr, /api\.post\("\/api\/setup\/first-run\/finish"\)/);
  assert.doesNotMatch(fr, /<Button variant="contained" disableElevation disabled=\{st\.step !== "done"\} onClick=\{onWalk\}>/, "no button of its own on the canvas");
});

test("a step on the rail takes the canvas back to it", () => {
  assert.match(read("SetupSteps.jsx"), /new CustomEvent\("tq-setup-go", \{ detail: key \}\)/);
  assert.match(read("FirstRun.jsx"), /window\.addEventListener\("tq-setup-go", go\)/);
});

test("the top bar keeps Setup after setup is done, and it opens the setup canvas", () => {
  assert.match(read("SetupWizard.jsx"), /data-tq-setup-open=""/);
  assert.match(read("AssistantView.jsx"), /setupRef\.current = \(\) => setFirstRun\(true\);/);
});
