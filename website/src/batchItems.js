// A batch's items (batch.py): the ranked arrivals of one repository, let in as one task and worked top-down by a read-only
// agent. One shape for the task page and the rail: what each item's state is called, what the owner may press on it, and
// the one line that says how far the batch got.

export const CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳";
export const circled = (n) => CIRCLED[n - 1] || String(n);
const OPEN = ["waiting", "working", "needs_you"];
export const isOpen = (i) => OPEN.includes(i?.State);

// the state, in words - "needs you" is the only one that shouts
export const stateWord = (i) => ({ waiting: "not yet read", working: "reading", needs_you: "needs you", done: "done",
  ended: (i?.EndedWhy || "").toLowerCase().includes("merged") ? "merged" : "closed" })[i?.State] || i?.State || "";

const isPull = (i) => /github\.com\/[^/]+\/[^/]+\/pull\/\d+/.test(i?.Link || "");

// what the owner can press on one line. Merge only on a pull request the agent has reviewed: the merge is pinned to the head
// it read (batch.act), so with nothing reviewed there is nothing to pin it to.
export function actions(i) {
  if (!i) return [];
  if (!isOpen(i)) return [{ action: "reopen", label: "Open again" }];
  if (i.State !== "needs_you") return [{ action: "settle", label: "Nothing to do" }];
  return [...(isPull(i) && i.reviewed ? [{ action: "merge", label: "Merge", primary: true }] : []),
    ...(isPull(i) ? [{ action: "close", label: "Close it" }] : []), { action: "settle", label: "Nothing to do" }];
}

// "2 of 4 done · ③ needs you" - the rail's second line and the block's heading
export function progress(items) {
  const its = items || [];
  if (!its.length) return "";
  const settled = its.filter((i) => !isOpen(i)).length;
  const you = its.filter((i) => i.State === "needs_you").map((i) => circled(i.Place));
  return [`${settled} of ${its.length} done`, you.length ? `${you.join("")} need${you.length === 1 ? "s" : ""} you` : ""].filter(Boolean).join(" · ");
}
