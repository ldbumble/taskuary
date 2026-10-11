// What a live session is ASKING the owner, read off its own word (terminal.worker_fields: request, questions, held) -
// the Task page drew only "coder is asking you" over a held Claude question, with no text and nothing to pick (B11,
// the owner, 2026-10-11). The Assistant tab already drew the pills; this is the same ask, for the page.

// null when nothing is asked; a stall is not a question (nothing answers a rate limit)
export function asksOf(session) {
  const req = session?.request;
  if (!session?.alive || !req?.request_id || req.kind === "stalled") return null;
  const qs = (session.questions || []).length > 1 ? session.questions : [req];
  return { kind: req.kind, held: !!session.held,
    questions: qs.map((q) => ({ request_id: q.request_id, text: q.text || "", choices: (q.choices || []).map(String) })) };
}

// the same answer roads the Assistant uses: one question -> /worker/answer, a group -> /worker/answers, all together
export function answerCall(taskId, ask, picks) {
  const qs = ask?.questions || [];
  if (qs.length === 1) return [`/api/tasks/${taskId}/worker/answer`, { request_id: qs[0].request_id, text: picks[qs[0].request_id] }];
  return [`/api/tasks/${taskId}/worker/answers`, { answers: Object.fromEntries(qs.map((q) => [q.request_id, picks[q.request_id]])) }];
}

// a group goes back whole: Send waits until every question has a pick
export const allPicked = (ask, picks) => (ask?.questions || []).every((q) => String(picks?.[q.request_id] || "").trim());
