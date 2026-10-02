// A RELOAD NEVER REVIVES A HANDLED CARD (the owner, 2026-10-02: "if you click all read next on fyi mail too quickly it
// reopens the same 4 again before disappearing"). "All read, next" on the LAST batch found nothing next, so the page
// reloaded the conversation - and the server's history does not carry the page's own `done` mark, so the read batch,
// still the newest card, was drawn live again while the server said nothing was on the table.
import test from "node:test";
import assert from "node:assert/strict";
import { interactiveCardIndex, settledHistory } from "../src/funnelPile.js";

const batch = { id: "a1", role: "assistant", card: { key: "fyis:processing:p1,processing:p2", kind: "fyis" } };
const empty = { id: "a2", role: "assistant", text: "That's everything for now." };

test("a card that is not the server's current comes back put down", () => {
  const msgs = settledHistory([batch, empty], null);
  assert.equal(interactiveCardIndex(msgs), -1);
});

test("the server's current card stays live, by key or alias", () => {
  assert.equal(interactiveCardIndex(settledHistory([batch, empty], batch.card.key)), 0);
  const aliased = { ...batch, card: { ...batch.card, key: "agent:7", aliases: ["msg:9"] } };
  assert.equal(interactiveCardIndex(settledHistory([aliased], "msg:9")), 0);
});

test("a proposal, the set-up walk and the brief are not item cards - a reload leaves them as they were", () => {
  for (const card of [{ kind: "proposal", key: "op:1" }, { kind: "walk", key: "w1" }, { kind: "setup" }, { kind: "brief", key: "brief" }]) {
    assert.equal(settledHistory([{ id: "x", role: "assistant", card }], null)[0].done, undefined, card.kind);
  }
  assert.equal(settledHistory([{ id: "p", role: "assistant", proposal: { id: "op1" }, card: { key: "msg:3", kind: "message" } }], null)[0].done, undefined);
});
