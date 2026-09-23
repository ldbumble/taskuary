import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const view = fs.readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
const card = fs.readFileSync(new URL("../src/assistantCards.jsx", import.meta.url), "utf8");
// the decision moved out of the tab into a component both the queue and the task page mount
const reviews = fs.readFileSync(new URL("../src/ReviewDecision.jsx", import.meta.url), "utf8");

test("Assistant sends the message revision it saw and a newer live-chat line refreshes the card", () => {
  assert.match(view, /context_mid: currentItem\?\.mid/);
  assert.match(view, /New message from/);
  assert.match(view, /The context is refreshed/);
  assert.doesNotMatch(view, /notice:msg:/);   // no strip notice any more (2026-09-23): the card refreshes, never a chat line (PW-165)
});

test("an open Assistant always pulls durable provider corrections", () => {
  assert.match(view, /Provider messages can arrive while this conversation is already open/);
  assert.match(view, /const \{ data: st \} = await api\.get\("\/api\/concierge"\)/);
  assert.match(view, /onLive\(\["feed-changed", "task-changed"\], \(ev, meta\) => \{ if \(!coveredByReload\(meta, forcedLoadStartedAt\.current\)\) loadPile\(true\); \}, \{ wait: 1500, max: 5000 \}\)/);
  assert.match(view, /pollWhileActive\(active, \(\) => \{\s*if \(first \|\| !liveUp\(\) \|\| \+\+n % 10 === 0\) loadPile\(false\);\s*else readChat\(\)/);
  // under a live socket the tick reads only the chat: provider turns push no event (store.add_comment)
  assert.match(view, /if \(!\(await readChat\(epoch\)\)\) return;/);
  assert.match(view, /if \(pileFlight\.current\)/);
  assert.match(view, /pileForcePending\.current = true/);
  assert.match(view, /queueMicrotask\(\(\) => loadPileRef\.current\?\.\(true\)\)/);
});

test("New chat clears immediately without impersonating an AI turn or accepting stale polls", () => {
  const block = view.slice(view.indexOf("const newChat = async"), view.indexOf("const openOld", view.indexOf("const newChat = async")));
  assert.ok(block.indexOf("setMsgs([])") < block.indexOf('api.post("/api/assistant/dock/new"'));
  assert.doesNotMatch(block, /setBusy\(/);
  assert.match(block, /chatEpoch\.current \+= 1/);
  assert.match(block, /cancelDeferredChat\(\)/);
  assert.match(view, /epoch !== chatEpoch\.current \|\| resettingRef\.current/);
  assert.match(view, /chatsLoading && .*Loading past chats/s);
});

test("delayed next-card actions cannot cross a New chat boundary", () => {
  assert.match(view, /const deferredChat = useRef\(new Set\(\)\)/);
  assert.match(view, /epoch === chatEpoch\.current && !resettingRef\.current/);
  assert.doesNotMatch(view, /setTimeout\(\(\) => surface(?:Ref\.current\?\.)?\(/);
});

test("same-tick composer submits are synchronously locked", () => {
  assert.match(view, /const turnFlight = useRef\(false\)/);
  assert.match(view, /if \(!t \|\| busy \|\| resetting \|\| handoff \|\| turnFlight\.current\) return/);
});

// A stale draft is never sent - and the card must say what to do instead. Disabling the only
// button on it left the owner with a warning and no road (the owner, 2026-09-21: "can't hit
// approve & send since there is warning? just reprocess it then"), so refreshing takes the
// primary slot for exactly as long as the thread is ahead of the draft.
test("a stale reply draft offers a refresh in place of the send", () => {
  assert.match(card, /New messages arrived after this draft/);
  assert.match(card, /stale \? \(/);
  assert.match(card, /Refresh the draft/);
  assert.doesNotMatch(card, /!value\.trim\(\) \|\| !!stale/);      // no dead end behind the warning
  assert.match(reviews, /r\.Stale \? \(/);
  assert.match(reviews, /Refresh the draft/);
  assert.doesNotMatch(reviews, /r\.Stale \|\| !\(edits/);
});
