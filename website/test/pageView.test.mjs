// THE ASSISTANT ACTS ON THE PAGE AS THE OWNER WOULD - EXCEPT A SEND, AND NEVER A SECRET (the owner, 2026-10-30). The page's half of the two
// lines the server draws again (taskuary/pageview.py): which button sends something out, and which box holds a secret.
import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import { isSecret, isSend } from "../src/pageView.js";

const read = (name) => fs.readFileSync(new URL(`../src/${name}`, import.meta.url), "utf8");

test("an outward send is known by its verb or its words, and nothing else is one", () => {
  for (const b of [{ id: "row:approve", label: "Approve" }, { id: "x", label: "Send" }, { id: "x", label: "Send test message" }, { id: "x", label: "Anything", send: true },
    { id: "row:accept_invite", label: "Accept" }, { id: "x", label: "Reply all" }]) assert.equal(isSend(b), true, JSON.stringify(b));
  for (const b of [{ id: "test", label: "Test" }, { id: "row:done", label: "Mark done" }, { id: "save", label: "Save" }, { id: "sync", label: "Sync" },
    { id: "row:remind", label: "Remind me" }, { id: "row:redraft", label: "Redraft" }]) assert.equal(isSend(b), false, JSON.stringify(b));
});

test("a secret is known by its key or the words on its box", () => {
  for (const [k, l] of [["Secret", ""], ["client_secret", "Client secret"], ["x", "bot token (xoxb-…)"], ["api_key", ""], ["pw", "Password"]]) assert.equal(isSecret(k, l), true, k);
  for (const [k, l] of [["poll_seconds", "Check every (seconds)"], ["title", "Title"], ["region", "Region"]]) assert.equal(isSecret(k, l), false, k);
});

test("what leaves the page is the view without its elements, and a secret as its state only", () => {
  const src = read("pageView.js");
  assert.match(src, /secret: true, state: state \|\| "empty" \}/);
  assert.match(src, /buttons: v\.buttons\.map\(\(\{ id, label, enabled, send \}\)/, "no element and no handler goes");
  // ...and a press on a send is a light, checked again on the live page whatever the server said
  assert.match(src, /if \(op\.op === "point" \|\| \(b && isSend\(b\)\)\)/);
});

test("the chat sends the view only with a line the owner asked, and runs what came back as steps", () => {
  const view = read("AssistantView.jsx");
  assert.match(view, /const view = how\.view !== undefined \? how\.view : pageView\.context\(\);/);
  assert.match(view, /\.\.\.\(view \? \{ view \} : \{\}\), \.\.\.\(react \? \{ react \} : \{\}\)/);
  assert.match(view, /await pageView\.run\(ops, \(steps\) => setMsgs/);
  // ...a reaction is no line of the owner's, never opens the window, and stops at three in a row
  assert.match(view, /if \(!react\) setMsgs\(\(m\) => \{ const i = held/);
  assert.match(view, /s\.auto >= 3\) return;/);
  // ...and its × asks before it ends the help
  assert.match(view, /if \(pageView\.sessionNow\(\)\?\.door\) setEnding\(true\); else \{ pageView\.endSession\(\); shutBox\(\); \}/);
});
