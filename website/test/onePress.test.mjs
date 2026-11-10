// THE SPINE AUDIT, 2026-11-09: a review's verdict was posted from ten places, each with its own patience, its own reading of the answer and
// its own words when it failed. An act's card said "nothing was posted. Try again" over a post still going up; six presses had no timeout at
// all. One press now (src/press.js), and no card posts a verdict any other way.
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import test from "node:test";
import { STILL, failLine, landed, outcomeOf, press, pressSteps, sure } from "../src/press.js";
import { DECIDE_TIMEOUT } from "../src/sendState.js";

const SRC = new URL("../src/", import.meta.url), read = (f) => readFileSync(new URL(f, SRC), "utf8");
const api = (answer) => { const calls = []; return { calls, post: async (url, body, opts) => { calls.push({ url, body, opts });
  if (answer instanceof Error || answer?.code || answer?.response) throw answer; return { data: answer }; } }; };

test("the server's answer is read one way", () => {
  const kind = (d) => outcomeOf(d).kind;
  assert.equal(kind({ ok: true, status: "approved" }), "ok");
  assert.equal(kind({ ok: true, send_error: "Done on GitHub, but the reply was not sent: it was refused" }), "partial");
  assert.equal(kind({ ok: false, already: true, send_error: "this one was already approved" }), "already");
  assert.equal(kind({ ok: false, stale: true, send_error: "New messages arrived after this draft." }), "stale");
  assert.equal(kind({ ok: false, blanks: ["[date]"], send_error: "It still has a blank" }), "blanks");
  assert.equal(kind({ ok: false, refused: true, send_error: "checks are failing", offers: [] }), "refused");
  assert.equal(kind({ ok: false, send_error: "LinkedIn refused the post" }), "failed");
  assert.equal(outcomeOf({ ok: false, send_error: "LinkedIn refused the post" }).why, "LinkedIn refused the post");
  assert.ok(landed(outcomeOf({ ok: true })) && landed(outcomeOf({ ok: true, send_error: "x" })) && !landed(outcomeOf({ ok: false, already: true })));
});

test("no answer in time is never 'nothing was sent', and a press that never arrived says the server's sentence or that nothing was done", async () => {
  const slow = await press(api({ code: "ECONNABORTED" }), 7, { verb: "approve" });
  assert.equal(slow.kind, "unknown"); assert.equal(failLine(slow, "posted"), STILL); assert.doesNotMatch(STILL, /nothing was|try again/i);
  const refused = await press(api({ response: { status: 409, data: { detail: "That draft is from an earlier session of the agent." } } }), 7, { verb: "approve" });
  assert.deepEqual([refused.kind, failLine(refused)], ["error", "That draft is from an earlier session of the agent."]);
  const down = await press(api(new Error("Network Error")), 7, { verb: "approve" });
  assert.deepEqual([down.kind, failLine(down, "posted")], ["error", "It didn't go through - nothing was posted. Try again."]);
});

test("every press is the one post, with the one patience", async () => {
  const a = api({ ok: true, result: { url: "https://social.example/p/1" } });
  const o = await press(a, 7, { verb: "approve", final_text: "We shipped the export." }, 2);
  assert.deepEqual(a.calls[0], { url: "/api/reviews/7/decide", body: { final_text: "We shipped the export.", note: null, verb: "approve" }, opts: { timeout: DECIDE_TIMEOUT * 2 } });
  assert.equal(o.data.result.url, "https://social.example/p/1");
  await press(a, 8, { verb: "reject" });
  assert.deepEqual(a.calls[1], { url: "/api/reviews/8/decide", body: { final_text: null, note: null, verb: "reject" }, opts: { timeout: DECIDE_TIMEOUT } });
});

test("a turn's held steps go together, and the step that stopped them is the reason", async () => {
  const a = api({ ok: false, done: [{ review: 4 }], failed: { review: 5, step: 2, error: "exit 1" }, left: [6] });
  const o = await pressSteps(a, [4, 5, 6], "approve");
  assert.deepEqual([o.kind, o.why, a.calls[0].url, a.calls[0].opts.timeout], ["failed", "exit 1", "/api/reviews/steps", DECIDE_TIMEOUT * 3]);
  assert.deepEqual(a.calls[0].body, { ids: [4, 5, 6], verb: "approve" });
  assert.equal((await pressSteps(api({ ok: true, done: [{ review: 4 }], failed: null, left: [] }), [4], "approve")).kind, "ok");
  assert.equal(failLine(await pressSteps(api({ code: "ETIMEDOUT" }), [4], "approve"), "run"), STILL);
});

test("a road that reports what is thrown gets the answer, the line, or the request's own error", () => {
  assert.deepEqual(sure(outcomeOf({ ok: true, status: "approved" })), { ok: true, status: "approved" });
  assert.throws(() => sure(outcomeOf({ ok: false, already: true, send_error: "this one was already approved" })), /already approved/);
  assert.throws(() => sure(outcomeOf({ ok: true, send_error: "the reply was not sent" })), /the reply was not sent/);
  assert.throws(() => sure(outcomeOf(null, { code: "ECONNABORTED" })), new RegExp(STILL.slice(0, 13)));
  const refusal = Object.assign(new Error("demo"), { response: { status: 403, data: { detail: "The demo does not send.", fix: { href: "#x", label: "Open" } } } });
  assert.throws(() => sure(outcomeOf(null, refusal)), (e) => e === refusal, "its reader knows a refusal's fix: the error itself, not a copy of its words");
});

test("no card posts a verdict any other way", () => {
  for (const f of readdirSync(SRC).filter((x) => /\.jsx?$/.test(x) && x !== "press.js" && !/^demo/i.test(x)))
    assert.doesNotMatch(read(f), /api\.post\((`\/api\/reviews\/\$\{[^}]+\}\/decide`|"\/api\/reviews\/steps")/, `${f} posts its own`);
  const uses = { "ActionCard.jsx": /press\(api, row\.ReviewId, /, "HeldSteps.jsx": /pressSteps\(api, c\.waiting, verb\)/, "BrowserPane.jsx": /pressReview\(api, h\.id, /,
    "GeneralWorkspace.jsx": /press\(api, r\.ReviewId, /, "assistantCards.jsx": /press\(api, onCo, /, "SlotList.jsx": /press\(api, r\.ReviewId, /,
    "gameItem.jsx": /press\(api, item\.rid, /, "ReviewDecision.jsx": /press\(api, r\.ReviewId,/ };
  for (const [f, re] of Object.entries(uses)) assert.match(read(f), re, f);
  // ...and an act's card reads itself again where the press was answered elsewhere or not yet, with no failure said for the first
  const card = read("ActionCard.jsx");
  assert.match(card, /if \(!landed\(o\) && o\.kind !== "already"\) setErr\(failLine\(o, post \? "posted" : "sent"\)\);/);
  assert.match(card, /if \(landed\(o\) \|\| \["already", "unknown"\]\.includes\(o\.kind\)\) onChanged\?\.\(\);/);
  assert.doesNotMatch(read("GeneralWorkspace.jsx"), /if \(data\.send_error\) throw new Error\(data\.send_error\);\n\s+const message = verb === "approve"/);
});
