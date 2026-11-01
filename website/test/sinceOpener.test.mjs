// THE DAY'S OPENER LEADS THE CONVERSATION (the owner, 2026-11-01: "let's move the greeting all the way to the top always"): the morning's
// opener was recorded under yesterday's walk, and a folded task card stood over "Good morning".
import test from "node:test";
import assert from "node:assert/strict";
import { sinceOpener } from "../src/funnelPile.js";

const line = (id, kind) => ({ id, role: "assistant", text: id, ...(kind ? { card: { kind, key: kind === "brief" ? "brief" : `p:${id}` } } : {}) });

test("nothing from an earlier walk is drawn above the opener", () => {
  const ms = [line(1, "todo"), line(2), line(3, "brief"), line(4, "todo")];
  assert.deepEqual(sinceOpener(ms).map((m) => m.id), [3, 4]);
  assert.deepEqual(sinceOpener([line(1, "brief"), line(2, "todo"), line(3, "brief")]).map((m) => m.id), [3], "the newest opener leads");
});

test("a chat with no opener, or one already at the top, is the same array", () => {
  const none = [line(1, "todo"), line(2)], top = [line(1, "brief"), line(2, "todo")];
  assert.equal(sinceOpener(none), none); assert.equal(sinceOpener(top), top);
  assert.deepEqual(sinceOpener([]), []);
});
