// ENABLING SAVES IT, FOR EVERY CONNECTOR (the owner, 2026-10-23: "you enable a connection and then sync now button shows up but
// then under it it says not saved ... for all connectors"). The switch was a draft: the card drew itself on - Sync now and all -
// while the server still had it off and the Save bar listed "Connection: off → on". One press, one state, on every card.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { applied, changes, editedBoxes, splitNow, stage, syncState } from "../src/connectorDraft.js";

const cat = JSON.parse(readFileSync(new URL("../../taskuary/connectorcatalog.json", import.meta.url), "utf8"));
const src = readFileSync(new URL("../src/ConnectorsView.jsx", import.meta.url), "utf8");
const types = cat.cards.map((c) => c.type);

// what a card's switch does through the shared draft (ConnectorDraft.jsx useCardDraft.stageConn), as the server would answer it
const press = (row, on) => {
  const { now, rest } = splitNow({ ConnectorId: row.ConnectorId, Active: on });
  const want = rest ? stage(null, rest) : null;
  return { saved: now ? { ...row, Active: now.Active } : row, want };
};

test("the catalogue is read", () => assert.ok(types.length > 20, `only ${types.length} types`));

for (const [i, type] of types.entries()) test(`${type}: Enable saves on the press, and Sync now never stands beside "not saved"`, () => {
  const off = { ConnectorId: i + 1, Type: type, Active: 0, ConfigJson: JSON.stringify({ host: "mail.northwind.example" }) };
  assert.deepEqual(syncState(off), { show: false, ok: false, why: "" }, "off on the server: no Sync now");

  const { saved, want } = press(off, true);
  assert.equal(saved.Active, true, "the press posts Active at once");
  assert.deepEqual(changes(saved, want), [], "nothing left for the Save bar to call unsaved");
  assert.equal(applied(saved, want).Active, true, "the card draws what the server holds");
  assert.deepEqual(syncState(saved, changes(saved, want)), { show: true, ok: true, why: "" });

  // a real unsaved edit greys Sync now with the reason, and it is gone once saved
  const edit = stage(want, { ConnectorId: saved.ConnectorId, ConfigJson: JSON.stringify({ host: "imap.northwind.example" }) });
  const s1 = syncState(saved, changes(saved, edit));
  assert.equal(s1.show && !s1.ok && /Save/.test(s1.why), true);
  const after = { ...saved, ConfigJson: JSON.stringify(edit.cfg) };
  assert.equal(syncState(after, changes(after, edit)).ok, true, "saved: Sync now is pressable again");

  // ...and off is saved on the press as well
  const back = press(saved, false);
  assert.equal(back.saved.Active, false); assert.deepEqual(changes(back.saved, back.want), []);
  assert.equal(syncState(back.saved).show, false);
});

test("a switch posted with settings beside it: the switch goes now, the settings stay in the draft", () => {
  const { now, rest } = splitNow({ ConnectorId: 4, Active: false, Roles: "feed" });
  assert.deepEqual(now, { ConnectorId: 4, Active: false });
  assert.deepEqual(rest, { ConnectorId: 4, Roles: "feed" });
  assert.deepEqual(splitNow({ ConnectorId: 4, Roles: "feed" }), { now: null, rest: { ConnectorId: 4, Roles: "feed" } });
});

test("a credential box counts as unsaved only past what it last saved", () => {
  assert.equal(editedBoxes(["host"], { host: "a" }, { host: "a" }), false);
  assert.equal(editedBoxes(["host"], { host: "b" }, { host: "a" }), true);
  assert.equal(editedBoxes(["host"], { host: "a", auth: "user" }, { host: "a" }), false, "a key no box shows is not the owner's typing");
  assert.equal(editedBoxes(["host"], {}, {}, "pw"), true, "a typed secret is unsaved until saved");
});

test("every card that opens a draft switches through it, and every Sync now on a card reads syncState", () => {
  // the two draft cards (ChannelDetail, DataDetail) carry every catalogue type but mssql and winrm, whose own Save posts
  // Active: true with its settings, and reason_network, whose switch (ReasonNetwork.jsx) posts on the press - one press each already
  assert.equal(src.match(/const setActive = \(on\) => draft\.ctx\.stageConn\(\{ ConnectorId: conn\.ConnectorId, Active: on \}\)/g)?.length, 2);
  const body = src.slice(src.indexOf("export function ChannelDetail"), src.indexOf("function MssqlDetail"));
  const syncs = body.match(/onClick=\{syncHere\}[^>]*>/g) || [];
  assert.equal(syncs.length, 2);
  for (const b of syncs) assert.match(b, /sync\.ok/, `a Sync now that does not read syncState: ${b}`);
  assert.doesNotMatch(body, /\{conn\.Active && !isAI && \(/, "Sync now drawn off the draft, not what is saved");
  for (const t of ["mssql", "winrm", "reason_network"]) assert.ok(types.includes(t), t);
  assert.match(readFileSync(new URL("../src/ReasonNetwork.jsx", import.meta.url), "utf8"), /api\.post\("\/api\/connectors", \{ ConnectorId: conn\.ConnectorId, Active: e\.target\.checked \}\)/);
  assert.equal(src.match(/ConfigJson: JSON\.stringify\(cfg\), Active: true/g)?.length, 2, "mssql and winrm save and switch on in one press");
});
