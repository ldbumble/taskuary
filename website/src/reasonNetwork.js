// The Reason Network card's words and its trust list, apart from React so node tests read them (test/reasonNetwork.test.mjs).
// The list is the server's rule as well (reasonnet.clean_trusted): people (erin) and single sessions (erin/api-claude),
// lower case, no machine, never a group - a star or a repo: line would let a whole team in by one entry.
const NAME = "[a-z0-9][a-z0-9._-]*";
const ADDR = new RegExp(`^${NAME}(/${NAME})?$`);

export const cleanOne = (x) => String(x || "").trim().toLowerCase().split("@")[0];

export function cleanTrusted(list) {
  const out = [];
  for (const x of list || []) {
    const v = cleanOne(x);
    if (v && ADDR.test(v) && !out.includes(v)) out.push(v);
  }
  return out;
}

// whom an address is trusted as: the whole person, that one session, or not at all ("" for the owner: always theirs)
export function trustOf(trusted, address, me = "") {
  const a = cleanOne(address), person = a.split("/")[0];
  if (me && person === cleanOne(me)) return "you";
  const t = cleanTrusted(trusted);
  return t.includes(person) ? "person" : t.includes(a) ? "session" : "";
}

export const withTrust = (trusted, x) => cleanTrusted([...(trusted || []), x]);
export const withoutTrust = (trusted, x) => cleanTrusted(trusted).filter((t) => t !== cleanOne(x));

// one line per session, the way `reason-network who` reads: what it is and what it is doing now
export function sessionLine(s) {
  const where = s.repo ? `${s.repo}${s.branch ? `@${s.branch}` : ""}` : "";
  return [s.agent, where, s.status, s.doing].filter(Boolean).join(" · ");
}

export function gateWords(gate) {
  if (!gate) return "";
  if (gate.on) return "On: Reason Network holds every message from anyone you have not trusted below. It reaches no agent on this computer until you deliver it.";
  return `Off: Reason Network's own setting decides (it ${gate.default === "refuse" ? "refuses" : gate.default === "hold" ? "holds" : "delivers"} teammates' messages).`;
}
