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
  assert.match(source, /putOnTable\(data\.current \|\| null, "sync"\)/);   // the server's validated Current, never the last card (PW-162)
  const events = source.slice(source.indexOf("if (data.events?.length)"), source.indexOf("// the item on the table is live"));
  assert.doesNotMatch(events, /setCurrent|setCurrentItem|currentRef\.current\s*=|putOnTable/,
    "live watcher updates do not choose any historical card as Current");
});

test("a set-up's pending questions are a line, not an item on the table", async () => {
  const { restorableCurrent } = await import("../src/funnelPile.js");
  assert.equal(restorableCurrent([{ card: { kind: "setup_questions", questions: ["Which repo?"] } }]), null);
  // ...nor is a line that carries its own words (a failed act's way on, the already-seen opens)
  assert.equal(restorableCurrent([{ card: { kind: "words", chips: [{ verb: "next", label: "Next" }] } }]), null);
  const view = (await import("node:fs")).readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");
  assert.match(view, /const NOTE_KINDS = new Set\(\["setup_questions", "words"\]\)/);
  assert.match(view, /NOTE_KINDS\.has\(c\?\.kind\) \? null/);
});

test("a phone turn shows on the desktop as it happens - the dots, then the words", () => {
  const view = readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8");
  assert.match(view, /onLive\(\["chat-changed"\], \(ev\) => \{\s*setPhoneBusy\(!!ev\?\.thinking\);\s*readChat\(\)/);
  assert.match(view, /\{\(busy \|\| phoneBusy \|\| nextComing \|\| walkDots\) && \(/);
  // ...and between letting a card go and the next pick: the settle and the deferred surface() run before busy
  assert.match(view, /const leave = \(key, how, x = \{\}\) => new Promise\(\(done\) => \{\s*const epoch = chatEpoch\.current;\s*setNextComing\(true\);/);
  assert.match(view, /try \{ if \(epoch === chatEpoch\.current && !resettingRef\.current\) await fn\(\); \} finally \{ if \(!turnFlight\.current\) setNextComing\(false\); setDeferring\(deferredChat\.current\.size > 0\); \}/);
});

// A PAGE OPEN ON THE CANVAS STAYS OPEN UNDER THE ASSISTANT'S OWN WORDS (New -> a routine -> its builder, 2026-11-12): the setup turn's line
// came back from the 30 s chat read carrying its steps as a `words` card, the canvas took that line for an item put on the table over the
// builder, and folded the builder - the composed draft, not yet saved, gone with it, and the page back on the walk's last task
test("a line's own words after a page do not put the page down; an item does", async () => {
  const { liveBrowseId } = await import("../src/funnelPile.js");
  const page = { id: "b1", role: "browse", area: "reports" };
  const said = { id: 58, role: "assistant", text: "The routine is laid out.", card: { kind: "words", steps: [{ summary: "Pointed at Test every step" }] } };
  assert.equal(liveBrowseId([page, said]), "b1");
  assert.equal(liveBrowseId([page, { id: 59, role: "assistant", card: { kind: "task", key: "task:4" } }]), null);
  assert.equal(liveBrowseId([page, { id: 60, role: "assistant", card: { kind: "task", key: "task:4", background_event: true } }]), "b1");
  assert.equal(liveBrowseId([{ ...page, down: true }, said]), null);
  assert.match(readFileSync(fileURLToPath(new URL("../src/AssistantView.jsx", import.meta.url)), "utf8"), /const browsing = useMemo\(\(\) => liveBrowseId\(shown\), \[shown\]\);/);
});
