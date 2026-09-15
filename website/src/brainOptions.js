// Normalize the brain catalogue at the UI boundary as well as on the server. A browser may be
// reloaded against a Taskuary process that has not restarted yet; older /api/brains responses
// contain one CLI row per profile (coder, researcher, analyst...) even though those are all the
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
    // "claude · coder" and "claude (your CLI)" both reduce to "claude".
    const cli = info.cli || info.cmd || String(row.label || profile).split(/\s(?:·|\()/, 1)[0] || profile;
    const identity = `cli:${cli}`;
    if (seen.has(identity)) return [];
    seen.add(identity);
    return [{ ...row, label: `${cli} (your CLI)`, cli,
      models: row.models?.length ? row.models : (info.choices || []) }];
  });
}
