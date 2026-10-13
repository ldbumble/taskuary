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
// it read (batch.act), so with nothing reviewed there is nothing to pin it to. The filled one is what the agent PROPOSED
// (--propose): a duplicate it says to close must not wear a filled Merge. Asking for changes is said on GitHub, so it opens it.
// FIX IT (batch.fix): where the review asked for changes, the changes made - by the batch's agent for our own people, in GitHub's
// cloud for an outsider (cloudfix.py). A fix that is done has its own pull request, and Merge merges that one.
export const fixing = (i) => i?.Fix === "running";
export function fixLine(i) {
  if (fixing(i)) return "Being fixed in GitHub's cloud…";
  if (i?.Fix === "done") return "Fixed in GitHub's cloud - its pull request is ready to merge.";
  if (i?.Fix === "failed") return "The cloud fix did not work.";
  return "";
}
export function actions(i) {
  if (!i) return [];
  if (fixing(i)) return [];
  if (!isOpen(i)) return [{ action: "reopen", label: "Open again" }];
  if (i.State !== "needs_you") return [{ action: "settle", label: "Nothing to do" }];
  const p = i.Propose, fixed = i.Fix === "done";
  const canFix = isPull(i) && p === "changes" && i.canFix !== false;
  const all = [...(canFix ? [{ action: "fix", label: i.Fix === "failed" ? "Fix it again" : "Fix it", primary: true }] : []),
    ...(i.Link && p === "changes" ? [{ action: "open", label: "Ask for changes", href: i.Link, primary: !canFix }] : []),
    ...(fixed && i.FixLink ? [{ action: "open-fix", label: "See the fix", href: i.FixLink }] : []),
    ...(isPull(i) && i.reviewed ? [{ action: "merge", label: fixed ? "Merge the fix" : "Merge", primary: p === "merge" }] : []),
    ...(isPull(i) ? [{ action: "close", label: "Close it", primary: p === "close" }] : []), { action: "settle", label: "Nothing to do" }];
  return [...all.filter((a) => a.primary), ...all.filter((a) => !a.primary)];
}

// "2 of 4 done · ③ needs you" - the rail's second line and the block's heading
export function progress(items) {
  const its = items || [];
  if (!its.length) return "";
  const settled = its.filter((i) => !isOpen(i)).length;
  const you = its.filter((i) => i.State === "needs_you").map((i) => circled(i.Place));
  return [`${settled} of ${its.length} done`, you.length ? `${you.join("")} need${you.length === 1 ? "s" : ""} you` : ""].filter(Boolean).join(" · ");
}

// the rail row's own height has room for a count, not a sentence: "1/4" (settled of all)
export const railShort = (states) => `${(states || []).filter((st) => !OPEN.includes(st)).length}/${(states || []).length}`;
