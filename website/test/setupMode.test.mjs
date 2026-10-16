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
  assert.match(fr, /useVerbs\("setup", \[\.\.\.navShown\.map\(/);
  // the Advisor's suggestions are typed into the catalogue's search, never buttons (2026-10-16); never "press Next" in its line
  assert.doesNotMatch(fr, /setup:open:/);
  assert.doesNotMatch(fr, /or press Next/);
  assert.match(fr, /walk: \{ label: "Walk me through my tasks"/);
  assert.match(fr, /finish: \{ label: reopened \? "Back to my day" : "Finish setup"/);
  assert.match(fr, /api\.post\("\/api\/setup\/first-run\/finish"\)/);
  assert.doesNotMatch(fr, /<Button variant="contained" disableElevation disabled=\{st\.step !== "done"\} onClick=\{onWalk\}>/, "no button of its own on the canvas");
});

test("a step on the rail takes the canvas back to it", () => {
  assert.match(read("SetupSteps.jsx"), /new CustomEvent\("tq-setup-go", \{ detail: key \}\)/);
  assert.match(read("FirstRun.jsx"), /window\.addEventListener\("tq-setup-go", on\)/);
});

test("the top bar keeps Setup after setup is done, and it opens the setup canvas", () => {
  assert.match(read("SetupWizard.jsx"), /data-tq-setup-open=""/);
  assert.match(read("AssistantView.jsx"), /setupRef\.current = \(\) => \(DEMO \? setup\(\) : setFirstRun\(true\)\);/);
});

// "on startup i still don't see ... the survey questions ... does hitting set up taskuary on assistant button put the system on
// setup mode? is it the same as setup on top right corner?" (the owner, 2026-10-16): every door is the one setup mode
test("set up Taskuary typed in the chat is setup mode too, never a card in the chat", () => {
  const av = read("AssistantView.jsx");
  assert.match(av, /if \(!DEMO\) \{ setFirstRun\(true\); return; \}/);
  assert.doesNotMatch(av, /A walk through every part of Taskuary/);
});

test("setup reopens on the first step not done, and on Your AI only when every step is", async () => {
  const { openAt } = await import("../src/setupSteps.js");
  assert.equal(openAt({ step: "done", about_done: false }, true), "about");
  assert.equal(openAt({ step: "email", brain: { name: "Claude" } }, true), "mail");
  assert.equal(openAt({ step: "done", about_done: true }, true), "ai");
  assert.equal(openAt({ step: "done", about_done: true }, false), "other");
  assert.match(read("FirstRun.jsx"), /setView\(openAt\(st, revisit \|\| st\.dismissed\)\)/);
});

// "i went back to change the ai but could not go forward again to my email without clicking the sidebar ... while it's loading the
// email it shows it's up to survey step on left sidebar ... when does it allow you to turn off setup mode? it should be after
// email/ai/survey rest is optional" (the owner, 2026-10-15)
test("the rail marks the step on the canvas, not the first one unfinished", async () => {
  const { stepsOf } = await import("../src/setupSteps.js");
  const st = { step: "reading", about_done: false, brain: { name: "Google Vertex AI" } };
  assert.equal(stepsOf(st, "mail").find((r) => r.current).key, "mail");
  assert.equal(stepsOf(st).find((r) => r.current).key, "about");
});

test("Finish is open once AI, email and About your work are done - the rest is optional - and says so until then", async () => {
  const { stepsOf, navMoves } = await import("../src/setupSteps.js");
  const fin = (st) => stepsOf(st).find((r) => r.key === "finish").sub;
  assert.match(fin({ step: "reading", about_done: false }), /after AI, email and About your work/);
  assert.match(fin({ step: "reading", about_done: true }), /ready/);
  assert.equal(navMoves({ step: "reading", about_done: true }, "other").find((m) => m.id === "finish").disabled, false);
  assert.equal(navMoves({ step: "reading", about_done: false }, "other").find((m) => m.id === "finish").disabled, true);
});

test("every step has Back and Next; Next waits for the step to be done; the last step is Finish setup alone", async () => {
  const { navMoves, frontierOf, nextOf, prevOf } = await import("../src/setupSteps.js");
  const ids = (st, v, r) => navMoves(st, v, r).map((m) => m.id + (m.disabled ? "-" : ""));
  assert.deepEqual(ids({ step: "ai" }, "ai"), ["next-"]);
  assert.deepEqual(ids({ step: "email" }, "ai"), ["next"]);
  assert.deepEqual(ids({ step: "email" }, "mail"), ["back", "next-"]);
  assert.deepEqual(ids({ step: "reading", about_done: false }, "mail"), ["back", "next"]);
  assert.deepEqual(ids({ step: "reading", about_done: false }, "about"), ["back", "next-"]);
  // no Walk me through my tasks in setup: it is the day's move once setup is finished (the owner, 2026-10-15)
  assert.deepEqual(ids({ step: "reading", about_done: true }, "other"), ["back", "finish"]);
  assert.deepEqual(ids({ step: "done", about_done: true }, "other"), ["back", "finish"]);
  assert.deepEqual(ids({ step: "reading", about_done: false }, "other"), ["back", "finish-"]);
  assert.deepEqual(ids({ step: "done", about_done: true, dismissed: true }, "mail", true), ["back", "next", "finish"]);
  assert.equal(frontierOf({ step: "email" }), "mail"); assert.equal(frontierOf({ step: "reading", about_done: false }), "about");
  assert.equal(frontierOf({ step: "done", about_done: true }), "other");
  assert.equal(nextOf("mail"), "about"); assert.equal(prevOf("about"), "mail"); assert.equal(prevOf("ai"), "ai");
});

test("saving About your work tells the rail and the top bar's chip, not only an AI or email step", () => {
  assert.match(read("FirstRun.jsx"), /const at = st && `\$\{st\.step\}\|\$\{!!st\.about_done\}`;/);
});
