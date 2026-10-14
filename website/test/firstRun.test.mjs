import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

// the owner, 2026-10-14: "first time you login the setup up taskuary on the assistant canvas ... choose model from cards, then
// choose the email connector ... setup this app in 2 steps ... Remove the popup things ... use the advisor as well to say next
// steps ... it should never drop the user"
test("setup is the assistant canvas: no dialog opens itself, the chip goes to the canvas", () => {
  const hub = read("TaskHubPage.jsx");
  assert.doesNotMatch(hub, /<SetupPanel/);
  assert.doesNotMatch(hub, /setSetupOpen\(true\)/);
  assert.match(hub, /<SetupChip state=\{setup\} onOpen=\{openSetup\} \/>/);
  const view = read("AssistantView.jsx");
  assert.match(view, /const welcome = \(m = null\) => firstRun \?/);
  assert.match(view, /<FirstRun onChanged=\{\(\) => loadPile\(true\)\} onWalk=\{\(\) => \{ setFirstRun\(false\); start\(null\); \}\} \/>/);
});

test("two steps of cards, the server's next line on top, and every wait bounded", () => {
  const fr = read("FirstRun.jsx");
  assert.match(fr, /<Next text=\{st\.next\} \/>/, "the next step is said on top, by the server");
  assert.match(fr, /Pick your AI/); assert.match(fr, /Connect your email/);
  assert.match(fr, /api\.post\("\/api\/setup\/first-run\/ai", \{ name: ai\.name \}, \{ timeout: CHECK_MS \}\)/);
  assert.match(fr, /api\.post\("\/api\/setup\/first-run\/key"/);
  assert.match(fr, /api\.post\("\/api\/setup\/first-run\/mail"/);
  assert.match(fr, /if \(Date\.now\(\) > until\) throw new Error\("the install is taking too long"\)/, "an install never spins forever");
  assert.match(fr, /<MsSignIn conn=\{ms\.conn\} cfg=\{ms\.cfg\} reload=\{loadMs\} onSignedIn=\{reload\} plain \/>/, "one Microsoft sign-in, in plain words");
  assert.match(fr, /Click the card to try again\./, "a failure always says what to press");
  assert.doesNotMatch(fr, /<Dialog|<Popover|<Drawer/);
});
