// ONE READ OF A THING AT A TIME, SHARED (the owner's live app, 2026-11-16: six identical reads of one task's conversation in the same second,
// every few seconds - each view of the chat, each of its listeners, asking on its own): a read asked while the same one is on its way joins
// it and takes its answer; the next asked after it lands is a read of its own
export const shared = (inflight, key, start) => {
  if (!inflight.has(key)) inflight.set(key, Promise.resolve().then(start).finally(() => inflight.delete(key)));
  return inflight.get(key);
};
