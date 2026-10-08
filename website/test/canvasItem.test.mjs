import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const src = (f) => readFileSync(fileURLToPath(new URL(`../src/${f}`, import.meta.url)), "utf8");
const view = src("AssistantView.jsx"), item = src("CanvasItem.jsx");

// The canvas redesign (docs/superpowers/specs/2026-09-29-assistant-canvas-redesign-design.md): the item on the table is
// the Tasks tab's own task view, and three hard requirements hold it.
test("an item with a task behind it is shown by TaskPage; a proposal, a batch or a meeting keeps its own card", () => {
  // (JSX cannot load under bare node - the rule is read from the source)
  assert.match(item, /export const showsTask = \(card, kind\) => !!card\?\.tid && !\["proposal", "setup", "walk", "brief", "fyis", "meeting"\]\.includes\(kind\)/);
  assert.match(view, /if \(live && canvas && m\.card && showsTask\(c, kind\) && !foldedNow\) return \(/);
  assert.match(item, /<TaskPage taskId=\{card\.tid\} canvas active/);
});

// HARD REQUIREMENT 1: no terminal redraw corruption. The view's box is the chat body's height in BOTH states - Expand
// hides the conversation around it and never resizes it, so the pty inside can never be grown after it has output.
test("Expand never changes the view's height, so the pane is never grown", () => {
  assert.match(item, /sx=\{\{ height: h, display: "flex", flexDirection: "column", minWidth: 0, scrollMarginTop: "8px",/);
  assert.match(item, /export const CANVAS_ITEM_HEIGHT = "max\(420px, calc\(100cqh - 26px\)\)";/);
  assert.match(view, /height: CANVAS_ITEM_HEIGHT, expanded,/);
  assert.match(src("assistantView.css"), /container-type: size;/);
  assert.doesNotMatch(view.slice(view.indexOf("const canvasState"), view.indexOf("const canvasState") + 400), /expanded \?/);
  assert.match(src("assistantView.css"), /\.tq-chat-inner\.expanded > :not\(\.tq-canvas-live\) \{ display: none; \}/);
});

// ...and on a phone the view is the screen's height from the start; Expand pins that same box (measured in place) full
// screen with a back arrow - still no resize
test("a phone's full screen pins the same box, never a bigger one", () => {
  assert.match(item, /export const phoneItemHeight = \(innerHeight\) => Math\.max\(420, Math\.round\(\(innerHeight \|\| 0\) - 16\)\)/);
  assert.match(item, /const h = phone \? phoneH : height;/);
  assert.match(item, /if \(r\) setPin\(\{ left: r\.left, width: r\.width \}\);/);
  assert.match(item, /position: "fixed", top: 8, left: pin\.left, width: pin\.width/);
  // ...the arrow the SAME size as the icon it replaces: 2px more re-flowed the strip and the pane grew on the way back
  assert.match(src("TaskPage.jsx"), /backArrow \? <ArrowBackIcon sx=\{\{ fontSize: 15 \}\} \/> : <CloseFullscreenIcon sx=\{\{ fontSize: 15 \}\} \/>\) : <OpenInFullIcon sx=\{\{ fontSize: 15 \}\} \/>/);
});

// HARD REQUIREMENT 2: no rail rebuild on a click. Fold, unfold and Expand are client state.
test("fold, unfold and expand ask the server for nothing", () => {
  const state = view.slice(view.indexOf("const canvasState"), view.indexOf("const canvasState") + 400);
  assert.doesNotMatch(state, /api\.|loadPile|surface\(/);
  const reopen = view.slice(view.indexOf("reopen: (key, onTable)"), view.indexOf("reopen: (key, onTable)") + 120);
  assert.match(reopen, /if \(onTable\) setFoldedKey\(null\); else pull\(key\);/, "the folded item unfolds in place; an earlier one is a named pull");
});

// HARD REQUIREMENT 3: one live card - only the interactive line mounts a TaskPage (and with it one terminal)
test("only the item on the table is mounted live", () => {
  assert.match(view, /live=\{!old && i === lastCardIdx\}/);
  assert.equal((view.match(/<CanvasItem /g) || []).length, 1);
});

// the final review (2026-09-29): the canvas passes fresh callbacks on every render, and loadDetail listed onSelect in its
// deps - so every keystroke in the composer refetched the task and rebuilt its live subscription
test("the task view's loads do not depend on the callbacks its page passes", () => {
  const page = src("TaskPage.jsx");
  assert.match(page, /const onSelectRef = useRef\(onSelect\); onSelectRef\.current = onSelect;/);
  const load = page.slice(page.indexOf("const loadDetail = useCallback"), page.indexOf("const loadDetail = useCallback") + 1400);
  assert.match(load, /\}, \[\]\);/);
  assert.match(page, /const loadTasks = useCallback\(async \(\) => \{ await listRef\.current\?\.\(\); \}, \[\]\);/);
});

test("a new line always shows; only a browse card's own steps hold the bottom", () => {
  assert.match(view, /browseState: \(id, state\) => \{ holdBottom\.current = true; setMsgs/);
  assert.match(view, /useEffect\(\(\) => \{ holdBottom\.current = false; const el = bodyRef\.current;/);
  assert.doesNotMatch(view, /holdBottom\.current = !!browsing/);
});

test("a card open in the canvas is the turn's subject, not the item folded above it", () => {
  assert.match(view, /const subject = openCardRef\.current \? null : \(tableKey \|\| current\);/);
  assert.match(view, /key: subject, context_mid: currentItem\?\.mid && subject === current && !openCardRef\.current \? currentItem\.mid : null,\n\s+open_card: openCardRef\.current/);
});

// the owner, 2026-09-29: "fill up more width and more height for tasks so you can see more in one screen ... same for all items"
test("the item on the table spans the canvas, not the chat's reading column", () => {
  const css = src("assistantView.css");
  assert.match(css, /\.tq-chat-inner > \.tq-canvas-live, \.tq-chat-inner > \.tq-browse-line, \.tq-chat-inner > \.tq-live-card \{/);
  // the conversation column is the canvas's width now (.tq-chat-inner), so the item takes all of it: the same edges as the composer
  assert.match(css, /width: 100%; margin-left: 0; max-width: none; \}/);
  assert.match(css, /\.tq-chat-inner \{ width: 100%; \}/);
  assert.match(css, /\.tq-compose-box \{ width: 100%; \}/);
  assert.match(view, /live && card && kind !== "proposal" \? "tq-msg tq-live-card" : "tq-msg"/);   // ...a proposal is a chat line, not the item
});

// the gate at 1830x823: an expanded body's smaller top padding grew the pane 345 -> 355 (the view is sized off 100cqh)
test("expanding never changes the chat body's padding", () => {
  assert.doesNotMatch(src("assistantView.css"), /\.tq-chat-body\.expanded \{[^}]*padding/);
});

// the owner, 2026-09-29: Next "on the bottom like it used to be" - under the task view, never in its header's corner
// (2026-09-30, layout B): Next moved again - into the ONE row above the chat line, with the task's other verbs; the view registers it
test("a task's Next is the row's button: registered by the view, drawn above the chat line, in neither its header nor its foot", () => {
  assert.match(item, /useVerbs\("next", \[\{ id: "next", group: "next", label: "Next", disabled: !!busy, run: \(\) => onNext\(\)/);
  assert.doesNotMatch(item, /data-tq-next/);
  assert.match(src("ActionRow.jsx"), /data-tq-next=""/);
  assert.match(view, /<ActionRow waited=\{currentItem\?\.ref \? waitedText\(currentItem\) : ""\} \/>/);   // ...carrying how long it has waited (2026-10-07)
  assert.doesNotMatch(src("TaskPage.jsx"), /data-tq-next/);
});

// A CLOSE STAYS PUT DOWN (the owner, 2026-10-05: "the task stayed open and popped back open before closing"): Mark done and
// Close with a note fold the task at the press, then advance() empties the table - and the fold reset on ANY table change, so
// the closed task drew again for the ~0.6 s until the next item landed. Only a NEW item on the table opens unfolded.
test("emptying the table on the way to the next item keeps the closed one folded", () => {
  assert.match(view, /useEffect\(\(\) => \{ if \(!tableKey\) return; setExpanded\(false\); setFoldedKey\(null\); \}, \[tableKey\]\);/);
});

test("the note card goes at the press, and comes back with its words if the close fails", () => {
  const card = view.slice(view.indexOf("<CloseNote inline"), view.indexOf("<CloseNote inline") + 700);
  assert.ok(card.indexOf("setNoteOn(null)") < card.indexOf("await on.close(note)"), "put down before the close runs");
  assert.match(card, /catch \(e\) \{ setNoteOn\(\{ \.\.\.on, note \}\); throw e; \}/);
});

test("a close the server already answered brings the next item without the half-second grace", () => {
  assert.match(view, /onAfter=\{\(\) => actions\.advance\(null, true\)\}/);
  assert.match(view, /advance: \(pile, settled\) => advance\(pile, settled\),/, "the walk's advance passes `settled` on - it dropped it, so every close waited 500 ms");
});

// ONE ROW OF WORDS (the owner, 2026-10-05: "why is there buttons both places?"): with the item drawn as its task view, the row under
// the chat holds its words; a bare line under it borrowed the same item's recorded chips - twice, and stale.
test("a bare line borrows no words while the task view's own row holds them", () => {
  assert.match(view, /const barHolds = useMemo\(\(\) => \{/);
  assert.match(view, /showsTask\(c, cardFor\(c\)\) && !foldsAs\(canvasState\?\.folded, c\.key\) && !canvasState\?\.browsing/);
  assert.match(view, /const chips = barHolds && !m\.card \? \[\]/);
  assert.match(view, /tableChips=\{tableChips\} barHolds=\{barHolds\}/);
});
