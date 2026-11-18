// The seam, which is where this broke: processingAll's predicates were tested on hand-built error
// objects, api.js's normalizer was never tested at all, and nothing ran the two together. In the
// app the normalizer runs FIRST on every rejection, so a structured refusal reached the deciding
// code as a JSON string that matched no code - the Assistant's two pile retries went
// unreachable, and a routine "membership is being
// reconciled" surfaced as axios's "Request failed with status code 409" in a red banner.
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { detailText, keepDetail } from "../src/apiError.js";
import { isCoveragePending, processingErrorCode, processingErrorMessage } from "../src/processingAll.js";

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
  const moved = refused("processing_target_moved", "That item moved under you");
  assert.equal(processingErrorCode(moved), "processing_target_moved");
  assert.equal(moved.detail.message, "That item moved under you");   // the banner's words are the server's
});

test("the rail's own catches read the structure, not the flattened copy", () => {
  const src = readFileSync(fileURLToPath(new URL("../src/FeedView.jsx", import.meta.url)), "utf8");
  assert.doesNotMatch(src, /response\?\.data\?\.detail\?\.code/);
  assert.doesNotMatch(src, /response\.data\.detail\.message/);
  assert.match(src, /processingErrorMessage\(e, "Failed to load the feed"\)/);
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

test("a structured refusal's shape - read off error.detail - is kept on the error", async () => {
  const e = keepDetail({ response: { status: 409, data: { detail: { code: "processing_coverage_pending", retryable: true } } } });
  assert.equal(e.detail?.code, "processing_coverage_pending");
});

test("a failed save reads as a sentence: the server's, or that nothing answered - never axios's", async () => {
  const { plainError } = await import("../src/apiError.js");
  assert.equal(plainError(keepDetail({ response: { status: 422, data: { detail: "pick one of those three" } } })), "pick one of those three");
  assert.equal(plainError(refused("x", "That item moved under you")), "That item moved under you");
  assert.match(plainError(new Error("Network Error")), /isn't answering/);
  assert.equal(plainError({ response: { status: 500, data: {} } }, "fallback"), "fallback");
});

test("api.js normalizes through the one helper, so this cannot drift back apart", () => {
  const src = readFileSync(fileURLToPath(new URL("../src/api.js", import.meta.url)), "utf8");
  assert.match(src, /keepDetail/);
  assert.doesNotMatch(src, /JSON\.stringify\(d\)/);   // the flattening lives in apiError.js only
});

// THE DEMO'S NO IS ITS OWN LINE (the walk, 2026-11-18): Trust on a closed task read "That didn't go through - This is the demo - ...
// Press Trust Priya again." - a press that can never work, asked for again. One reader says whether an error is the demo saying no.
test("the demo's refusal is read as its own sentence, and nothing else is", async () => {
  const { demoNo } = await import("../src/apiError.js");
  const no = { response: { status: 403, data: { demo: true, detail: "This is the demo - the agents here are recordings, so nothing new starts." } } };
  assert.equal(demoNo(no), no.response.data.detail);
  assert.equal(demoNo({ response: { status: 403, data: { detail: "forbidden" } } }), "");
  assert.equal(demoNo({ response: { status: 500, data: { demo: true, detail: "x" } } }), "");
  const page = readFileSync(fileURLToPath(new URL("../src/TaskPage.jsx", import.meta.url)), "utf8");
  const trust = page.slice(page.indexOf("const trustPress"), page.indexOf("finally { setTrusting(null)"));
  assert.match(trust, /setErr\(demoNo\(e\) \|\|/, "the Trust press says the demo's no as it is");
});
