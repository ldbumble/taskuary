// WHICH MAILBOX A RULE IS FOR (Settings → Rules, the owner, 2026-10-20): "Applies to: All mailboxes / each connected sending
// mailbox", saved to the rule's Mailbox (policy.on_mailbox: blank is every mailbox, today's behaviour). The choice is shown only
// when more than one mailbox is connected - with one, every rule is that mailbox's anyway.
export const ALL_MAILBOXES = "All mailboxes";

// the menu's rows: [] when there is nothing to choose; a rule already scoped to a mailbox no longer connected keeps that row,
// so opening and saving it never widens it to every mailbox behind the owner's back
export function mailboxChoices(boxes, current = "") {
  const addrs = [...new Set((boxes || []).map((b) => String(b?.address || "").trim()).filter(Boolean))];
  if (addrs.length < 2) return [];
  const extra = String(current || "").split("|").map((s) => s.trim()).filter((s) => s && !addrs.some((a) => a.toLowerCase() === s.toLowerCase()));
  return [{ value: "", label: ALL_MAILBOXES }, ...addrs.map((a) => ({ value: a, label: a })),
    ...(extra.length ? [{ value: String(current), label: `${extra.join(", ")} (not connected)` }] : [])];
}

// the value the menu shows for a rule: its Mailbox matched to a connected address whatever its case, else as saved
export function mailboxValue(choices, current = "") {
  const c = String(current || "").trim();
  return (choices.find((o) => o.value.toLowerCase() === c.toLowerCase()) || { value: c }).value;
}
