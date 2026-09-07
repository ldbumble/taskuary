// Which provider the workspace's picker should show, and therefore which one a message is sent to.
//
// It used to be `providers[0]`, and provider_options lists CLIs before API brains - so a general
// task with no session nominated a CODING agent, showed "Claude Code · coder (your CLI)", and posted
// that as its pick (TQ-0420: a research question answered by a coder in a checkout). The server
// already makes this decision for itself in general._selected and now says so as `defaultPick`;
// a live session's own choice still outranks it.
export const pickFor = (payload) => {
  const providers = payload?.providers || [];
  if (!providers.length) return null;
  const by = (id) => providers.find((p) => String(p.id) === String(id));
  return by(payload?.session?.pick)
    || providers.find((p) => p.label === payload?.session?.provider)
    || by(payload?.defaultPick)
    || providers[0];
};
