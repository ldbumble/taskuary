import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  captureNextSelection,
  hasNextSelection,
  nextMarkerKey,
  nextSelectionBody,
  nextSelectionScope,
  refreshPilePresentation,
  replaceSelectionToken,
  restorableCurrent,
  sameSelectionScope,
  selectionGuardDetail,
} from "../src/funnelPile.js";

const view = readFileSync(new URL("../src/AssistantView.jsx", import.meta.url), "utf8");

test("a captured automatic selection is bound to its exact scope and detached members", () => {
  const scope = nextSelectionScope("mail", "msg:4");
  const pile = {
    selection_revision: "selection-v1",
    expected_next_key: "fyis:msg:8,msg:9",
    expected_next_members: ["msg:8", "msg:9"],
    selection_pending: { triage: 2 },
  };
  const captured = captureNextSelection(pile, scope);
  pile.expected_next_members.push("msg:10");

  assert.equal(hasNextSelection(pile), true);
  assert.deepEqual(captured, {
    selection_revision: "selection-v1",
    expected_next_key: "fyis:msg:8,msg:9",
    expected_next_members: ["msg:8", "msg:9"],
    selection_pending: { triage: 2 },
    scope: { only: "mail", include_surfaced: false, exclude: "msg:4" },
  });
  assert.deepEqual(nextSelectionBody(captured), {
    selection_revision: "selection-v1",
    expected_next_key: "fyis:msg:8,msg:9",
    expected_next_members: ["msg:8", "msg:9"],
    only: "mail",
    include_surfaced: false,
    exclude: "msg:4",
  });
  assert.equal(sameSelectionScope(scope, nextSelectionScope("mail", "msg:4")), true);
  assert.equal(sameSelectionScope(scope, nextSelectionScope(null, "msg:4")), false);
  assert.equal(sameSelectionScope(scope, nextSelectionScope("mail", "msg:5")), false);
});

test("the server capture owns the visible Next marker, including FYI batches and null", () => {
  const items = [
    { key: "msg:1", lane: "asked", surfaced: false },
    { key: "msg:8", lane: "fyi", surfaced: false },
    { key: "msg:9", lane: "fyi", surfaced: false },
  ];
  assert.equal(nextMarkerKey({ selection_revision: "r", expected_next_key: "fyis:msg:8,msg:9",
    expected_next_members: ["msg:8", "msg:9"] }, items, null), "msg:8");
  assert.equal(nextMarkerKey({ selection_revision: "r2", expected_next_key: null,
    expected_next_members: [] }, items, null), null);
  // Static demos and old servers have no capture fields and keep their established local marker.
  assert.equal(nextMarkerKey({ rev: "legacy" }, items, null), "msg:1");
});

test("HTTP and streamed stale conflicts share one authoritative no-retry detail", () => {
  const detail = { code: "selection_stale", selection_revision: "fresh-r",
    expected_next_key: "msg:12", expected_next_members: ["msg:12"],
    selection_pending: null, retryable: true };
  assert.equal(selectionGuardDetail({ response: { data: { detail } } }), detail);
  assert.equal(selectionGuardDetail({ code: "selection_stale", detail }), detail);
  assert.equal(selectionGuardDetail({ response: { data: { detail: "ordinary error" } } }), null);

  const old = { display_revision: "display-old", selection_revision: "old-r",
    expected_next_key: "msg:11", expected_next_members: ["msg:11"], items: [] };
  const fresh = replaceSelectionToken(old, detail);
  assert.notEqual(fresh, old);
  assert.equal(fresh.display_revision, "display-old");
  assert.equal(fresh.selection_revision, "fresh-r");
  assert.deepEqual(fresh.expected_next_members, ["msg:12"]);
  assert.equal(old.selection_revision, "old-r");

  const unavailable = { code: "selection_unavailable", message: "selection is temporarily unavailable", retryable: true };
  assert.equal(selectionGuardDetail({ detail: unavailable }), unavailable);
  const disabled = replaceSelectionToken(old, unavailable);
  assert.equal(hasNextSelection(disabled), true);
  assert.equal(captureNextSelection(disabled, nextSelectionScope()), null);
  assert.equal(nextMarkerKey(disabled, [{ key: "msg:11", lane: "asked" }], null), null);

  // The capture is outside display_revision. A successful retry with unchanged rows must clear a
  // transient unavailable marker instead of preserving it through the presentation cache.
  const recovered = { ...old, selection_revision: "old-r", expected_next_key: "msg:11",
    expected_next_members: ["msg:11"], selection_unavailable: false };
  assert.equal(refreshPilePresentation(disabled, recovered), recovered);
});

test("reload restores only the latest explicit subject and leaves passive watcher cards in history", () => {
  const explicit = { key: "msg:4", kind: "review", lane: "approve" };
  const watcher = { key: "agent:9", kind: "agent", lane: "blocked", background_event: true };
  assert.equal(restorableCurrent([
    { id: 1, card: explicit },
    { id: 2, card: watcher },
  ]), explicit);
  assert.equal(restorableCurrent([{ id: 2, card: watcher }]), null);
  assert.equal(restorableCurrent([{ id: 1, card: explicit }, { id: 3, card: { key: "brief", kind: "brief" } }]), explicit);
});

test("Assistant echoes one captured selection and never retries a 409 through the plain endpoint", () => {
  assert.match(view, /selection_revision: body\.selection_revision, expected_next_key: body\.expected_next_key, expected_next_members: body\.expected_next_members/);
  assert.match(view, /if \(\[404, 405, 501\]\.includes\(res\.status\)\) return plain\(\)/);
  assert.doesNotMatch(view, /if \(!res\.ok \|\| !res\.body\).*return plain/);
  assert.match(view, /const navigation = capture \? nextSelectionBody\(capture\) : scope/);
  assert.match(view, /landed\(await turn\(\{ mode: "next", key, \.\.\.navigation \}\)\)/);
  assert.match(view, /loadPile\(true\);\s*\/\/ refresh the rows, never retry the navigation/);
});

test("Walk validates Current without creating a turn and stale gestures remove their optimistic line", () => {
  const start = view.slice(view.indexOf("const start = async"), view.indexOf("// The day used to write itself"));
  assert.ok(start.indexOf("await loadPile(true)") < start.indexOf("if (!currentRef.current) await surface"));
  assert.match(start, /if \(!currentRef\.current\) await surface/);
  const surface = view.slice(view.indexOf("const surface = useCallback"), view.indexOf("useEffect(() => { surfaceRef.current"));
  assert.ok(surface.indexOf("selectionContractSeen.current && !capture") < surface.indexOf("setMsgs((m) => [...m"),
    "an unavailable capture is rejected before drawing an optimistic owner turn");
  assert.match(view, /m\.filter\(\(message\) => message\.id !== optimisticId\)/);
  assert.match(view, /Next changed while the list refreshed/);
});

test("background events can notify but cannot choose, clear, or advance Current", () => {
  const events = view.slice(view.indexOf("if (data.events?.length)"), view.indexOf("// the item on the table is live"));
  assert.match(events, /speakRef\.current/);
  assert.doesNotMatch(events, /setCurrent|setCurrentItem|currentRef\.current\s*=|surfaceRef|deferInChat/);
  assert.match(view, /const last = restorableCurrent\(data\.messages\)/);
});
