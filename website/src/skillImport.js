// Pure logic behind the skill-import wizard (SkillImport.jsx), kept in its own module so it can be
// exercised directly by a test instead of only grepped for in the markup.

// Mirrors taskuary/skillimport.py's save(): the server slugifies a name before writing it, and
// returns THAT slug in /api/skills/import's response. Kept in exactly one place so the wizard's own
// idea of a name can never drift from the server's second copy of the same rule - callers normalise
// a name through this function rather than comparing against one.
export const slug = (s) => String(s || "").trim().toLowerCase()
  .replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "");

// Where the owner's text points: a link goes to /api/skills/fetch, anything else is a path on this
// machine for /api/skills/read. One field, two doors, decided here so the wizard has no second copy.
export const isLink = (s) => /^https?:\/\//i.test(String(s || "").trim());

// The proposals a read or fetch returned, as wizard rows. `include` is the owner's choice of WHICH
// ones become profiles: a single skill is presumably wanted; a repository of forty is a catalogue to
// pick from, so those start unticked. `enabled` (offer to the router) always starts off.
export const toRows = (data) => {
  const one = (data || []).length === 1;
  return (data || []).map((r) => ({ ...r, name: slug(r.name), include: one, enabled: false, replace: false, clash: null, imported: false }));
};

// The rows an import is about: chosen, and not yet written.
export const chosen = (rows) => rows.filter((r) => r.include && !r.imported);

// The rows an import call is about to send, turned into /api/skills/import items. Names are slugged
// here too, so what is SENT is exactly what the server will store and echo back - an owner typing
// "My Skill" sends "my-skill", not a name the server will silently reshape on its own.
export const buildPayload = (rows) => chosen(rows).map((r) => ({
  name: slug(r.name), purpose: r.purpose, body: r.body, kind: r.kind,
  enabled: !!r.enabled, replace: !!r.replace,
}));

// Fold an /api/skills/import response back onto the rows. Matching happens on the SLUGGED name on
// both sides - the response names slugs, and slug(r.name) is what was actually sent - so a row never
// gets stuck in "pending" (and Done stays unreachable) just because the owner typed a name the
// server reshaped before writing it.
// A clash is {kind, doc}: `doc` names an OPERATOR DOCUMENT (soul, triage, agent, style...) the name
// would have rewritten - those have no profile row to collide with, so the word "profile" would be
// the wrong one to show for them.
export const reconcileImport = (rows, data) => {
  const clashed = new Map((data.clashed || []).map((c) => [c.name, { kind: c.kind || "", doc: c.doc || "" }]));
  const wrote = new Set(data.imported || []);
  return rows.map((r) => {
    if (r.imported) return r;
    const name = slug(r.name);
    if (wrote.has(name)) return { ...r, name, imported: true, clash: null, replace: false };
    if (clashed.has(name)) return { ...r, name, clash: clashed.get(name) };
    return r;
  });
};

// What a clash chip says, and what the Overwrite confirm must name: the thing that would be destroyed.
export const clashText = (c) => (c?.doc
  ? `would rewrite ${c.doc.toUpperCase()}.md - an operator document, not a profile`
  : `clashes with an existing "${c?.kind}" profile`);

// Whether a body arrives whole. `flat` and `docChars` both come from the server (/api/skills/read):
// the flattened length is the seed's own measure and DOC_CHARS its own cut, so this is not a second
// rule about size, it is the first one, reported. Returns the characters that would be cut, or 0.
export const cutBy = (r, docChars) => (r?.flat > docChars && docChars > 0 ? r.flat - docChars : 0);
