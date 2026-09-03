// "New task for the agent" has one question that decides everything under it: which repository.
// It opened in a terminal whatever you answered - including "General - no repository, just a
// question to answer", which has no checkout for a CLI to stand in and belongs in the chat.
import assert from "node:assert/strict";
import test from "node:test";
import { ASK_TAG, BROWSER_TAG, NO_REPO, planTask, repoOf, wantsAsk, wantsBrowser, withoutAsk } from "../src/newTask.js";

test("a repository means a coding task for a CLI in that checkout", () => {
  const p = planTask("acme/fanapp", "live");
  assert.equal(p.kind, "coding");
  assert.equal(p.chat, false);
  assert.equal(p.repo, "acme/fanapp");
  assert.equal(p.tags, "repo:acme/fanapp");
});

test("General means a general task, worked in the assistant's chat", () => {
  const p = planTask(NO_REPO, "live");
  assert.equal(p.kind, "general");
  assert.equal(p.chat, true);
  assert.equal(p.repo, null);
});

test("the question to ask rides ON the task, so no navigation can lose it", () => {
  const p = planTask(NO_REPO, "live");
  assert.equal(p.ask, true);
  assert.equal(p.tags, ASK_TAG);
  assert.equal(wantsAsk({ Tags: p.tags }), true);
});

test("only 'Ask the assistant' asks - filing it and the terminal do not", () => {
  assert.equal(planTask(NO_REPO, "file").tags, null);
  assert.equal(planTask(NO_REPO, "terminal").ask, false);
  assert.equal(wantsAsk({ Tags: "repo:acme/fanapp" }), false);
  assert.equal(wantsAsk({}), false);
});

test("the marker is stripped once the question has been asked, and nothing else is", () => {
  assert.equal(withoutAsk(`repo:acme/fanapp,${ASK_TAG}`), "repo:acme/fanapp");
  assert.equal(withoutAsk(ASK_TAG), "");
  assert.equal(withoutAsk(""), "");
  assert.equal(wantsAsk({ Tags: withoutAsk(ASK_TAG) }), false);
});

test("a tag that merely CONTAINS the marker is not the marker", () => {
  assert.equal(wantsAsk({ Tags: "ask:assistant-later" }), false);
});

test("no repository is never written as a repo tag", () => {
  // 'repo:none' was a tag pointing at nothing; the ask marker is the only tag a General task wears
  for (const pick of [NO_REPO, ""]) assert.equal(planTask(pick, "live").tags, ASK_TAG);
  assert.equal(planTask(NO_REPO, "file").tags, null);
  assert.match(String(planTask("acme/fanapp", "live").tags), /^repo:/);
});

test("an empty picker - no repositories connected at all - is the chat, not a terminal", () => {
  assert.equal(planTask("", "live").chat, true);
  assert.equal(planTask(undefined, "live").kind, "general");
});

test("a question can still be worked in a terminal, when that is asked for", () => {
  const p = planTask(NO_REPO, "terminal");
  assert.equal(p.kind, "coding");          // a terminal task, so the task page shows one
  assert.equal(p.chat, false);
  assert.equal(p.start, true);
  assert.equal(p.repo, null);              // ...and still no repository invented for it
  assert.equal(p.tags, null);
});

test("'just file it' starts nobody, on either kind", () => {
  assert.equal(planTask("acme/fanapp", "file").start, false);
  assert.equal(planTask(NO_REPO, "file").start, false);
  assert.equal(planTask(NO_REPO, "live").start, true);
});

test("a task can say it needs a browser, on either kind", () => {
  assert.equal(planTask("acme/fanapp", "live", true).tags, `repo:acme/fanapp,${BROWSER_TAG}`);
  assert.equal(planTask(NO_REPO, "live", true).tags, `${ASK_TAG},${BROWSER_TAG}`);
  assert.equal(planTask(NO_REPO, "terminal", true).tags, BROWSER_TAG);
  assert.equal(planTask(NO_REPO, "file", true).tags, BROWSER_TAG);
});

test("an already-created walkthrough's browser marker is detected exactly", () => {
  assert.equal(wantsBrowser({ Tags: `assistant:setup,${BROWSER_TAG}` }), true);
  assert.equal(wantsBrowser({ Tags: "needs:browsers" }), false);
  assert.equal(wantsBrowser({}), false);
});

test("and by default it does not", () => {
  for (const how of ["live", "file", "terminal"])
    assert.equal(String(planTask("acme/fanapp", how).tags || "").includes(BROWSER_TAG), false);
  assert.equal(planTask(NO_REPO, "live").browser, false);
});

test("repoOf is what the API is given", () => {
  assert.equal(repoOf("acme/fanapp"), "acme/fanapp");
  assert.equal(repoOf(NO_REPO), null);
  assert.equal(repoOf(""), null);
});
