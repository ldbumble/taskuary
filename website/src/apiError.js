// One error body, read two ways: shown to the owner, and acted on by the code.
//
// FastAPI puts an ARRAY OF OBJECTS in `detail` for a validation error, and rendering that in JSX
// crashes React (#31) and blanks the whole app - so every non-string detail is normalized to a
// string, and ~130 `setErr(detail || "...")` sites depend on that.
//
// The STRUCTURE is the other half: a refused read says `{code, message}`, and processingErrorCode
// reads the code to decide what to DO about it (fall back to the legacy Timeline, reload an
// expired page, retry the pile in 1200ms). Flattening both halves at once is what left a routine
// "membership is being reconciled" showing as axios's own "Request failed with status code 409"
// with every one of those recoveries unreachable - a red banner over something that had already
// healed (seen on the owner's Timeline, 2026-09-10). So the structure is kept ON THE ERROR, where
// only the deciding code looks for it.
export const detailText = (d) => Array.isArray(d)
  ? d.map((x) => `${(x.loc || []).join(".")}: ${x.msg || JSON.stringify(x)}`).join(" · ")
  : JSON.stringify(d);

// WHAT A FAILED SAVE SAYS TO THE OWNER. The server's own sentence when it sent one (they are
// written for the owner); when nothing answered at all, that - never axios's "Network Error".
export const plainError = (e, fallback = "That didn't save. Try again in a moment.") => {
  if (typeof e?.detail?.message === "string") return e.detail.message;   // a structured refusal's own words
  const d = e?.response?.data?.detail;
  if (d) return typeof d === "string" ? d : detailText(d);
  if (e && !e.response) return "Taskuary isn't answering. Check the app is still running, then try again.";
  return fallback;
};

// THE DEMO SAYING NO, HEARD WHEREVER IT IS SAID (the button stress, 2026-11-02): the chat posts a refusal as a plain line of the demo's
// (AssistantView setErr), but knew only the ones that reached it through its own error reader - Hand it to a person's refusal came back
// through the card's own catch and stood in red with "Report this bug" under it. Every refusal is noted here, as it is answered.
export const DEMO_SAID = new Set();
export function keepDetail(e) {
  if (e?.response?.status === 403 && e.response.data?.demo && typeof e.response.data.detail === "string") DEMO_SAID.add(e.response.data.detail);
  const d = e?.response?.data?.detail;
  if (d && typeof d !== "string") { e.detail = d; e.response.data.detail = detailText(d); }
  return e;
}
