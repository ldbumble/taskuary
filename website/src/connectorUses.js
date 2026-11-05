// The line beside a card's Remove: what leans on the connection (/api/connectors/{id}/uses, dependents.py), said before the
// press (#238). One of a kind is named, several are counted; drafts and sources are only ever counted.
const WORDS = {
  workflow: ["workflow", "workflows"], report: ["report", "reports"], brain: ["", "AI brains"], card: ["card", "cards"],
  draft: ["reply draft waiting", "reply drafts waiting", true], rule: ["rule", "rules"], playbook: ["playbook", "playbooks"],
  source: ["source it reads", "sources it reads", true],
};

const one = (name, word) => `the ${name}${!word || name.toLowerCase().endsWith(word) ? "" : ` ${word}`}`;

export function usedBy(rows) {
  const said = (rows || []).filter((r) => r?.names?.length).map(({ kind, names }) => {
    const [w1, wn, counted] = WORDS[kind] || [kind, `${kind}s`];
    const n = names.length;
    return n === 1 && !counted && names[0] ? one(names[0], w1) : `${n} ${n === 1 ? w1 || kind : wn}`;
  });
  return said.length ? `Used by: ${said.join(", ")}` : "";
}

// REMOVE ASKS ONCE, AND SAYS WHAT IT MEANS (the owner, 2026-11-05: "it should go away"): one press, one question - the card's name,
// what stays (what it brought in), what it takes (its sign-in, its settings), and what leaning on it stops working (#238)
const KEPT = { email: "Its mail stays in Taskuary.", ai: "", data: "" };
export function removeWords(conn, channel, rows) {
  const name = conn?.Name || conn?.Type || "this connection";
  const kept = channel in KEPT ? KEPT[channel] : channel ? "What it brought in stays in Taskuary." : "";
  const used = usedBy(rows).replace(/^Used by: /, "");
  return { title: `Remove ${name}?`,
    text: [kept, `Its sign-in and settings are wiped${channel && !(channel in KEPT && !KEPT[channel]) ? " and it stops reading" : ""}.`,
      used && `Still using it, and stopping with it: ${used}.`, "Undo on the list brings it back for ten minutes."]
      .filter(Boolean).join(" ") };
}
