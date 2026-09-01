// A desktop process can stay alive while a freshly built UI is picked up from disk. The newer
// continuation route preserves the exact checkout; an older process still has /dispatch, which
// can reopen the saved coder with the owner's instruction instead of surfacing a raw route 404.
const routeMissing = (error) => error?.response?.status === 404
  && error?.response?.data?.detail === "Not Found";

export async function continueCoding(client, taskId, instruction, agent) {
  try {
    return await client.post(`/api/tasks/${taskId}/continue`, { instruction });
  } catch (error) {
    if (!routeMissing(error)) throw error;
    return client.post(`/api/tasks/${taskId}/dispatch`, { agent, instruction });
  }
}

