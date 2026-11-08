// A VIDEO TOOL'S SIGN IN (the owner, 2026-11-08: one press, then "Signed in"): the button's state from the card's (videotools.state) -
// "" with no MCP server added (or none at all: a skill), "out" / "signing" / "in" by what each CLI that has it says, "demo" in the demo
export const signState = (st) => {
  if (!st?.url) return "";
  if (st.demo) return "demo";
  const on = Object.values(st.clis || {}).filter((v) => v.added);
  return !on.length ? "" : on.every((v) => v.signed_in) ? "in" : on.some((v) => v.signing_in) ? "signing" : "out";
};
export const SIGN_LABEL = { out: "Sign in", signing: "Signing in…", in: "Signed in" };
