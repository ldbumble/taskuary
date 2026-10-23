import test from "node:test";
import assert from "node:assert/strict";
import { createHealth, CONTACT_SYNC } from "./health.mjs";

// Baileys says these only to its logger - resyncAppState swallows the failure - so the bridge listens there (2026-10-23)
test("a contact sync that cannot find its key is counted, and a good sync clears the count", () => {
  let t = 1_750_000_000_000;
  const h = createHealth(() => t), said = [];
  const logger = h.tap({ info: (...a) => said.push(a), warn: () => {}, error: (...a) => said.push(a) });
  logger.info(`resyncing ${CONTACT_SYNC} from v0`);
  logger.info({ name: CONTACT_SYNC, error: 'Error: failed to find key "AAA=" to decode mutation\n    at x' }, "failed to sync state from version");
  logger.info({ name: CONTACT_SYNC, error: "Error: failed to find key" }, "failed to sync state from version");
  logger.info({ name: "regular_low", error: "boom" }, "failed to sync state from version");
  assert.equal(said.length, 4, "the logger still logs everything");
  let st = h.status();
  assert.equal(st.contactSync.failures, 2, "only the address book's collection counts");
  assert.equal(st.contactSync.why, "missing key");
  assert.deepEqual([st.lastFailure.kind, st.lastFailure.detail], ["contacts", "missing key"]);
  t += 60_000;
  logger.info(`restored state of ${CONTACT_SYNC} from snapshot to v12 with mutations`);
  st = h.status();
  assert.equal(st.contactSync.failures, 0);
  assert.equal(st.contactSync.ok, Math.floor(t / 1000));
});

test("a decrypt failure is the last failure, said in one short line; arrivals stamp lastInboundAt", () => {
  const h = createHealth(() => 1_750_000_000_000);
  const logger = h.tap({ error: () => {} });
  logger.error({ key: { id: "X" }, err: new Error("Bad MAC\nstack") }, "failed to decrypt message");
  assert.deepEqual(h.status().lastFailure, { kind: "decrypt", at: 1_750_000_000, detail: "Bad MAC" });
  assert.equal(h.status().lastInboundAt, 0);
  h.inbound();
  assert.equal(h.status().lastInboundAt, 1_750_000_000);
  assert.equal(h.tap(undefined), undefined, "no logger to tap (a test double of Baileys): nothing breaks");
});

test("a log call that the observer cannot read still reaches the logger", () => {
  const h = createHealth(), got = [];
  const logger = h.tap({ info: (...a) => got.push(a) });
  logger.info(Object.create(null, { name: { get() { throw new Error("odd"); } } }), "failed to sync state from version");
  assert.equal(got.length, 1);
});
