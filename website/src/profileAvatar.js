// THE OWNER'S FACE IN THE CORNER (the owner, 2026-11-06: "about you should not be in menu on sidebar. it should be profile in corner which
// is the profile picture that is the about you page in top right corner next to the power button"). Pure, for test/profileButton.test.mjs.
// The picture is the avatar About you already draws (whoami.avatar_svg, its style and seed kept there); the initials stand in until it is
// read, or where there is none. The same rule as whoami.initials: first and last word, "T" for no name.
export const PROFILE_TIP = "About you";
// the event About you sends when the name or the avatar changes, so the corner redraws without a reload
export const PROFILE_CHANGED = "tq-profile-changed";
export const initialsOf = (name) => {
  const n = String(name || "").trim().toLowerCase() === "the owner" ? "" : String(name || "");     // the template's stand-in is no name
  const ps = n.replace(/-/g, " ").split(/\s+/).filter((p) => p && /^[\p{L}\p{N}]/u.test(p));
  return ps.length ? (ps[0][0] + (ps.length > 1 ? ps[ps.length - 1][0] : "")).toUpperCase() : "?";   // no name yet: a question, never Taskuary's T
};
export const svgUri = (svg) => `data:image/svg+xml;utf8,${encodeURIComponent(svg || "")}`;
// what /api/whoami answers, as the corner draws it: the picture when there is one, the initials always (the img's alt, and its fallback)
export const profileFace = (p) => ({ initials: initialsOf(p?.facts?.owner_name), name: p?.facts?.owner_name || "",
  pic: /^\s*<svg[\s>]/.test(String(p?.avatar || "")) ? svgUri(p.avatar) : "" });
