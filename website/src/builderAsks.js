// WHAT THE BUILDER ASKS BACK, AS THE ANSWER'S OWN CONTROL (the owner, 2026-10-29: "which repository holds the skill?" was a free-text
// box beside the repository list the coding picker already has). The model says each question's kind (compose.ask_of); the page
// draws a repository list, a schedule, a choice or a text box from that - never from the question's words. Pure, so it is tested.
export const KINDS = ["text", "repo", "schedule", "choice"];
export const OTHER = "\u0000other";   // a repository or a choice that is not in the list: typed instead

// -> [{ q, kind, options }]: the server's asks, or an older answer's bare strings as text questions
export const asksOf = (out) => Array.isArray(out?.asks) && out.asks.length
  ? out.asks.map((a) => ({ q: String(a?.q || ""), kind: KINDS.includes(a?.kind) ? a.kind : "text", options: Array.isArray(a?.options) ? a.options : [] })).filter((a) => a.q)
  : (out?.questions || []).map((q) => ({ q: String(q), kind: "text", options: [] }));

export const filled = (v) => !!String(v ?? "").trim();
export const blanks = (asks, answers) => asks.filter((a) => !filled(answers[a.q])).length;

// ANSWER & BUILD PRESSES WITH SOME LEFT BLANK: what is answered goes back, and what is not the builder decides or asks again.
// Nothing answered is the same ask twice, so that one waits - and its hover says so.
export const answerState = (asks, answers, busy) => {
  const left = blanks(asks, answers), none = asks.length > 0 && left === asks.length;
  return { disabled: !!busy || none, left,
    hint: busy ? "Building it from your answers…" : none ? "Answer at least one - it decides the ones you leave blank, or asks again"
      : left ? `${left} left blank - it decides ${left === 1 ? "that one" : "those"} itself, or asks again` : "" };
};

// every question goes back, a blank one as "" - so the model knows which it still has to decide
export const answersFor = (asks, answers) => Object.fromEntries(asks.map((a) => [a.q, String(answers[a.q] ?? "").trim()]));

// a pick list for a repository or a choice: the known rows, an answer typed before that is not one of them kept as its own row
export const pickRows = (rows, value) => {
  const xs = [...new Set((rows || []).map(String).filter(Boolean))];
  return filled(value) && value !== OTHER && !xs.includes(value) ? [...xs, value] : xs;
};
