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
  assert.match(read("ConnectorsView.jsx"), /api\.post\("\/api\/setup\/first-run\/mail"/, "the Connections email card itself, in its simple mode");
  assert.match(fr, /if \(Date\.now\(\) > until\) throw new Error\("the install is taking too long"\)/, "an install never spins forever");
  assert.match(fr, /<MsSignIn conn=\{card\.conn\} cfg=\{card\.cfg\} reload=\{\(\) => load\("outlook"\)\} onSignedIn=\{reload\} plain \/>/, "one Microsoft sign-in, in plain words");
  assert.match(fr, /Click the card to try again\./, "a failure always says what to press");
  assert.doesNotMatch(fr, /<Dialog|<Popover|<Drawer/);
});

test("saving your name on the walk moves on to the next stop", () => {
  assert.match(read("assistantCards.jsx"), /card\.key === "owner" && <OwnerForm onDone=\{async \(\) => \{ await onSaved\?\.\(\); onNext\?\.\(\); \}\} \/>/);
});

// the owner, 2026-10-14: "if it's not microsoft, it should show the settings page for email in connectors. reuse our component but
// make it simple. if ai is not installed let them choose one, use the power shell to install, any errors it should handle"
test("other email is the Connections card in its simple mode, and an AI not installed installs on its click", () => {
  const fr = read("FirstRun.jsx"), cv = read("ConnectorsView.jsx");
  assert.match(fr, /<ChannelDetail simple conn=\{card\.conn\}/);
  assert.match(cv, /export function ChannelDetail\(\{[^}]*simple = false, onConnected \}\)/);
  assert.match(cv, /const SIMPLE_FIELDS = \{ gmail: \["address"\], imap: \["address", "imap_host"\] \};/);
  assert.match(fr, /if \(!ai\.installed && ai\.install && !ai\.done\) \{ install\(ai\); return; \}/);
  assert.match(fr, /Press Install to try again, or pick another AI\./);
});

// the owner, 2026-10-14: "what is this garbage ... where are the cards with choices" - Set up Taskuary opened the 13-stop walk
test("Set up Taskuary opens the two cards, open on both steps, and only a fresh install opens on them by itself", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /if \(!DEMO\) \{ setMsgs\(\(m\) => \[\.\.\.m, \{ id: `f\$\{Date\.now\(\)\}`, role: "assistant", card: \{ key: "firstrun", kind: "firstrun"/);
  assert.match(view, /firstrun: <FirstRun revisit onChanged=\{actions\.reload\} onWalk=\{\(\) => actions\.start\(null\)\} \/>/);
  assert.match(view, /data\.step !== "done" && !data\.sorted\) setFirstRun\(true\)/, "an install already sorting mail opens on its day");
  assert.match(read("FirstRun.jsx"), /\{\(s1 \|\| revisit\) && <AiStep/);
});
