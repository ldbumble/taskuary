// THE ONE PRESS (the spine audit, 2026-11-09). A review's verdict was posted from ten places, each with its own patience (none at all, one
// minute, two), its own reading of the answer and its own words when it failed. So an act's card that gave up after two minutes said "nothing
// was posted. Try again" while the server was still posting; a press answered in another window was an error on one card and nothing on the
// next; and six had no patience at all, so behind a stalled server their button spun for ever.
// One post, one patience, one reading of the answer - `kind`, which every card switches on. No React, so it runs under bare node.
import { DECIDE_TIMEOUT, timedOut } from "./sendState.js";

//   ok       it landed
//   partial  it landed, and what rode with it did not (a close-out went, its reply was refused): `why` says so
//   already  decided elsewhere - another window, the chat itself. Nothing failed; the card reads the review again
//   stale    the thread moved under a reply and nothing was sent (approvalInterrupt.interruptOf reads `data`)
//   blanks   a blank the server found in the words
//   refused  not now - a close-out its repository's state refuses - with what fits instead (`data.offers`)
//   failed   it answered, and `why` is its reason
//   unknown  no answer in time. The server may be at it still, so this is never "nothing was sent": the card reads the review again
//   error    the press never arrived, or the request itself was refused (`why`: the server's sentence, if it sent one; `thrown`: the error)
export const outcomeOf = (data, e = null) => e
  ? { kind: timedOut(e) ? "unknown" : "error", data: null, why: timedOut(e) ? "" : String(e?.response?.data?.detail || ""), thrown: e }
  : { kind: data?.already ? "already" : data?.stale ? "stale" : data?.blanks?.length ? "blanks" : data?.refused ? "refused"
      : !data?.ok ? "failed" : data.send_error ? "partial" : "ok", data: data || null, why: String(data?.send_error || "") };

const post = async (api, url, body, wait) => {
  try { return outcomeOf((await api.post(url, body, { timeout: DECIDE_TIMEOUT * Math.max(1, wait) })).data); }
  catch (e) { return outcomeOf(null, e); } };
// `wait`: how many times the one patience this press is given - an act that runs something takes longer than a reply handed to its provider
export const press = (api, rid, body, wait = 1) => post(api, `/api/reviews/${rid}/decide`, { final_text: null, note: null, ...body }, wait);
// ...and a turn's held steps, approved or dismissed together (/api/reviews/steps): it stops at the first that fails, and `why` is that step's
export const pressSteps = async (api, ids, verb) => { const o = await post(api, "/api/reviews/steps", { ids, verb }, ids.length);
  return o.data?.failed ? { ...o, kind: "failed", why: String(o.data.failed.error || "") } : o; };

export const landed = (o) => o.kind === "ok" || o.kind === "partial";
// what a card says under a press that did not land: the server's reason, else that nothing was `done` ("sent", "posted", "run") - and never
// that after no answer, when it may be going still (verdicts' claim: a second press of a running act or send does nothing)
export const STILL = "No answer yet - it may still be going. Nothing runs twice.";
export const failLine = (o, done = "done") => o.kind === "unknown" ? STILL : o.why || `It didn't go through - nothing was ${done}. Try again.`;
// ...for a road that reports what is thrown itself (the game's play, the walk's card): the answer, or the line as an error. A press that
// never arrived throws what the request threw - its reader knows the demo's refusal and a fix the server offered
export const sure = (o, done) => { if (o.kind === "error") throw o.thrown; if (o.kind !== "ok") throw new Error(failLine(o, done)); return o.data; };
