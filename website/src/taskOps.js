// One road for every task-view button (PW-215): propose, then execute by id and version - the same two
// endpoints the assistant's confirmation card uses, so target checks, freshness, errors and the recorded
// outcome are identical whichever door the owner came through. No phrase is interpreted here: the kind
// is the button's, the params are its fields.
export async function runOperation(api, kind, target, params = {}) {
  const { data: op } = await api.post("/api/operations", { kind, target, params });
  const { data } = await api.post(`/api/operations/${op.id}/execute`, { version: op.version });
  if (data?.status === "error") throw new Error(data.error || `${kind} did not run`);
  return data?.outcome ?? data;
}
