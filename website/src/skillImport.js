// Pure logic behind the skill-import wizard (SkillImport.jsx), kept in its own module so it can be
// exercised directly by a test instead of only grepped for in the markup.

// Mirrors taskuary/skillimport.py's save(): the server slugifies a name before writing it, and
// returns THAT slug in /api/skills/import's response. Kept in exactly one place so the wizard's own
// idea of a name can never drift from the server's second copy of the same rule - callers normalise
// a name through this function rather than comparing against one.
export const slug = (s) => String(s || "").trim().toLowerCase()
  .replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "");

// The rows an import call is about to send, turned into /api/skills/import items. Names are slugged
// here too, so what is SENT is exactly what the server will store and echo back - an owner typing
// "My Skill" sends "my-skill", not a name the server will silently reshape on its own.
export const buildPayload = (rows) => rows.filter((r) => !r.imported).map((r) => ({
  name: slug(r.name), purpose: r.purpose, body: r.body, kind: r.kind,
  enabled: !!r.enabled, replace: !!r.replace,
}));

// Fold an /api/skills/import response back onto the rows. Matching happens on the SLUGGED name on
// both sides - the response names slugs, and slug(r.name) is what was actually sent - so a row never
// gets stuck in "pending" (and Done stays unreachable) just because the owner typed a name the
// server reshaped before writing it.
export const reconcileImport = (rows, data) => {
  const clashed = new Map((data.clashed || []).map((c) => [c.name, c.kind]));
  const wrote = new Set(data.imported || []);
  return rows.map((r) => {
    if (r.imported) return r;
    const name = slug(r.name);
    if (wrote.has(name)) return { ...r, name, imported: true, clash: null, replace: false };
    if (clashed.has(name)) return { ...r, name, clash: clashed.get(name) };
    return r;
  });
};
