import test from "node:test";
import assert from "node:assert/strict";
import { connectName, connectionWish, draftRequest } from "../src/bugReportOpen.js";
import { matchCards } from "../src/connectorCatalog.js";
import { label } from "../src/buttons.js";

const groups = [{ title: "Mail", cards: [{ key: "imap", title: "IMAP", channel: "imap" }] },
                { title: "Planned", cards: [{ key: "p", title: "Payworth", channel: "payworth", planned: true }] }];

test("the button stands only when the search matches no card, planned ones included", () => {
  assert.equal(matchCards(groups, "payworth").length, 1); assert.equal(matchCards(groups, "Trainly").length, 0);
});

test("a plain product name is asked for by name; a short or odd query as this connection", () => {
  assert.equal(connectName("  Trainly   HR "), "Trainly HR"); assert.equal(connectName("Q&A.io"), "Q&A.io");
  for (const q of ["x", "", "<script>", "a".repeat(41), "why won't it ?"]) assert.equal(connectName(q), "");
  assert.equal(label("report_bug", "connect"), "Request this connection");
});

test("it is the same wish concierge.no_card files: a feature, no error, the typed name carried", () => {
  const w = connectionWish("Trainly");
  assert.deepEqual([w.kind, w.screen], ["feature", "Connections"]);
  assert.match(w.happened, /A card under Connections for Trainly, so Taskuary can connect to it/);
  const r = draftRequest({ screen: "x", error: "boom", stack: "s", route: "/r", actions: ["a"] }, w);
  assert.deepEqual([r.kind, r.error, r.stack, r.actions, r.trying], ["feature", "", "", [], "Find a card under Connections for Trainly"]);
  assert.match(connectionWish("??").happened, /a system I searched for/);
});
