// THE BOX A PRESS OPENED A TASK FOR (the owner, 2026-11-13, on a report: "when you hit send to agent it should look like every task with coming
// from and then you should be able to write what you want"): the press made the task and put it on the table; its chat's box takes the cursor once
// it is drawn (GeneralWorkspace), whichever comes first - the press or the chat.
// ...for the few seconds the task takes to settle, not once: its chat is drawn again as the page reads the new task, and a box focused on the
// first draw went with it - the cursor was nowhere (the recorded walk, 2026-11-13)
const WANT = new Map(), HOLD = 4000;
export const wantBox = (tid, now = Date.now()) => {
  if (!tid) return;
  WANT.set(Number(tid), now);
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent("tq-want-box", { detail: { tid: Number(tid) } }));
};
export const takeBox = (tid, now = Date.now()) => now - (WANT.get(Number(tid)) ?? -Infinity) < HOLD;
