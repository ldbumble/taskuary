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

// the owner, 2026-10-15: "Don't create new ui. keep the same as we have in connections but just show them/tell what to do next
// using the advisor ... like what ai do you have? what email do you have? any other connection you would like to setup"
test("three questions on the Advisor's line, each answered on the Connections page's own cards", () => {
  const fr = read("FirstRun.jsx"), cv = read("ConnectorsView.jsx");
  assert.match(fr, /<Ask text=\{said \|\| err \|\| \(redo \?[\s\S]{0,120}: st\.next\)\} \/>/, "the question is said on top, by the server");
  assert.match(fr, /className="tq-next"/, "in the Advisor's own line, not a box of our own");
  assert.match(fr, /import \{ CardGrid, ChannelDetail, ConnCard, connCardOf \} from "\.\/ConnectorsView\.jsx";/);
  assert.match(cv, /export const ConnCard = /); assert.match(cv, /export const connCardOf = /);
  assert.doesNotMatch(fr, /function Card\(|borderRadius: "12px"|<TextField/, "no card or form of our own");
  assert.match(fr, /const FIRST = 4;/, "four cards, then More");
  assert.match(fr, /api\.post\("\/api\/setup\/first-run\/ai", \{ name: ai\.name \}, \{ timeout: CHECK_MS \}\)/);
  assert.match(cv, /api\.post\("\/api\/setup\/first-run\/key", \{ type: conn\.Type, key: secret, cid: conn\.ConnectorId, config: cfg \}/);
  assert.match(cv, /api\.post\("\/api\/setup\/first-run\/mail"/, "the Connections email card itself, in its simple mode");
  assert.match(cv, /if \(conn\.Type === "outlook"\) return <MsSignIn conn=\{conn\} cfg=\{cfg\} reload=\{reload\} onSignedIn=\{onConnected\} plain \/>;/);
  assert.match(fr, /if \(Date\.now\(\) > until\) throw new Error\("the install is taking too long"\)/, "an install never spins forever");
  assert.match(fr, /Click the card to try again\./, "a failure always says what to press");
  assert.doesNotMatch(fr, /<Dialog|<Popover|<Drawer/);
});

// the owner, 2026-10-15: plain words on the setup screen only - never "off · trigger + tool · 0/0 chat jids"
test("on the setup screen the same cards say their state in plain words; Connections keeps its own", () => {
  const fr = read("FirstRun.jsx"), cv = read("ConnectorsView.jsx");
  assert.match(cv, /export const connCardOf = \(c, sources, go, plain = false\) =>/, "a mode of the shared card, not a copy");
  assert.match(cv, /const connState = \(c\) => \(c\.state \|\|/, "a plain card carries its state, its words are not parsed");
  for (const w of ["Not set up", "Connected", "Needs sign-in", "Not answering"]) assert.match(cv, new RegExp(`"${w}`), w);
  assert.match(fr, /connCardOf\(c, sources, \(\) => setOpen[^\n]*, true\)/, "every connector card on the setup screen is plain");
  assert.doesNotMatch(fr, /last test failed|not set up/, "the CLI cards use the same plain words");
  assert.match(cv, /chanCard = \(c\) => connCardOf\(c, sources, \(\) => setOpen\(\{ kind: "connector", id: c\.ConnectorId \}\)\);/, "Connections is unchanged");
});

test("the rail and the top bar's chip say what is next from the first run's own state", () => {
  const view = read("AssistantView.jsx"), chip = read("SetupWizard.jsx");
  assert.match(view, /\{tx\("Setup:"\)\} \{settingUp\}/);
  assert.match(view, /setSetupTodo\(data\?\.todo/);
  assert.match(chip, /`Setup: \$\{state\.first_todo\}`/);
  assert.doesNotMatch(view + chip, /two setup steps|Set up · \$\{left\} step/);
});

test("the cards wear their logos: each CLI its maker's, Gemini its own", () => {
  const fr = read("FirstRun.jsx");
  assert.match(fr, /const CLI_LOGO = \{ claude: "anthropic", codex: "openai", gemini: "gemini", copilot: "github" \};/);
  assert.match(read("logos.jsx"), /^ {2}gemini: \(p\) => \(/m);
});

test("a failed pick keeps its Sign in and the line saying so, and Gmail links to its App Password page", () => {
  const fr = read("FirstRun.jsx"), cv = read("ConnectorsView.jsx");
  assert.match(fr, /fix\?\.fix === "signin" && fix\.setup/, "the fix is the server's, so a reload keeps it");
  assert.match(fr, /Sign in to \$\{fix\.title\}/);
  assert.match(cv, /href="https:\/\/myaccount\.google\.com\/apppasswords"/);
  assert.doesNotMatch(cv.match(/const SIMPLE_HINT = [\s\S]*?\n\};/)[0], /Credentials|imap->smtp/);
});

test("saving your name on the walk moves on to the next stop", () => {
  assert.match(read("assistantCards.jsx"), /card\.key === "owner" && <OwnerForm onDone=\{async \(\) => \{ await onSaved\?\.\(\); onNext\?\.\(\); \}\} \/>/);
});

// the owner, 2026-10-14: "if it's not microsoft, it should show the settings page for email in connectors. reuse our component but
// make it simple. if ai is not installed let them choose one, use the power shell to install, any errors it should handle"
test("other email is the Connections card in its simple mode, and an AI not installed installs on its click", () => {
  const fr = read("FirstRun.jsx"), cv = read("ConnectorsView.jsx");
  assert.match(fr, /<ChannelDetail key=\{conn\.ConnectorId\} conn=\{conn\} sources=\{sources\} reload=\{reload\} simple=\{open\.simple\}/);
  assert.match(cv, /export function ChannelDetail\(\{[^}]*simple = false, onConnected \}\)/);
  assert.match(cv, /const SIMPLE_FIELDS = \{ gmail: \["address"\], imap: \["address", "imap_host"\] \};/);
  assert.match(fr, /if \(!ai\.installed && ai\.install && !ai\.done\) \{ install\(ai\); return; \}/);
  assert.match(fr, /Click its card to try again, or pick another AI\./);
});

// the owner, 2026-10-14: "what is this garbage ... where are the cards with choices" - Set up Taskuary opened the 13-stop walk
test("Set up Taskuary opens the two cards, open on both steps, and only a fresh install opens on them by itself", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /if \(!DEMO\) \{ setMsgs\(\(m\) => \[\.\.\.m, \{ id: `f\$\{Date\.now\(\)\}`, role: "assistant", card: \{ key: "firstrun", kind: "firstrun"/);
  assert.match(view, /firstrun: <FirstRun revisit onChanged=\{actions\.reload\} onWalk=\{\(\) => actions\.start\(null\)\} \/>/);
  assert.match(view, /data\.step !== "done" && !data\.sorted\) setFirstRun\(true\)/, "an install already sorting mail opens on its day");
  assert.match(read("FirstRun.jsx"), /const shelf = \(k, cards, more\) => \(revisit \|\| q === k\) &&/);
  assert.match(view, /c\?\.kind === "firstrun" \? "firstrun"/, "the card is routed to FirstRun, not drawn as an empty message");
});
