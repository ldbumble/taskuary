// One road for every task-view button (PW-215): propose, then execute by id and version - the same two
// endpoints the assistant's confirmation card uses, so target checks, freshness, errors and the recorded
// outcome are identical whichever door the owner came through. No phrase is interpreted here: the kind
// is the button's, the params are its fields.
export async function runOperation(api, kind, target, params = {}) {
  const { data: op } = await api.post("/api/operations", { kind, target, params });
  const { data } = await api.post(`/api/operations/${op.id}/execute`, { version: op.version });
  // A halt carries its own outcome - "a repository still to choose", say - and the caller needs it
  // to ask the right question. Throwing the sentence alone left the task page with a 422 it could
  // only print (2026-09-22).
  if (data?.status === "error") {
    const err = new Error(data.error || `${kind} did not run`);
    err.outcome = data.outcome ?? null;
    throw err;
  }
  return data?.outcome ?? data;
}
