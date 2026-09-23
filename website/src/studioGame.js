// The Studio as a game: the office is the assistant, every real item has a place in it, and
// every real move you make earns points. Pure and dependency-free (test/studioGame.test.mjs) -
// the scene draws it, StudioView calls the real endpoints, this file only decides WHERE a thing
// lives, WHO should take it, and WHAT the move was worth.
//
// Nothing here reads words. A zone comes from the lane triage already judged, a match from the
// kind it already chose (no-hardcoded-words: the model reads intent, code only routes on it).

export const ZONES = [
  { key: "floor", name: "Agent Floor", hotkey: "1", blurb: "agents at their desks - jump into a code space" },
  { key: "lobby", name: "The Lobby", hotkey: "2", blurb: "people waiting on a reply from you" },
  { key: "coffee", name: "Coffee Room", hotkey: "3", blurb: "fyi's and reports - catch up over a cup" },
  { key: "archive", name: "Memory Archive", hotkey: "4", blurb: "filing cabinets of what the team knows - and the ghosts of threads that slipped" },
  { key: "hq", name: "Assistant Core", hotkey: "5", blurb: "ask who should take what" },
];
export const zoneMeta = (key) => ZONES.find((z) => z.key === key) || null;

const LANE_ZONE = {
  blocked: "floor", working: "floor", queued: "floor", stopped: "floor",
  approve: "lobby", asked: "lobby", yours: "lobby", time: "lobby", unjudged: "lobby",
  fyi: "coffee", report: "coffee", broken: "coffee",
  forgotten: "archive",
};
export const zoneOf = (item) => item?.kind === "agent" ? "floor" : LANE_ZONE[item?.lane] || "coffee";

export function zoneItems(items = []) {
  const out = { floor: [], lobby: [], coffee: [], archive: [], hq: [] };
  for (const i of items) out[zoneOf(i)].push(i);
  return out;
}

// what waits on YOU - the boss's health bar. fyi, reports and a working agent do not.
const ON_YOU = new Set(["blocked", "approve", "asked", "yours", "unjudged", "broken", "stopped"]);
export const needsYou = (item) => ON_YOU.has(item?.lane);
export const bossHp = (items = []) => items.filter(needsYou).length;

// The matchmaker: who is right for this, and the one move that gets it there. It routes on the
// judged lane/kind and on the agents actually configured - never on the subject line.
export function matchFor(item, agents = []) {
  const coder = agents.find((a) => a.Kind === "coding")?.Name || agents[0]?.Name || "the coder";
  const general = agents.find((a) => a.Kind && a.Kind !== "coding")?.Name || "the general agent";
  const lane = item?.lane, kind = item?.kind;
  if (kind === "agent" && lane === "blocked") return { who: item.working || item.agent || coder, verb: "answer", why: "an agent stopped for your call" };
  if (kind === "agent") return { who: item.working || item.agent || coder, verb: "watch", why: "already with an agent" };
  if (lane === "approve") return { who: "you", verb: "approve", why: "a draft is written - it only needs your yes" };
  if (lane === "forgotten") return { who: "you", verb: "followup", why: "gone quiet - a nudge keeps it alive" };
  if (lane === "fyi" || lane === "report") return { who: "nobody", verb: "read", why: "nothing to do but know it" };
  if (lane === "broken") return { who: "you", verb: "open", why: "a connection stopped - only you can sign it back in" };
  if (item?.coding || kind === "coding") return { who: coder, verb: "dispatch", kind: "coding", why: "code work - hand it to a coding agent" };
  if (kind === "todo" || kind === "task" || lane === "yours") return { who: general, verb: "dispatch", kind: "general", why: "real work, not a sentence - an agent can start it" };
  return { who: "you", verb: "draft", why: "a question a reply settles - let the assistant draft it" };
}

// ── points ────────────────────────────────────────────────────────────────────────────────────
export const XP = {
  answer: 60, dispatch: 45, approve: 40, followup: 35, file: 25, draft: 20, vote: 10,
  done: 12, read: 8, open: 5, ask: 5, pull: 3, later: 0, rest: 6,
};
export const MOVE_WORDS = {
  answer: "Unblocked an agent", dispatch: "Handed off", approve: "Reply sent", followup: "Ghost busted",
  file: "Filed to memory", draft: "Draft summoned", vote: "Upvoted a file", done: "Cleared", read: "Caught up",
  open: "Jumped in", ask: "Asked the core", pull: "Pulled a file", later: "Dodged", rest: "Laid to rest",
};

export const TITLES = ["Intern", "Inbox Rookie", "Reply Ranger", "Agent Wrangler", "Combo Clerk",
  "Thread Slayer", "Ghostbuster", "Chief of Vibes", "Office Legend", "Inbox Zero Deity"];
// level n starts at 50*n*(n+1) - quick early levels, a longer climb later
export const levelStart = (n) => 50 * n * (n + 1);
export function levelOf(xp = 0) {
  let n = 0;
  while (xp >= levelStart(n + 1)) n += 1;
  const lo = levelStart(n), hi = levelStart(n + 1);
  return { level: n + 1, title: TITLES[Math.min(n, TITLES.length - 1)], into: xp - lo, span: hi - lo, pct: (xp - lo) / (hi - lo) };
}

export const COMBO_WINDOW = 45000;   // ms between moves that keeps a streak alive
export const comboMult = (combo) => 1 + Math.min(4, Math.max(0, combo - 1)) * 0.25;

export const ACHIEVEMENTS = [
  { key: "first", name: "First Blood", says: "your first move in the office", test: (s) => s.moves >= 1 },
  { key: "unblock", name: "Unblocker", says: "answered an agent that was stuck", test: (s) => (s.by.answer || 0) >= 1 },
  { key: "handoff3", name: "Matchmaker", says: "handed 3 things to the right agent", test: (s) => (s.by.dispatch || 0) >= 3 },
  { key: "ghost3", name: "Ghostbuster", says: "busted 3 ghost threads", test: (s) => (s.by.followup || 0) + (s.by.rest || 0) >= 3 },
  { key: "coffee", name: "Coffee Break", says: "emptied the coffee room", test: (s, w) => w?.coffee === 0 && (s.by.read || 0) >= 1 },
  { key: "lobby", name: "Lobby Zero", says: "nobody left waiting in the lobby", test: (s, w) => w?.lobby === 0 && s.moves >= 1 },
  { key: "combo5", name: "On Fire", says: "a 5-move combo", test: (s) => s.best >= 5 },
  { key: "librarian", name: "Librarian", says: "filed a lesson to memory", test: (s) => (s.by.file || 0) >= 1 },
  { key: "sender", name: "Send It", says: "sent 5 replies", test: (s) => (s.by.approve || 0) >= 5 },
  { key: "century", name: "Triple Digits", says: "100 XP in one day", test: (s) => s.today >= 100 },
];

const day = (now) => new Date(now).toISOString().slice(0, 10);
export const fresh = (now = Date.now()) => ({ xp: 0, moves: 0, by: {}, dayBy: {}, quests: [], combo: 0, best: 0, lastAt: 0, day: day(now), today: 0, got: [], runStart: now });

// One move: the new state, what it was worth, and anything it unlocked. `world` is the live zone
// counts AFTER the move, so "empty the coffee room" is judged on the room, not on a guess.
export function award(state, move, now = Date.now(), world = null) {
  const s = { ...fresh(now), ...state, by: { ...(state?.by || {}) }, dayBy: { ...(state?.dayBy || {}) },
    quests: [...(state?.quests || [])], got: [...(state?.got || [])] };
  if (s.day !== day(now)) Object.assign(s, { day: day(now), today: 0, runStart: now, dayBy: {}, quests: [] });
  s.combo = now - s.lastAt <= COMBO_WINDOW ? s.combo + 1 : 1;
  const mult = comboMult(s.combo), gained = Math.round((XP[move] ?? 0) * mult);
  const before = levelOf(s.xp).level;
  Object.assign(s, { xp: s.xp + gained, today: s.today + gained, moves: s.moves + 1, lastAt: now, best: Math.max(s.best, s.combo) });
  s.by[move] = (s.by[move] || 0) + 1;
  s.dayBy[move] = (s.dayBy[move] || 0) + 1;
  const quests = QUESTS.filter((q) => !s.quests.includes(q.key) && s.dayBy[q.move] >= q.n);
  for (const q of quests) { s.quests.push(q.key); s.xp += q.xp; s.today += q.xp; }
  const unlocked = ACHIEVEMENTS.filter((a) => !s.got.includes(a.key) && a.test(s, world));
  s.got.push(...unlocked.map((a) => a.key));
  return { state: s, gained, mult, unlocked, quests, levelUp: levelOf(s.xp).level > before ? levelOf(s.xp) : null };
}

// daily quests read the day's tally - they reset with it
export const QUESTS = [
  { key: "q-reply", says: "Send 3 replies", move: "approve", n: 3, xp: 50 },
  { key: "q-hand", says: "Hand 2 things to agents", move: "dispatch", n: 2, xp: 50 },
  { key: "q-coffee", says: "Catch up on 4 fyi's", move: "read", n: 4, xp: 30 },
];
export const questProgress = (s, q) => Math.min(q.n, s?.dayBy?.[q.move] || 0);

const KEY = "taskuary.studioGame.v1";
export function loadGame(store = globalThis.localStorage, now = Date.now()) {
  try { const s = JSON.parse(store?.getItem(KEY) || "null"); return s && typeof s.xp === "number" ? { ...fresh(now), ...s } : fresh(now); }
  catch { return fresh(now); }
}
export function saveGame(s, store = globalThis.localStorage) { try { store?.setItem(KEY, JSON.stringify(s)); } catch { /* private window: the run still plays */ } }

// The share card is the viral part, and it is public the moment it is pasted: counts only, never a
// name, a subject or a sender.
export function shareCard(s, now = Date.now()) {
  const lv = levelOf(s.xp), secs = Math.max(0, Math.round((now - (s.runStart || now)) / 1000));
  const t = `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, "0")}`;
  const b = (k) => s.by?.[k] || 0;
  return [`🏢 Taskuary · Assistant Game`, `Lv ${lv.level} ${lv.title} · ${s.xp} XP · best combo x${s.best}`,
    `📨 ${b("approve")} sent  🤖 ${b("dispatch")} handed off  🔓 ${b("answer")} unblocked  👻 ${b("followup") + b("rest")} ghosts  ☕ ${b("read")} fyi`,
    `⏱ today's run ${t} · 🏆 ${s.got.length}/${ACHIEVEMENTS.length}`].join("\n");
}
