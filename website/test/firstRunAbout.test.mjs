// About your work is one question a screen, filled from the mail, ending on the job description written from it (the owner,
// 2026-10-16: "about your work is too much on one screen. ask one then hit next button ... remove placeholder text").
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f) => readFileSync(new URL(`../src/${f}`, import.meta.url), "utf8");

test("the questions come one at a time: name, organisation, title, signature, systems, every mailbox, then the job", () => {
  const src = read("FirstRunAbout.jsx");
  assert.match(read("aboutWork.js"), /export const STEPS = \["name", "org", "role", "signature", "systems", "mailboxes", "job"/);
  assert.match(src, /export \{ DRAFTS, MAIL_AT, STEPS, canSkip, skipTo \} from "\.\/aboutWork\.js";/);
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
  // ...and its corner button says Next on every step (the owner, 2026-11-03) - never a word of its own per step
  assert.match(src, /const nextLabel = busy === "save" \? "Saving…" : "Next";/);
  assert.doesNotMatch(src.replace(/^\s*\/\/.*$/gm, ""), /"Looks right"|"That's all my sources"|"Save"|press Looks right/);
  assert.match(src, /if \(step === "soul"\) return save\(\);/);
});

// HOW YOU WRITE AND WHO YOU ARE (the owner, 2026-10-20): two more drafts after the job, the job's own pattern - written from the mail,
// edited, accepted - each with its state said, a failure said plainly with Write it again
// ...and WHAT YOU WORK ON after the job (the owner, 2026-11-01: a one-screen "Here's what I think you work on" at first setup) - under
// the job, on its screen, since 2026-11-06: nine questions, no longer ten
test("the job, what you work on, how you write and who you are are four drafts, each accepted as the owner leaves it", async () => {
  const src = read("FirstRunAbout.jsx");
  const { STEPS, DRAFTS, counter } = await import("../src/aboutWork.js");
  assert.deepEqual(STEPS, ["name", "org", "role", "signature", "systems", "mailboxes", "job", "style", "soul"]);
  assert.deepEqual(DRAFTS, ["job", "workstreams", "style", "soul"]);
  assert.ok(!STEPS.includes("workstreams"), "what you work on has no step of its own");
  assert.equal(counter(STEPS.indexOf("job")), "7 of 9"); assert.equal(counter(STEPS.indexOf("style")), "8 of 9"); assert.equal(counter(STEPS.length - 1), "9 of 9");
  assert.match(src, /job: "About your work", workstreams: "What you work on", style: "How you write", soul: "Who you are"/);
  assert.match(src, /About your work · \{counter\(at\)\}/);
  for (const k of ["job", "workstreams", "style", "soul"]) assert.match(src, new RegExp(`\\n  ${k}: \\{ running: "[^"]+",\\n    failed: \\(why\\) =>`), `${k} says each state`);
  assert.match(src, /\{draft\.state === "failed" && <Typography data-tq-draft-failed=""/);
  assert.match(src, /api\.post\("\/api\/setup\/first-run\/about\/accept", \{ doc: k, text: texts\[k\] \}\)/);
  assert.match(src, /\{draft\.state === "none" \? "Write it" : "Write it again"\}/);
});

// EVERY MAILBOX BEFORE THE JOB (the owner, 2026-10-20): never skipped - Skip before it lands on it - and it moves on once one is in
test("the mailbox step comes right before the job, and Skip lands on it instead of passing it", async () => {
  const src = read("FirstRunAbout.jsx");
  const { STEPS: steps, skipTo, canSkip } = await import("../src/aboutWork.js");
  const at = steps.indexOf("mailboxes");
  assert.equal(at + 1, steps.indexOf("job"), "right before the job");
  // the rule as it is stated: every question before the mailboxes skips TO them; on them there is no Skip
  for (let i = 0; i < at; i++) assert.equal(skipTo(i), at, `Skip on ${steps[i]} lands on the mailboxes`);
  assert.equal(skipTo(at + 1), null); assert.equal(canSkip("mailboxes"), false); assert.equal(canSkip("job"), true);
  assert.match(src, /const skipper = !again && canSkip\(step\),/);
  assert.match(src, /\{skipper && <Button size="small" disabled=\{!!busy\} onClick=\{skip\}/);
  assert.match(src, /if \(to !== null\) return setAt\(to\);/);
  // Next moves on only with one connected - any source, not only a mailbox - and the cards are the main source step's own
  assert.match(src, /\(step !== "mailboxes" \|\| boxes > 0\)/);
  assert.match(read("FirstRun.jsx"), /mailboxes=\{st\.sources \|\| \[\]\} mailShelf=\{mailAbout && <Shelf cards=\{mail\} more="More chat and task"/);
  // ...and the main source's cards are the server's list (firstrun.source_types: the catalogue's, email first), never a name list here
  assert.match(read("FirstRun.jsx"), /const mail = byType\(st\.source_types \|\| MAIL_TYPES\)/);
});

test("a failed email sign-in is the Advisor's line, with what to do", () => {
  assert.match(read("FirstRun.jsx"), /: st\.mail_error \? \(litCard[\s\S]{0,200}: `\$\{st\.mail_error\} Fix it in the card and press Connect again/);
});

test("while About your work is on the canvas setup's own Back and Next stand aside, and its question is the Advisor's line", () => {
  const fr = read("FirstRun.jsx");
  assert.match(fr, /const navShown = \["done", "about"\]\.includes\(view\) \? \[\] : nav;/);
  // ...and About's own Back and Next are the Nav pill's, as every step's (the owner, 2026-11-03)
  const about = read("FirstRunAbout.jsx");
  assert.match(about, /id: "about:back", group: "back"/); assert.match(about, /id: "about:next", group: "next"/);
  assert.match(fr, /<FirstRunAbout again=\{!!st\.about_done\} onBack=\{\(\) => go\("mail"\)\} onLine=\{setAboutLine\}/);
  assert.match(fr, /about: aiErr \? `\$\{aiErr\} Change AI picks one that does\.` : aboutLine \|\|/);
});

test("the job reads as a document, and Edit opens its text", () => {
  const src = read("FirstRunAbout.jsx");
  assert.match(src, /\{editing === step \|\| !text\.trim\(\)\s*\? <TextField key=\{step\} multiline/);
  // ...what you work on is a list to answer under the job, never a text box (WorkstreamsSection -> WorkstreamsConfirm)
  assert.match(src, /\{under && <WorkstreamsSection d=\{drafts\.workstreams\} text=\{texts\.workstreams\}/);
  assert.match(src, /under = step === "job";/);
  // ...the job's Edit and Write it again under the job, never under the list that follows it
  assert.match(src, /\{under && moves\.length > 0 && <Box data-tq-job-moves=""/);
  assert.match(src, /: <WorkstreamsConfirm text=\{text\} onChange=\{onChange\} \/>\}/);
  // ...each line's box keeps it, "Personal" said in words (the owner, 2026-11-03: "Personal" and "Keep" on a lone card said nothing)
  assert.match(src, /inputProps=\{\{ "aria-label": `Keep \$\{r\.name \|\| "this workstream"\}` \}\}/); assert.match(src, /label="Personal"/);
  assert.match(src, /Untick any that isn't yours to leave it out\. Tick <b>Personal<\/b> for life outside/);
  assert.match(src, /<Md text=\{text\} \/>/);
  assert.match(src, /\{editing === step \? "Done editing" : "Edit"\}/);
});

test("the first time About your work is saved, setup is complete: confetti and one big button into the day", () => {
  const fr = read("FirstRun.jsx"), done = read("SetupDone.jsx");
  // ...but only once the AI and the mail work too: saved from the rail over no AI, it went to Setup complete (2026-10-17)
  // ...by way of Developer mode, the optional step after it: its Next lands on Setup complete on that first pass (2026-11-02)
  assert.match(fr, /go\(!s \? "other" : !requiredDone\(s\) \? frontierOf\(s\) : first \? "dev" : "other"\);/);
  assert.match(fr, /go\(firstPass\.current && n === "other" \? "done" : n\)/);
  assert.match(fr, /\{q === "done" && <Box data-tq-setup-scope=""><SetupDone onDay=\{finishThen\(onFinish\)\} onMore=\{\(\) => go\("other"\)\}\s+aiError=\{aiErr\} onChangeAi=\{\(\) => go\("ai"\)\} \/><\/Box>\}/);
  assert.match(fr, /const navShown = \["done", "about"\]\.includes\(view\) \? \[\] :/);
  assert.match(done, />Setup complete</); assert.match(done, /size="large" onClick=\{onDay\}/); assert.match(done, />Go to my day</);
  assert.match(done, /prefers-reduced-motion: reduce/);
  // the AI failing on the mail is not complete: the problem, and Change AI as the one big button
  assert.match(done, /if \(aiError\) return \([\s\S]*?size="large" onClick=\{onChangeAi\}[\s\S]*?>Change AI</);
  assert.match(read("setupSteps.js"), /shown === "finish" \? \{ sub: "ready - Go to my day" \}/);
});

test("an AI connected on the Connections page says so, and the one in use leads the shelf", () => {
  const fr = read("FirstRun.jsx");
  assert.match(fr, /: ai\.connected \? \["on", "Connected - pick it to make it your AI"\]/);
  assert.match(fr, /\["on", "Your AI - it sorts what comes in"\]/);
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
  assert.match(cv, /const hits = matchCards\(groups, q\);/);
  assert.match(read("connectorCatalog.js"), /const terms = String\(q \|\| ""\)\.split\(","\)/);
  assert.match(cv, /const \[q, setQ\] = useState\(asked \|\| ""\);/);
  // what ticks it is the server's (firstrun.rail, tests/test_setup_state.py); the rail shows the row as it comes
  const { stepsOf } = await import("../src/setupSteps.js");
  const other = stepsOf({ rail: [{ key: "other", done: true, open: true, optional: true, sub: "3 connected" }] })[0];
  assert.equal(other.done, true); assert.equal(other.sub, "3 connected"); assert.equal(other.disabled, false);
});

// "pull the signature from the email and use that in emails ... have a setting so they can check it" (the owner, 2026-10-16)
test("the email signature is a setup question and a Settings field, both with a preview under an email", () => {
  const about = read("FirstRunAbout.jsx"), settings = read("SettingsView.jsx");
  assert.match(read("aboutWork.js"), /export const STEPS = \["name", "org", "role", "signature", "systems", "mailboxes", "job"/);
  assert.match(about, /data-tq-signature-preview=""/);
  assert.match(settings, /if \(m\.type === "signature"\) return <SignatureSetting/);
  assert.match(settings, /api\.post\("\/api\/signature\/learn"/);
  assert.match(read("FirstRun.jsx"), /If OpenAI says your workspace's policy denies it, use Codex/);
});

// THE JOB AND WHAT YOU WORK ON, ONE STEP (the owner, 2026-11-06): one Next keeps both, and never waits on the grouping
test("one Next on About your work keeps the job and the workstreams - the list as left once grouped, the defaults while it still runs", async () => {
  const { wsAnswer, WS_LATER } = await import("../src/aboutWork.js");
  const rows = JSON.stringify([{ slug: "northwind-finance-systems", name: "Northwind finance systems", keep: true },
    { slug: "ledger-migration", name: "Ledger migration", keep: false }, { slug: "personal", name: "Personal", personal: true }]);
  // grouped: the list exactly as the owner left it
  assert.deepEqual(wsAnswer({ state: "ready" }, rows), { doc: "workstreams", text: rows });
  // still grouping: an empty answer - the server keeps every one, none personal, once it lands (firstrun.keep_when_ready)
  assert.deepEqual(wsAnswer({ state: "running" }, ""), { doc: "workstreams", text: "" });
  // nothing to say: no call, and Next still moves on
  assert.equal(wsAnswer({ state: "failed", why: "no AI" }, ""), null); assert.equal(wsAnswer({ state: "none" }, ""), null);
  const src = read("FirstRunAbout.jsx");
  assert.match(src, /try \{ await accept\(step\); if \(step === "job"\) await acceptWs\(\); \}/);
  // Next greys only on the job being written - the grouping is not the step's draft
  assert.match(src, /const step = STEPS\[at\], draft = DRAFTS\.includes\(step\) \? drafts\[step\] : null;/);
  assert.match(src, /const ready = !!a && \(!draft \|\| draft\.state !== "running"\)/);
  // its line in place while it runs, and the small line that says Next need not wait
  assert.match(src, /\{d\.state === "running" \? <>\s*<Box[^>]*><CircularProgress size=\{14\} \/>\s*<Typography[^>]*>\{SAYS\.workstreams\.busy\}/);
  assert.match(src, /busy: "Grouping your mail into what you work on…"/);
  assert.equal(WS_LATER, "What you work on is still being read from your mail - it fills in on its own; you can change it later on About you.");
  // ...started as the step opens when the mailbox step did not queue it, once
  assert.match(src, /if \(step !== "job" \|\| !a \|\| wsStarted\.current \|\| drafts\.workstreams\.state !== "none"\) return;\s*wsStarted\.current = true; learn\(\["workstreams"\]\);/);
});

test("About you holds the same list, saved as changed - only the rows touched, so an unanswered one stays unanswered", async () => {
  const { changedRows } = await import("../src/aboutWork.js");
  const was = [{ slug: "northwind-finance-systems", name: "Northwind finance systems", kept: true },
    { slug: "ledger-migration", name: "Ledger migration", kept: false, keep: false }];
  assert.deepEqual(changedRows(was, was), []);
  assert.deepEqual(changedRows(was, [{ ...was[0], name: "Northwind finance" }, was[1]]),
    [{ slug: "northwind-finance-systems", name: "Northwind finance", personal: false, keep: true }]);
  assert.deepEqual(changedRows(was, [was[0], { ...was[1], keep: true }]), [{ slug: "ledger-migration", name: "Ledger migration", personal: false, keep: true }]);
  const you = read("AboutYou.jsx");
  assert.match(you, /import \{ WorkstreamsSection, parseWorkstreams \} from "\.\/FirstRunAbout\.jsx";/);
  assert.match(you, /<AboutWorkstreams \/>/);
  assert.match(you, /api\.put\("\/api\/about\/workstreams", \{ items: rows \}\)/);
  assert.doesNotMatch(you.slice(you.indexOf("function AboutWorkstreams"), you.indexOf("export default")), /<Button/, "no Save button - it saves as it changes");
});
