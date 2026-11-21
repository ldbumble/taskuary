// WHAT AGENTS MAY DO IN A CONNECTED SYSTEM, AS ONE STATE (the design walk, 2026-11-20): Settings' Agent permissions drew "Full authority
// (default)" in its picker beside an "Off for agents" button - two answers on one row, one of them a button that read as the state. A
// connection is off for agents (no `tool` role) or on at one level of authority; one picker shows which, and picking one saves it.
export const ACCESS = { off: "Off for agents", read: "Read only", write: "Read and write", admin: "Full authority" };
const rolesOf = (c) => new Set(String(c?.Roles || "").split(",").map((r) => r.trim()).filter(Boolean));
export const accessOf = (c) => (rolesOf(c).has("tool") ? String(c.Scope || c.ScopeDefault || "read").toLowerCase() : "off");
// ...the save for a pick: off takes the role away and leaves the level as it was; a level gives the role back with that level
export const accessSave = (c, k) => {
  const roles = rolesOf(c);
  if (k === "off") { roles.delete("tool"); return { Roles: [...roles].join(",") }; }
  roles.add("tool"); return { Roles: [...roles].join(","), Scope: k };
};
