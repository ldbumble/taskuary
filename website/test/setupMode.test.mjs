// "it should be a distinct setup mode vs regular operations mode" (the owner, 2026-10-15): while setting up, the rail is the steps,
// the canvas is setup alone, the chat box and the Advisor line are off, and Finish is the owner's press in the row.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// SERVER-SHAPED STATES: which rows are done and open is the server's (firstrun.rail - tests/test_setup_state.py pins it); this file
// tests the page's part - the row on the canvas, Back/Next/Finish, where setup opens
const row = (key, done, open = true) => ({ key, done, open, optional: key === "other", need: `${key} first`, sub: "" });
const rail = (done, open, extra = {}) => ({ rail: ["ai", "mail", "about", "other", "finish"].map((k) => row(k, done.includes(k), open.includes(k))), ...extra });
const AI = rail([], ["ai", "other"], { frontier: "ai" });
const EMAIL = rail(["ai"], ["ai", "mail", "other"], { frontier: "mail" });
const READING = rail(["ai", "mail"], ["ai", "mail", "about", "other"], { frontier: "about" });
const READY = rail(["ai", "mail", "about"], ["ai", "mail", "about", "other", "finish"], { frontier: "other", ready: true });
const FINISHED = rail(["ai", "mail", "about", "finish"], ["ai", "mail", "about", "other", "finish"], { frontier: "other", ready: true, dismissed: true });

test("the steps say what is done and what is next", async () => {
  const { stepsOf } = await import("../src/setupSteps.js");
  const at = (st) => stepsOf(st).find((r) => r.current)?.key;
  assert.equal(at(AI), "ai");
  assert.equal(at(EMAIL), "mail");
  assert.equal(at(READING), "about");
  assert.equal(at(READY), "finish");
  assert.deepEqual(stepsOf({ step: "ai" }), [], "no rail from the server, no rows made up here");
});

test("setup mode: the steps for a rail, setup alone on the canvas, no chat box, no Advisor line", () => {
  const av = read("AssistantView.jsx");
  assert.match(av, /setupMode=\{firstRun\} setupRail=\{firstRun \? <SetupSteps \/> : null\}/);
  // ...setup alone, and still mounted - hidden - under a page or a task opened over it (W2, 2026-10-21)
  assert.match(av, /\{firstRun \? state && <div data-tq-setup-under=\{setupCovered\.current \? "hidden" : ""\} style=\{setupCovered\.current \? \{ display: "none" \} : undefined\}>\{welcome\(\)\}<\/div>\s+: state && !shown\.length && !busy && !starting && welcome\(\)\}/);
  assert.match(av, /\{!firstRun && shown\.map/);
  assert.match(av, /className="tq-compose-box" style=\{firstRun \? \{ display: "none" \} : undefined\}/);
  // ...no Advisor line over setup itself - but a task opened over it is the item in view, and speaks (2026-10-26)
  assert.match(av, /tableOf\(\{ current, cardKey, foldedKey, browsing, setup: setupOn\.current, over: !!setupCard \}\)/);
  assert.match(av, /\{firstRun && !setupCard && <SetupLine \/>\}/);
  assert.match(av, /const shownAdvice = table\.speaks && !litNow \? adviceShown/);
  assert.match(read("FeedView.jsx"), /display: setupMode \? "none" : "flex"/);
});

test("Finish setup and Walk me through my tasks are row verbs, and both finish setup on the server", () => {
  const fr = read("FirstRun.jsx");
  assert.match(fr, /useVerbs\("setup", \[\.\.\.navShown\.map\(/);
  // the Advisor's suggestions are typed into the catalogue's search, never buttons (2026-10-16); never "press Next" in its line
  assert.doesNotMatch(fr, /setup:open:/);
  assert.doesNotMatch(fr, /or press Next/);
  assert.match(fr, /walk: \{ label: btnLabel\("walk"\)/);
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
  // ...over whatever was opened on it: the page or the task goes, and setup is there as it was left (W2)
  assert.match(read("AssistantView.jsx"), /setupRef\.current = \(\) => \{ if \(DEMO\) \{ setup\(\); return; \} setFirstRun\(true\); backToSetup\(\); \};/);
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
  assert.equal(openAt(READING, true), "about");
  assert.equal(openAt(EMAIL, true), "mail");
  assert.equal(openAt(READY, true), "ai");
  assert.equal(openAt(READY, false), "other");
  assert.match(read("FirstRun.jsx"), /setView\(openAt\(st, revisit \|\| st\.dismissed\)\)/);
});

// "i went back to change the ai but could not go forward again to my email without clicking the sidebar ... while it's loading the
// email it shows it's up to survey step on left sidebar ... when does it allow you to turn off setup mode? it should be after
// email/ai/survey rest is optional" (the owner, 2026-10-15)
test("the rail marks the step on the canvas, not the first one unfinished", async () => {
  const { stepsOf } = await import("../src/setupSteps.js");
  assert.equal(stepsOf(READING, "mail").find((r) => r.current).key, "mail");
  assert.equal(stepsOf(READING).find((r) => r.current).key, "about");
});

test("Finish is open once AI, email and About your work are done - the rest is optional - and says so until then", async () => {
  const { stepsOf, navMoves } = await import("../src/setupSteps.js");
  // on Setup complete the rail points at its Go to my day
  assert.equal(stepsOf(READY, "finish").find((r) => r.key === "finish").sub, "ready - Go to my day");
  assert.equal(navMoves(READY, "other").find((m) => m.id === "finish").disabled, false);
  assert.equal(navMoves(READING, "other").find((m) => m.id === "finish").disabled, true);
});

test("every step has Back and Next; Next waits for the step to be done; the last step is Finish setup alone", async () => {
  const { navMoves, frontierOf, nextOf, prevOf } = await import("../src/setupSteps.js");
  const ids = (st, v, r) => navMoves(st, v, r).map((m) => m.id + (m.disabled ? "-" : ""));
  assert.deepEqual(ids(AI, "ai"), ["next-"]);
  assert.equal(navMoves(AI, "ai")[0].why, "ai first", "Next says what it waits for, in the server's words");
  assert.deepEqual(ids(EMAIL, "ai"), ["next"]);
  assert.deepEqual(ids(EMAIL, "mail"), ["back", "next-"]);
  assert.deepEqual(ids(READING, "mail"), ["back", "next"]);
  assert.deepEqual(ids(READING, "about"), ["back", "next-"]);
  // no Walk me through my tasks in setup: it is the day's move once setup is finished (the owner, 2026-10-15)
  assert.deepEqual(ids(READY, "other"), ["back", "finish"]);
  assert.deepEqual(ids(READING, "other"), ["back", "finish-"]);
  assert.deepEqual(ids(FINISHED, "mail", true), ["back", "next", "finish"]);
  assert.equal(frontierOf(EMAIL), "mail"); assert.equal(frontierOf(READING), "about"); assert.equal(frontierOf(null), "ai");
  assert.equal(nextOf("mail"), "about"); assert.equal(prevOf("about"), "mail"); assert.equal(prevOf("ai"), "ai");
});

test("saving About your work tells the rail and the top bar's chip, not only an AI or email step", () => {
  assert.match(read("FirstRun.jsx"), /const at = st && `\$\{st\.step\}\|\$\{!!st\.about_done\}`;/);
});

// the non-coder audit, 2026-10-17: About your work pressed on the rail from Your AI, then saved, put "Setup complete" over a day with
// no AI and no mail - and "Finish" ticked on a setup put away early
test("a rail row past what is done waits and says for what; Finish ticks only when finished and the three are done", async () => {
  const { stepsOf, reachable } = await import("../src/setupSteps.js");
  const row = (st, k) => stepsOf(st).find((r) => r.key === k);
  // what a waiting row says, and when Finish ticks, are the server's (firstrun.rail); the page disables what is not open
  assert.equal(row(AI, "about").disabled, true); assert.equal(row(AI, "mail").disabled, true);
  assert.equal(row(AI, "other").disabled, false, "the optional ones never wait");
  assert.equal(row(READING, "about").disabled, false);
  assert.equal(reachable(AI, "about"), false); assert.equal(reachable(EMAIL, "mail"), true);
  const fr = read("FirstRun.jsx");
  assert.match(fr, /if \(!stRef\.current \|\| reachable\(stRef\.current, v\)\) go\(v\);/, "the canvas guards the jump too");
  assert.match(read("SetupSteps.jsx"), /disabled=\{!!r\.disabled\}/);
  // ...and the server refuses Finish while there is no AI or no mail; the canvas says why instead of moving on
  assert.match(fr, /if \(e\?\.response\?\.status === 409\) \{ setErr\(errText\(e\)\); return; \}/);
});

// the 2026-10-19 UI walk: Back from More connections opened About your work while the email was not in yet - a locked step the rail
// itself refuses - and the Advisor spoke about answers never given. Back steps over a locked step; every go() lands on an open one.
test("Back never lands on a locked step, and no move does", async () => {
  const { prevOf, landOn } = await import("../src/setupSteps.js");
  assert.equal(prevOf("other", EMAIL), "mail", "About your work waits for the email: Back from More connections is the email");
  assert.equal(prevOf("other", AI), "ai", "...and with no AI, the AI");
  assert.equal(prevOf("other", READING), "about", "an open step is still the step before");
  assert.equal(prevOf("about", EMAIL), "mail");
  assert.equal(landOn(EMAIL, "about"), "mail"); assert.equal(landOn(READING, "about"), "about");
  assert.equal(landOn(AI, "done"), "done", "Setup complete is not a rail step");
  assert.equal(landOn(null, "about"), "about", "before the state is read nothing is refused");
  const fr = read("FirstRun.jsx");
  assert.match(fr, /const go = useCallback\(\(v\) => \{ setView\(landOn\(stRef\.current, v\)\);/, "go() is the one road onto the canvas");
  assert.match(fr, /run: \(\) => go\(prevOf\(view, st\)\)/);
});
