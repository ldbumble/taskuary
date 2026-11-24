// Normalize the brain catalogue at the UI boundary as well as on the server. A browser may be
// reloaded against a Taskuary process that has not restarted yet; older /api/brains responses
// contain one CLI row per profile (coding, researcher, analyst...) even though those are all the
// same Claude executable. Keep a selected legacy value when possible, but show each CLI once.

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
    // ...BY ITS ONE NAME, the server's (clis.name_of: "Claude Code", decided 2026-11-12) - never "claude (on this computer)" beside "Claude Code"
    // on the next screen; an old server's "claude · coding" is its command
    return [{ ...row, label: /\s(?:·|\()/.test(row.label || "") || !row.label ? cli : row.label, cli,
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

// HAND THE TASK TO ANOTHER AI (the owner, 2026-11-18: "we need button on top of every task to change the backend of this both model, and
// provider of whatever is available in app"): every AI ready here - a coding task's coding_options, any other's general brains - each with
// its models, the one at work marked (`now`). `current` is its pick (`cli:<key>` / `connector:<id>`), `model` the model it runs.
// `why` is the reason the control is greyed: there is nothing else to hand it to.
export const SHOWN = 3;
const modelRows = (ms = []) => ms.map((m) => (typeof m === "string" ? { id: m, label: m } : { id: m?.id, label: m?.label || m?.id })).filter((m) => m.id);
// `named`: the AI's own name where its pick is not one of the rows (the server's willRun / ranOn brain) - the pill says it rather than nothing
export function switchChoices({ coding = false, codingOptions = [], generalBrains = [], brainModels = {}, current = "", model = "", read = true, named: own = "" } = {}) {
  const cardModels = (pick) => generalBrains.find((b) => b.pick === pick)?.models;
  const ais = coding
    ? codingOptions.filter((o) => o.ready !== false).map((o) => ({ pick: o.value, label: o.label,
        models: modelRows(o.kind === "cli" ? brainModels[o.key]?.models || brainModels[o.key]?.choices : cardModels(o.value)) }))
    : generalBrains.map((b) => ({ pick: b.pick, label: b.label, models: modelRows(b.models) }));
  const on = ais.find((a) => a.pick === current), named = on?.models.some((m) => m.id === model) ? model : "";
  // ...EACH AI ITS FEW MODELS (the 2026-11-18 walk: sixteen model names for one AI): its default and the first SHOWN of the list, the one at
  // work always - the rest `more`, folded under the AI's own "More models" until asked for
  const rows = ais.flatMap((a) => [{ pick: a.pick, model: "", label: a.label, now: a === on && !named },
    ...a.models.map((m, i) => ({ pick: a.pick, model: m.id, label: m.label, ai: a.label, now: a === on && m.id === named,
      ...(i >= SHOWN && !(a === on && m.id === named) ? { more: true } : {}) }))]);
  // ...and THE PILL NAMES THE MODEL ITS TICK MARKS (the owner, 2026-11-23: "why does this say both claude and codex????" - Codex ticked at its
  // default under a pill reading "Codex · claude-sonnet"): a model its AI does not list is that AI's default; with no list read, as given
  const shown = on?.models.length ? named : model;
  const said = on ? `${on.label}${shown ? ` · ${shown}` : ""}` : own ? `${own}${model ? ` · ${model}` : ""}` : "";
  const why = !read ? "Reading which AIs are ready…" : !ais.length ? "No AI is connected - connect one under Connections."
    : rows.length === 1 || rows.every((r) => r.now) ? "Only one AI is ready - connect another under Connections to hand this to it." : "";
  return { rows, said, why };
}
