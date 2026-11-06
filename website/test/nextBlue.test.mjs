// NEXT TURNS BLUE AS SOON AS THE MOVE SAVES (the owner, 2026-11-06, revising 11-03's "Next greys until the move lands"): a walk move asks for
// the light answer - the move and the walk's word, no rail rebuilt for it - so Next is free the moment that answer is in, and the rail is read
// behind it. A second press before that rail lands still moves one row on from the row on screen: never a skip, never a double move.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";
import { pressOnto, walkOf, withWalk } from "../src/funnelPile.js";

const read = (n) => readFileSync(fileURLToPath(new URL(`../src/${n}`, import.meta.url)), "utf8");
const view = read("AssistantView.jsx");

test("every walk move asks for the light answer, and the press frees Next once it is drawn - the rail is never awaited", () => {
  const turn = view.slice(view.indexOf("const turnOnce = useCallback"), view.indexOf("const turn = useCallback"));
  assert.match(turn, /api\.post\(`\/api\/walk\/\$\{walkRoute\}`, \{[^]*?fyi: fyiWant\.current, light: true,/);
  const landed = view.slice(view.indexOf("const landed = useCallback"), view.indexOf("const noteLine = useCallback"));
  assert.match(landed, /else \{ const p = withWalk\(pileRef\.current, data\.walk\); if \(p !== pileRef\.current\) \{ pileRef\.current = p; setPile\(p\); \} loadPile\(true\); \}/);
  assert.doesNotMatch(landed, /await loadPile/, "the answer waits on the rail read behind it");
  const surface = view.slice(view.indexOf("const surface = useCallback"), view.indexOf("useEffect(() => { surfaceRef.current = surface; }"));
  assert.match(surface, /else landed\(data, off\(\)\);[^]*turnFlight\.current = false;\n\s+setBusy\(false\); setFlight\(null\);/, "busy drops right after the answer is drawn");
});

test("withWalk: only a whole walk word (one naming `below`) is taken, onto the same rail rows", () => {
  const pile = { items: [{ key: "a" }], walk: { on: "a", below: "b", above: null } };
  const p = withWalk(pile, { on: "b", below: "c", above: "a", members: [] });
  assert.equal(p.items, pile.items); assert.deepEqual(walkOf(p), { on: "b", below: "c", above: "a", members: [] });
  assert.equal(withWalk(pile, { on: "b", above: "a" }), pile, "a heavy answer's walk (no below) leaves the rail alone");
  assert.equal(withWalk(null, { on: "b", below: "c" }), null);
});

// the server's walk over four rows, and the page as surface() drives it: press, light answer, Next free, the rail read behind
const ROWS = ["A", "B", "C", "D"];
const server = () => {
  let on = null; const seen = new Map(), moves = [];
  const word = () => { const i = ROWS.indexOf(on); return { on, members: [], above: ROWS[i - 1] || null, below: ROWS[i + 1] || null }; };
  return { moves, rail: () => ({ items: ROWS.map((key) => ({ key })), walk: word() }),
    post(route, { from_key, press }) {
      if (seen.has(press)) return seen.get(press);              // one press, one answer (railwalk._remember)
      const i = ROWS.indexOf(from_key); on = route === "start" ? ROWS[0] : route === "back" ? ROWS[Math.max(0, i - 1)] : ROWS[i + 1] || null;
      moves.push(on); const out = { item: on ? { key: on } : null, walk: word(), pile: null };
      seen.set(press, out); return out;
    } };
};
const page = (srv) => {
  const pg = { pile: srv.rail(), current: null, busy: false, drawn: [], n: 0 };
  pg.press = async (how = "next", { railLands = false } = {}) => {
    if (pg.busy) return "BUSY";                                  // one move at a time: a press over one out does nothing
    pg.busy = true;
    const fromKey = how === "start" ? null : pg.current, putDown = how === "next" ? fromKey : null;
    const { below } = pressOnto(walkOf(pg.pile), pg.pile.items, { putDown, how, fromKey, card: pg.current ? { key: pg.current } : null });
    if (below) { pg.drawn.push(`ahead:${below}`); pg.current = below; }
    const data = await Promise.resolve(srv.post(how, { from_key: fromKey, press: `p${++pg.n}` }));
    pg.current = data.item?.key || pg.current; pg.drawn.push(`landed:${pg.current}`);
    pg.pile = withWalk(pg.pile, data.walk);
    if (railLands) pg.pile = srv.rail();                         // the rail read behind the answer - here, before the next press or not
    pg.busy = false;
    return data;
  };
  return pg;
};

test("rapid presses with the rail never landing in between: each moves one row on, drawn at its press", async () => {
  const srv = server(), pg = page(srv);
  await pg.press("start");
  for (const want of ["B", "C", "D"]) { assert.equal(pg.busy, false, "Next is free once the answer is in"); assert.equal((await pg.press()).item.key, want); }
  assert.deepEqual(srv.moves, ["A", "B", "C", "D"], "no row skipped, none moved twice");
  assert.deepEqual(pg.drawn.filter((d) => d.startsWith("ahead:")), ["ahead:B", "ahead:C", "ahead:D"], "each next row drawn at its press from the light walk word");
  assert.equal(walkOf(pg.pile).below, null, "and on the last row Next has nothing below - it goes before the rail lands");
});

test("a double press while one is out is one move; Back after a light Next draws the row above at once", async () => {
  const srv = server(), pg = page(srv);
  await pg.press("start");
  const [one, two] = await Promise.all([pg.press(), pg.press()]);
  assert.equal(one.item.key, "B"); assert.equal(two, "BUSY");
  assert.deepEqual(srv.moves, ["A", "B"], "the second click over the first is no move");
  await pg.press("back");
  assert.equal(pg.drawn.at(-2), "ahead:A"); assert.equal(pg.current, "A"); assert.deepEqual(srv.moves, ["A", "B", "A"]);
});

test("a walk older than the row on the table draws nothing ahead, and the press still moves from the row on screen", async () => {
  const srv = server(), pg = page(srv);
  await pg.press("start"); await pg.press();
  pg.pile = { ...pg.pile, walk: { on: "A", below: "B", above: null, members: [] } };      // the rail as it stood before the last move
  const out = await pg.press();
  assert.equal(out.item.key, "C"); assert.ok(!pg.drawn.includes("ahead:B", 2), "no row B drawn twice"); assert.deepEqual(srv.moves, ["A", "B", "C"]);
});
