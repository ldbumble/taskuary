import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { restorableCurrent } from "../src/funnelPile.js";

const source = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");

test("a historical finished-task card is never restored as current funnel work", () => {
  const live = { key: "msg:1", kind: "message" };
  assert.equal(restorableCurrent([
    { card: live },
    { card: { key: "agent:2", kind: "agentdone" } },
  ]), live);
  assert.equal(restorableCurrent([{ card: { key: "agent:2", kind: "agentdone" } }]), null);
  assert.match(source, /const last = data\.current \|\| null/);   // the server's validated Current, never the last card (PW-162)
  const events = source.slice(source.indexOf("if (data.events?.length)"), source.indexOf("// the item on the table is live"));
  assert.doesNotMatch(events, /setCurrent|setCurrentItem|currentRef\.current\s*=/,
    "live watcher updates do not choose any historical card as Current");
});

test("a set-up's pending questions are a line, not an item on the table", async () => {
  const { restorableCurrent } = await import("../src/funnelPile.js");
  assert.equal(restorableCurrent([{ card: { kind: "setup_questions", questions: ["Which repo?"] } }]), null);
  const view = (await import("node:fs")).readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
  assert.match(view, /const NOTE_KINDS = new Set\(\["setup_questions"\]\)/);
  assert.match(view, /NOTE_KINDS\.has\(c\?\.kind\) \? null/);
});

test("a phone turn shows on the desktop as it happens - the dots, then the words", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
  assert.match(view, /onLive\(\["chat-changed"\], \(ev\) => \{\s*setPhoneBusy\(!!ev\?\.thinking\);\s*readChat\(\)/);
  assert.match(view, /\{\(busy \|\| phoneBusy \|\| nextComing\) && \(/);
  // ...and between letting a card go and the next pick: the settle and the deferred surface() run before busy
  assert.match(view, /setNextComing\(true\);\s*let pile = null;/);
  assert.match(view, /deferredChat\.current\.delete\(timer\); setNextComing\(false\);/);
});
