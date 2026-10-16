// WHICH MODEL A WORKFLOW RUNS ON (the owner, 2026-10-16: "Workflow by default should use same brain as agents - general agents but
// they can choose for hard workflow to use higher level model and effort"). `brain` is GET /api/workflows/brain (workflows.brain_options):
// the general agents' brain, its models, and per model only the efforts that CLI can be told - an effort it cannot take is never offered.
export const modelChoices = (brain) => !brain ? [] : [
  { value: "", label: `Same as general agents${brain.said ? ` (${brain.said})` : ""}` },
  ...(brain.models || []).map((m) => ({ value: m.id, label: m.label && m.label !== m.id ? `${m.label} (${m.id})` : m.id })),
];

// the efforts for the model the run will use: the chosen one's, else the brain's own model's - [] where the CLI has no effort flag
export function effortChoices(brain, model) {
  const m = model && (brain?.models || []).find((x) => x.id === model);
  const efforts = m ? m.efforts || [] : brain?.efforts || [];
  return efforts.length ? [{ value: "", label: "Default effort" }, ...efforts.map((e) => ({ value: e, label: e }))] : [];
}

// ...and a saved effort the newly chosen model cannot take is cleared, not carried to a CLI that would refuse it
export const keepEffort = (brain, model, effort) => effortChoices(brain, model).some((c) => c.value === effort) ? effort : "";
