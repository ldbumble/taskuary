import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";

const view = fs.readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
const card = fs.readFileSync(new URL("../src/assistantCards.jsx", import.meta.url), "utf8");
const reviews = fs.readFileSync(new URL("../src/ReviewView.jsx", import.meta.url), "utf8");

test("Assistant sends the message revision it saw and announces a newer live-chat line", () => {
  assert.match(view, /context_mid: currentItem\?\.mid/);
  assert.match(view, /New message from/);
  assert.match(view, /I refreshed the context/);
});

test("an open Assistant always pulls durable provider corrections", () => {
  assert.match(view, /Provider messages can arrive while this conversation is already open/);
  assert.match(view, /const \{ data: st \} = await api\.get\("\/api\/concierge"\)/);
  assert.match(view, /onLive\(\["feed-changed", "task-changed"\], \(\) => loadPile\(true\)\)/);
  assert.match(view, /pollWhileActive\(active, \(\) => loadPile\(false\), 30000\)/);
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
  assert.match(view, /if \(!t \|\| busy \|\| resetting \|\| turnFlight\.current\) return/);
});

test("stale reply drafts cannot be approved until they are refreshed", () => {
  assert.match(card, /!value\.trim\(\) \|\| !!stale/);
  assert.match(card, /New messages arrived after this draft/);
  assert.match(reviews, /r\.Stale \|\| !\(edits/);
  assert.match(reviews, /Refresh draft/);
});
