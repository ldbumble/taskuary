// REACHING CLEAR IS A MOMENT (the owner, 2026-11-06): the walk empties the rail, a short confetti burst plays in it, and "All done" lands just
// after. Only on the way there - rows on the rail, then none - never on a reload or a render of a rail that was already clear. Pure, so node
// --test reads it.
export const BURST_MS = 1500, LINE_AFTER_MS = 350;
// `before`: how many rows the rail drew the last time it was looked at (null before it ever drew any); `now`: how many it draws now
export const burstsNow = (before, now) => Number.isFinite(before) && before > 0 && now === 0;
// the pieces, from a seed so a test reads the same burst: each starts at the rail's top middle and flies out and falls
const COLORS = ["#3c5740", "#78a17b", "#c7a258", "#55697a", "#b4654a", "#e4c66a"];
export const piecesOf = (n = 60, seed = 7) => {
  let s = seed;
  const r = () => ((s = (s * 16807) % 2147483647) / 2147483647);
  return Array.from({ length: n }, () => ({ a: -Math.PI / 2 + (r() - 0.5) * 2.2, v: 0.35 + r() * 0.45, spin: (r() - 0.5) * 0.02, w: 4 + r() * 4, h: 6 + r() * 6,
    c: COLORS[Math.floor(r() * COLORS.length)] }));
};
// where a piece is `t` ms in, in px from the start point: out along its angle, gravity pulling it down
export const pieceAt = (p, t) => ({ x: Math.cos(p.a) * p.v * t, y: Math.sin(p.a) * p.v * t + 0.0006 * t * t, rot: p.spin * t, fade: Math.max(0, 1 - t / BURST_MS) });
