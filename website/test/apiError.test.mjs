// The seam, which is where this broke: processingAll's predicates were tested on hand-built error
// objects, api.js's normalizer was never tested at all, and nothing ran the two together. In the
// app the normalizer runs FIRST on every rejection, so a structured refusal reached the deciding
// code as a JSON string that matched no code - the legacy-Timeline fallback, the snapshot reload
// and the Assistant's two pile retries all went unreachable, and a routine "membership is being
// reconciled" surfaced as axios's "Request failed with status code 409" in a red banner.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { detailText, keepDetail } from "../src/apiError.js";
import { isCoveragePending, isSnapshotExpired, processingErrorCode, processingErrorMessage } from "../src/processingAll.js";

// what axios hands a catch block after the interceptor has run, for a real 409 from the inventory
const refused = (code, message, extra = {}) => keepDetail({
  message: "Request failed with status code 409",
  response: { status: 409, data: { detail: { code, message, ...extra } } },
});

test("a refusal still names itself after normalizing, so its recovery can run", () => {
  const pending = refused("processing_coverage_pending", "All items are not ready yet", { coverage: {} });
  assert.equal(processingErrorCode(pending), "processing_coverage_pending");
  assert.equal(isCoveragePending(pending), true);
  assert.equal(processingErrorMessage(pending, "Failed to load the feed"), "All items are not ready yet");
  const expired = refused("processing_snapshot_expired", "This page snapshot expired; refresh All");
  assert.equal(isSnapshotExpired(expired), true);
  const moved = refused("processing_target_moved", "That item moved under you");
  assert.equal(processingErrorCode(moved), "processing_target_moved");
  assert.equal(moved.detail.message, "That item moved under you");   // the banner's words are the server's
});

test("the Timeline's own catches read the structure, not the flattened copy", () => {
  const src = readFileSync(fileURLToPath(new URL("../src/FeedView.jsx", import.meta.url)), "utf8");
  assert.doesNotMatch(src, /response\?\.data\?\.detail\?\.code/);
  assert.doesNotMatch(src, /response\.data\.detail\.message/);
  assert.match(src, /processingErrorCode\(e\) === "processing_target_moved"/);
});

test("the rendered copy is still a plain string, which every setErr site relies on", () => {
  const e = refused("processing_coverage_pending", "All items are not ready yet");
  assert.equal(typeof e.response.data.detail, "string");
  assert.match(e.response.data.detail, /processing_coverage_pending/);
});

test("a FastAPI validation array still reads as one line, never as [object Object]", () => {
  const e = keepDetail({ response: { data: { detail: [{ loc: ["body", "name"], msg: "field required" }] } } });
  assert.equal(e.response.data.detail, "body.name: field required");
  assert.equal(detailText([{ loc: ["a"], msg: "bad" }, { loc: ["b"], msg: "worse" }]), "a: bad · b: worse");
});

test("a string detail, and an error with no body at all, are left exactly as they are", () => {
  const said = keepDetail({ response: { data: { detail: "this reply has already been decided" } } });
  assert.equal(said.response.data.detail, "this reply has already been decided");
  assert.equal(said.detail, undefined);              // nothing to keep: it was never structured
  assert.equal(processingErrorMessage(said, "fallback"), "this reply has already been decided");
  assert.doesNotThrow(() => keepDetail(new Error("Network Error")));
  assert.equal(processingErrorMessage(new Error("Network Error"), "fallback"), "Network Error");
});

test("the selection guard's shape - written for error.detail all along - now gets one", async () => {
  const { selectionGuardDetail } = await import("../src/funnelPile.js");
  const e = keepDetail({ response: { status: 503, data: { detail: { code: "selection_unavailable", selection_pending: null } } } });
  assert.equal(selectionGuardDetail(e)?.code, "selection_unavailable");
});

test("api.js normalizes through the one helper, so this cannot drift back apart", () => {
  const src = readFileSync(fileURLToPath(new URL("../src/api.js", import.meta.url)), "utf8");
  assert.match(src, /keepDetail/);
  assert.doesNotMatch(src, /JSON\.stringify\(d\)/);   // the flattening lives in apiError.js only
});
