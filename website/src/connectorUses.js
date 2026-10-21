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
