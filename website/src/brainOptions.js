// Normalize the brain catalogue at the UI boundary as well as on the server. A browser may be
// reloaded against a Taskuary process that has not restarted yet; older /api/brains responses
// contain one CLI row per profile (coding, researcher, analyst...) even though those are all the
// same Claude executable. Keep a selected legacy value when possible, but show each CLI once.
import { localName } from "./words.js";

export function normalizeBrainOptions(rows = [], agentModels = {}, selected = []) {
  const wanted = new Map((selected || []).filter(Boolean).map((v, i) => [v, i]));
  const ordered = [...(rows || [])].sort((a, b) =>
    (wanted.get(a.value) ?? Number.MAX_SAFE_INTEGER) - (wanted.get(b.value) ?? Number.MAX_SAFE_INTEGER));
  const seen = new Set();
  return ordered.flatMap((row) => {
    if (!String(row.value || "").startsWith("cli:")) return [row];
    const profile = String(row.value).slice(4);
    const info = agentModels[profile] || {};
    // New servers provide info.cli. The label prefix is the compatibility road for an old one:
    // "claude · coding" and "claude (your CLI)" both reduce to "claude".
    const cli = info.cli || info.cmd || String(row.label || profile).split(/\s(?:·|\()/, 1)[0] || profile;
    const identity = `cli:${cli}`;
    if (seen.has(identity)) return [];
    seen.add(identity);
    // ...said in plain words: "(your CLI)" stood on the agent card as code-speak (the walk's WORDS, 2026-10-18)
    return [{ ...row, label: localName(cli), cli,
      models: row.models?.length ? row.models : (info.choices || []) }];
  });
}

// THE CODING PICKER LISTS EVERY AI THAT CAN CODE (the owner, 2026-11-09: "fix the picker ... it should choose the correct one"): each
// connected CLI and each active AI card, from /api/agents' coding_options. A CLI is chosen as `brain` (its key), a card as `pick`
// (`connector:<id>`) - the two fields the dispatch reads. Nothing chosen shows what a start would run: coding_pick, the server's own
// resolve_brain answer. An old server without coding_options gets its CLI keys, as before.
export function codingChoices({ options, brains = [], brain = "", pick = "", codingPick = "" } = {}) {
  const list = options?.length ? options : brains.map((k) => ({ value: `cli:${k}`, key: k, kind: "cli", label: k }));
  const chosen = brain ? `cli:${brain}` : String(pick || "").startsWith("connector:") ? pick : "";
  const value = chosen || (list.some((o) => o.value === codingPick) ? codingPick : list[0]?.value || "");
  // a brain the task names that is gone is still what it names - never silently the first entry
  const gone = chosen && !list.some((o) => o.value === chosen)
    ? [{ value: chosen, kind: chosen.startsWith("cli:") ? "cli" : "card", label: `${chosen.replace(/^cli:/, "")} · not connected` }] : [];
  return { list: [...gone, ...list], value };
}
// what choosing one sends: { brain, pick } with the other cleared
export const codingChoice = (v) => String(v).startsWith("cli:") ? { brain: String(v).slice(4), pick: "" } : { brain: "", pick: String(v) };
