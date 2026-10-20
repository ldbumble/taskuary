// About your work is one question a screen, filled from the mail, ending on the job description written from it (the owner,
// 2026-10-16: "about your work is too much on one screen. ask one then hit next button ... remove placeholder text").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the questions come one at a time: name, organisation, title, signature, systems, every mailbox, then the job", () => {
  const src = read("FirstRunAbout.jsx");
  assert.match(src, /export const STEPS = \["name", "org", "role", "signature", "systems", "mailboxes", "job"/);
  assert.match(src, /useVerbs\("setup-about", a \? \[/, "its own Back and Next in the row");
  assert.match(src, /&& \(!x\[k\] \|\| \(data\.guessed \|\| \[\]\)\.includes\(k\)\)\)/, "the mail fills only empty boxes and the guessed name");
  assert.doesNotMatch(src, /placeholder=/, "a box is filled from the mail or empty - never a sample answer that reads as one");
});

test("the job is written once the title is answered, and the last press saves what the owner left", () => {
  const src = read("FirstRunAbout.jsx");
  assert.match(src, /if \(step === "role" && who\(a, mailboxes\) !== learnedFor\.current\) learn\(\["job"\]\);/);
  // ...and all three drafts as the mailbox step is passed - the job again when a mailbox came in since: it is read from every one
  assert.match(src, /if \(step === "mailboxes"\) learn\(who\(a, mailboxes\) !== learnedFor\.current \? DRAFTS : DRAFTS\.filter\(\(k\) => k !== "job" && drafts\[k\]\.state === "none"\)\);/);
  assert.match(src, /\.\.\.boxes\.map\(\(b\) => b\.address\.toLowerCase\(\)\)\.sort\(\)/);
  assert.match(src, /api\.post\("\/api\/setup\/first-run\/about\/learn", \{ \.\.\.x, docs \}\)/);
  assert.match(src, /api\.get\("\/api\/setup\/first-run\/about\/drafts"\)/);
  assert.match(src, /const nextLabel = busy === "save" \? "Saving…" : draft \? \(draft\.state === "ready" \? "Looks right" : last \? "Save" : "Next"\)/);
  assert.match(src, /if \(step === "soul"\) return save\(\);/);
});

// HOW YOU WRITE AND WHO YOU ARE (the owner, 2026-10-20): two more drafts after the job, the job's own pattern - written from the mail,
// edited, accepted - each with its state said, a failure said plainly with Write it again
test("the job, how you write and who you are are three drafts in a row, each accepted as the owner leaves it", () => {
  const src = read("FirstRunAbout.jsx");
  assert.match(src, /export const STEPS = \[[^\]]*"mailboxes", "job", "style", "soul"\];/);
  assert.match(src, /export const DRAFTS = \["job", "style", "soul"\];/);
  assert.match(src, /style: "How you write", soul: "Who you are"/);
  assert.match(src, /About your work · \{at \+ 1\} of \{STEPS\.length\}/);
  for (const k of ["job", "style", "soul"]) assert.match(src, new RegExp(`\\n  ${k}: \\{ running: "[^"]+",\\n    failed: \\(why\\) =>`), `${k} says each state`);
  assert.match(src, /\{draft\.state === "failed" && <Typography data-tq-draft-failed=""/);
  assert.match(src, /api\.post\("\/api\/setup\/first-run\/about\/accept", \{ doc: k, text: texts\[k\] \}\)/);
  assert.match(src, /\{draft\.state === "none" \? "Write it" : "Write it again"\}/);
});

// EVERY MAILBOX BEFORE THE JOB (the owner, 2026-10-20): never skipped - Skip before it lands on it - and it moves on once one is in
test("the mailbox step comes right before the job, and Skip lands on it instead of passing it", () => {
  const src = read("FirstRunAbout.jsx");
  const body = src.slice(src.indexOf("export const STEPS")), steps = JSON.parse(body.slice(body.indexOf("["), body.indexOf("]") + 1));
  const at = steps.indexOf("mailboxes");
  assert.equal(at + 1, steps.indexOf("job"), "right before the job");
  // the rule as the component states it: every question before the mailboxes skips TO them; on them there is no Skip
  assert.match(src, /export const skipTo = \(at\) => \(at < MAIL_AT \? MAIL_AT : null\);/);
  assert.match(src, /export const canSkip = \(step\) => step !== "mailboxes";/);
  const skipTo = (i) => (i < at ? at : null);
  for (let i = 0; i < at; i++) assert.equal(skipTo(i), at, `Skip on ${steps[i]} lands on the mailboxes`);
  assert.match(src, /\{!again && canSkip\(step\) && <Box><Button size="small" disabled=\{!!busy\} onClick=\{skip\}/);
  assert.match(src, /if \(to !== null\) return setAt\(to\);/);
  // "That's all my mail" moves on only with one connected, and the cards are the email step's own
  assert.match(src, /\(step !== "mailboxes" \|\| boxes > 0\)/);
  assert.match(src, /step === "mailboxes" \? "That's all my mail" : "Next"/);
  assert.match(read("FirstRun.jsx"), /mailboxes=\{st\.mailboxes \|\| \[\]\} mailShelf=\{mailAbout && <Shelf cards=\{mail\} more="More email"/);
});

test("a failed email sign-in is the Advisor's line, with what to do", () => {
  assert.match(read("FirstRun.jsx"), /: st\.mail_error \? \(litCard[\s\S]{0,200}: `\$\{st\.mail_error\} Fix it in the card and press Connect again/);
});

test("while About your work is on the canvas setup's own Back and Next stand aside, and its question is the Advisor's line", () => {
  const fr = read("FirstRun.jsx");
  assert.match(fr, /view === "about" \? nav\.filter\(\(m\) => m\.id === "finish"\) : nav;/);
  assert.match(fr, /<FirstRunAbout again=\{!!st\.about_done\} onBack=\{\(\) => go\("mail"\)\} onLine=\{setAboutLine\}/);
  assert.match(fr, /about: aiErr \? `\$\{aiErr\} Change AI picks one that does\.` : aboutLine \|\|/);
});

test("the job reads as a document, and Edit opens its text", () => {
  const src = read("FirstRunAbout.jsx");
  assert.match(src, /\{editing === step \|\| !text\.trim\(\)\s*\? <TextField key=\{step\} multiline/);
  assert.match(src, /<Md text=\{text\} \/>/);
  assert.match(src, /\{editing === step \? "Done editing" : "Edit"\}/);
});

test("the first time About your work is saved, setup is complete: confetti and one big button into the day", () => {
  const fr = read("FirstRun.jsx"), done = read("SetupDone.jsx");
  // ...but only once the AI and the mail work too: saved from the rail over no AI, it went to Setup complete (2026-10-17)
  assert.match(fr, /go\(!s \? "other" : !requiredDone\(s\) \? frontierOf\(s\) : first \? "done" : "other"\);/);
  assert.match(fr, /\{q === "done" && <Box data-tq-setup-scope=""><SetupDone onDay=\{finishThen\(onFinish\)\} onMore=\{\(\) => go\("other"\)\}\s+aiError=\{aiErr\} onChangeAi=\{\(\) => go\("ai"\)\} \/><\/Box>\}/);
  assert.match(fr, /const navShown = view === "done" \? \[\] :/);
  assert.match(done, />Setup complete</); assert.match(done, /size="large" onClick=\{onDay\}/); assert.match(done, />Go to my day</);
  assert.match(done, /prefers-reduced-motion: reduce/);
  // the AI failing on the mail is not complete: the problem, and Change AI as the one big button
  assert.match(done, /if \(aiError\) return \([\s\S]*?size="large" onClick=\{onChangeAi\}[\s\S]*?>Change AI</);
  assert.match(read("setupSteps.js"), /shown === "finish" \? \{ sub: "ready - Go to my day" \}/);
});

test("an AI connected on the Connections page says so, and the one in use leads the shelf", () => {
  const fr = read("FirstRun.jsx");
  assert.match(fr, /: ai\.connected \? \["on", "Connected - pick it to make it your AI"\]/);
  assert.match(fr, /\["on", "Your AI - it sorts your mail"\]/);
  assert.match(fr, /const ai = inUse \? \[\.\.\.all\.filter\(using\), \.\.\.lead\.filter\(\(c\) => !using\(c\)\)\] : lead;/);
  // ...matched by its connection, not its name: "ChatGPT (your plan)" never matched the card titled ChatGPT (2026-10-17)
  assert.match(fr, /const inUseCid = \(c\) => st\.step !== "ai" && st\.brain\?\.pick === `connector:\$\{c\.ConnectorId\}`;/);
});

// "No such buttons. If it suggest systems then you can do it in search ... don't like new buttons besides for what there was before"
// (the owner, 2026-10-16) - and More connections ticks once something beyond the AI and the mail is connected
test("More connections suggests in the catalogue's search, never as row buttons, and ticks by what is connected", async () => {
  const fr = read("FirstRun.jsx"), cv = read("ConnectorsView.jsx");
  assert.doesNotMatch(fr, /setup:open:/, "no suggestion buttons in the row");
  assert.match(fr, /setBrowseSt\(\{ q: names\.join\(", "\), section: null, open: null \}\)/);
  assert.match(cv, /const terms = q\.split\(","\)/);
  assert.match(cv, /const \[q, setQ\] = useState\(asked \|\| ""\);/);
  // what ticks it is the server's (firstrun.rail, tests/test_setup_state.py); the rail shows the row as it comes
  const { stepsOf } = await import("../src/setupSteps.js");
  const other = stepsOf({ rail: [{ key: "other", done: true, open: true, optional: true, sub: "3 connected" }] })[0];
  assert.equal(other.done, true); assert.equal(other.sub, "3 connected"); assert.equal(other.disabled, false);
});

// "pull the signature from the email and use that in emails ... have a setting so they can check it" (the owner, 2026-10-16)
test("the email signature is a setup question and a Settings field, both with a preview under an email", () => {
  const about = read("FirstRunAbout.jsx"), settings = read("SettingsView.jsx");
  assert.match(about, /export const STEPS = \["name", "org", "role", "signature", "systems", "mailboxes", "job"/);
  assert.match(about, /data-tq-signature-preview=""/);
  assert.match(settings, /if \(m\.type === "signature"\) return <SignatureSetting/);
  assert.match(settings, /api\.post\("\/api\/signature\/learn"/);
  assert.match(read("FirstRun.jsx"), /If OpenAI says your workspace's policy denies it, use Codex/);
});
