// The first-run review waits for evidence, rather than calling a started request a result.
export async function startFirstSync(api) {
  const { data } = await api.post("/api/ingest/poll");
  if (!["running", "busy"].includes(data?.report)) throw new Error("The source read did not start. Try again.");
  return data.report;
}

export async function firstSyncProgress(api) {
  const [ingest, setup] = await Promise.all([api.get("/api/ingest/status"), api.get("/api/setup")]);
  const status = ingest.data || {}, state = setup.data || {};
  const problems = [status.failed?.length ? `Check these connections: ${status.failed.join(", ")}.` : "",
    status.triageError || ""].filter(Boolean);
  if (problems.length) return { phase: "failed", message: problems.join(" "), state };
  if (state.pending) return { phase: "reading", message: "Items have arrived; the AI is reading them.", state };
  if (status.status?.state === "running")
    return { phase: "reading", message: status.status.what || "Reading your connected sources…", state };
  if (state.steps?.find((step) => step.key === "sync")?.done)
    return { phase: "ready", message: "Your first items are ready. Open one to check its verdict or draft.", state };
  return { phase: "empty", message: "The read finished without a reviewable item. Check the source scope, or send a new message to the connected account and read again.", state };
}
