import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

// EVERY "NO AI CONNECTED" MESSAGE HAS A CONNECT AN AI BUTTON (owner-approved, 2026-10-21, the UI/UX audit's W11): each said an AI was
// needed and gave nothing to press, and a fresh install's rail said "All done" over a day in which nothing could be judged.
const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");

test("Connect an AI opens Connections at the AI cards", () => {
  const c = src("ConnectAi.jsx");
  assert.match(c, /openAppLink\(place\("ai"\)\.href\)/);
  assert.match(c, /export const CONNECT_AI = "Connect an AI"/);
});

test("each no-AI line carries the button", () => {
  for (const [file, near] of [
    ["GeneralWorkspace.jsx", /No AI is connected, so this work cannot run yet/],
    // (not the profile editor: a profile is a name and instructions and runs on no AI of its own - the owner, 2026-10-22)
    ["ui.jsx", /brainsRead && !generalBrains\.length && <ConnectAi/],
    ["NewSheet.jsx", /action=\{errAi \? <ConnectAi/],
    ["NewPlaybookDialog.jsx", /action=\{noAi \? <ConnectAi/],
    ["DigestText.jsx", /noAi \? <ConnectAi/],
    // (not a connection's Get AI to set it up any more: it opens the chat, whose own no-AI answer carries the button - 2026-10-30)
  ]) {
    const s = src(file);
    assert.match(s, /import ConnectAi/, `${file} imports the button`);
    assert.match(s, near, file);
  }
  // the composer's miss is the page's answer the Assistant hears and says in the chat (2026-10-30: the describe box is the chat's now)
  assert.match(src("ReportsView.jsx"), /viewResult\(\{ action: "compose", ok: false/);
});

test("the rail never says All done when no AI could judge anything", () => {
  const v = src("AssistantView.jsx");
  const noAi = v.indexOf("!drawn.length && noAi"), done = v.indexOf("<b>All done</b>");
  assert.ok(noAi > 0 && noAi < done, "the no-AI empty rail is decided before All done");
  assert.match(v, /noAi=\{!!state && !\(state\.providers \|\| \[\]\)\.length\}/);
  assert.match(v.slice(noAi, done), /data-tq-connect-ai[^>]*onClick=\{connectAi\}/);
});

test("Plan it with no AI says so instead of promising steps", () => {
  const s = src("NewSheet.jsx");
  assert.match(s, /if \(plan && !\(\(await api\.get\("\/api\/agents"\)\)/);
  assert.match(s, /setErr\(NO_AI_PLAN\); setErrAi\(true\)/);
});
