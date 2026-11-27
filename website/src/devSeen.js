// DEVELOPER MODE AS THIS BROWSER LAST READ IT (walk 25, 2026-11-26: "Board appears and disappears" on the top bar). The setting reads off
// until /api/agents answers, so every load drew Chat · Game and then pushed Board in between them a beat later. What the last read said is
// kept here and drawn from the first frame; the read that follows corrects it only where the setting really moved. Never read yet: off,
// as before - no coding door flashes on a setup that has none. Pure, so node --test reads it.
const KEY = "taskuary_developer_mode";
export const devSeen = (store = globalThis.localStorage) => { try { return store?.getItem(KEY) === "1"; } catch { return false; } };
export const rememberDev = (on, store = globalThis.localStorage) => { try { store?.setItem(KEY, on ? "1" : "0"); } catch { /* private window: it reads again next load */ } };
