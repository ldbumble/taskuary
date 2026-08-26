/* The Studio, live on the landing page. The same room as website/src/StudioView.jsx - same
   projection, same desks, same figures - drawn on a canvas and driven by a script instead of
   the API: mail arrives on the rail, triage rules on it, and when the ruling is "task" the card
   flies in through the door and an agent walks in behind it, sits, and the screen fills with
   what it is doing. The door is the way into the rest of the site. Nothing here is a 3D engine;
   it is 2:1 isometric with a depth sort, exactly like the app. */
(function () {
  const TW = 40, TH = 22, W = 1200, H = 640, DH = 30, WH = 132;
  const SKINS = [
    { body: "#b8b2a9", collar: "#efe9de", skin: "#f0e2d2", hair: "#3e4a3c" },
    { body: "#6f8a6e", collar: "#e8f1ea", skin: "#eddfcf", hair: "#2c3a31" },
    { body: "#8a6a5c", collar: "#eef1ec", skin: "#eedfcd", hair: "#33403a" },
    { body: "#54707a", collar: "#e6f1ef", skin: "#f2e5d5", hair: "#2e3f3c" },
    { body: "#6a6480", collar: "#f2f4ee", skin: "#f2e5d5", hair: "#4b4636" },
  ];
  const CODE = ["#8fb3c9", "#a7c79a", "#d9d3c6", "#7f8a96"];
  const COLS = 2, ROWS = 2, N = COLS * ROWS;
  const GX = Math.max(7, 0.9 + COLS * 2.7 + 0.9), GY = Math.max(6.4, 2.4 + ROWS * 2.9 + 0.7);
  const DOOR = GX - 2.0, AISLE = GX - 0.55, CORR = 0.8, SPEED = 1.7;        // tiles, tiles per second
  const deskAt = (i) => ({ gx: 0.9 + (i % COLS) * 2.7, gy: 2.4 + Math.floor(i / COLS) * 2.9 });
  const seatOf = (i) => { const d = deskAt(i); return [d.gx + 1.0, d.gy - 0.55]; };
  // door -> along the corridor under the windows -> down the free aisle -> across to the seat
  const pathTo = (i) => {
    const [sx, sy] = seatOf(i), door = [DOOR + 0.55, 0.35];
    return Math.floor(i / COLS) === 0 ? [door, [sx, CORR], [sx, sy]] : [door, [AISLE, CORR], [AISLE, sy], [sx, sy]];
  };
  const lenOf = (path) => path.slice(1).reduce((a, p, k) => a + Math.hypot(p[0] - path[k][0], p[1] - path[k][1]), 0);
  const along = (path, dist) => {
    for (let k = 1; k < path.length; k++) {
      const a = path[k - 1], b = path[k], seg = Math.hypot(b[0] - a[0], b[1] - a[1]);
      if (dist <= seg) { const f = seg ? dist / seg : 1; return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f]; }
      dist -= seg;
    }
    return path[path.length - 1];
  };
  const inPoly = (pt, poly) => {                 // even-odd, for the door hit test
    let hit = false;
    for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      const a = poly[i], b = poly[j];
      if ((a[1] > pt[1]) !== (b[1] > pt[1]) && pt[0] < (b[0] - a[0]) * (pt[1] - a[1]) / (b[1] - a[1]) + a[0]) hit = !hit;
    }
    return hit;
  };

  /* ── the story. One loop; the rail and the room read the same events. ─────────────────
     t is seconds into the loop. 'mail' puts a card on the rail, 'verdict' stamps it (and a
     'task' flies to the door), 'walk' sends an agent to a desk, 'done' sends it home,
     'approve' is you pressing Send. */
  const STORY = [
    { t: 0.6, k: "mail", id: "pr", ch: "github", from: "priya-dev · pull request", subj: "acme/ledger#212 Fix rounding in the AR aging report" },
    { t: 2.3, k: "verdict", id: "pr", v: "task", why: "a pull request on your repo is work by construction" },
    { t: 3.1, k: "walk", desk: 0, skin: 1, ref: "TQ-0044", who: "claude",
      tail: ["→ Read: aging.py", "→ Edit: rounding.py", "→ Bash: pytest -q", "14 passed, 0 failed"], files: 3 },
    { t: 5.2, k: "mail", id: "vpn", ch: "teams", from: "Sam Okafor · IT Helpdesk", subj: "Anyone able to reset my VPN token? Locked out again." },
    { t: 7.0, k: "verdict", id: "vpn", v: "fyi", why: "Lee already answered on this thread" },
    { t: 8.8, k: "mail", id: "var", ch: "email", from: "Dana Whitfield · Controller", subj: "Month-end variance — why is the accrual off by 2%?" },
    { t: 10.5, k: "verdict", id: "var", v: "reply", why: "a question — the answer is drafted for you" },
    { t: 12.2, k: "mail", id: "rep", ch: "report", from: "Nightly Ledger Check · scheduled", subj: "3 rows — balance mismatch" },
    { t: 13.6, k: "verdict", id: "rep", v: "task", why: "a failed check is work: an agent takes it" },
    { t: 14.4, k: "walk", desk: 1, skin: 3, ref: "TQ-0034", who: "codex",
      tail: ["→ Read: ledger_check.sql", "→ Bash: pytest -q", "3 rows off: Balance", "→ Edit: reconcile.py"], files: 2 },
    { t: 14.8, k: "approve", id: "var" },
    { t: 17.4, k: "mail", id: "ts", ch: "email", from: "Jordan Park · Payroll", subj: "Timesheet import fails on EmployeeId" },
    { t: 19.1, k: "verdict", id: "ts", v: "task", why: "a bug report: coding work" },
    { t: 19.9, k: "walk", desk: 2, skin: 2, ref: "TQ-0038", who: "gemini",
      tail: ["→ Read: payroll/import.py", "KeyError: EmployeeId", "→ Edit: import.py", "→ Bash: pytest tests/"], files: 1 },
    { t: 22.5, k: "mail", id: "ops", ch: "slack", from: "#ops · Priya", subj: "Staging deploy failed — I am on it" },
    { t: 24.0, k: "verdict", id: "ops", v: "fyi", why: "a colleague is already on it" },
    { t: 26.5, k: "done", desk: 0, note: "opened PR #212 ✓" },
    { t: 28.5, k: "mail", id: "ven", ch: "report", from: "New Vendors · scheduled", subj: "12 rows — new vendors this week" },
    { t: 30.0, k: "verdict", id: "ven", v: "task", why: "the report asked for a follow-up when rows arrive" },
    { t: 30.8, k: "walk", desk: 0, skin: 4, ref: "TQ-0051", who: "claude",
      tail: ["→ Read: vendors.csv", "12 new, 2 duplicates", "→ Edit: vendor_dedupe.py", "→ Bash: pytest -q"], files: 2 },
    { t: 33.5, k: "done", desk: 1, note: "3 rows reconciled ✓" },
    { t: 37.0, k: "done", desk: 2, note: "import fixed, 9 passed ✓" },
    { t: 41.0, k: "done", desk: 0, note: "dedupe shipped ✓" },
  ];
  const LOOP = 46;

  function mount(canvas, opts) {
    opts = opts || {};
    const ctx = canvas.getContext("2d");
    const onEvent = opts.onEvent || (() => {}), onDoor = opts.onDoor || (() => {});
    const still = opts.still || (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    const agents = Array(N).fill(null);        // per desk: {skin, ref, who, tail, files, t0, path, leaveAt, note}
    let fired = new Set(), t0 = performance.now(), last = -1, raf = 0;
    // the mouse turns the room a little, and the door knows when it is being looked at
    const mouse = { x: 0.5, y: 0.5, yaw: 0, lift: 0, overDoor: false, glow: 0 };
    let doorQuad = null, doorTop = null, fit = null, roomBox = null;
    const toCss = (p) => [p[0] * fit.s + fit.ox, p[1] * fit.s + fit.oy];

    const state = (agent, t) => {                // where an agent is in its life at time t
      if (!agent) return null;
      const walk = lenOf(agent.path) / SPEED, age = t - agent.t0;
      if (age < 0) return null;
      if (age < walk) return { mode: "walk", pos: along(agent.path, age * SPEED), ph: age * 8 };
      if (agent.leaveAt != null && t >= agent.leaveAt) {
        const back = t - agent.leaveAt;
        if (back * SPEED >= lenOf(agent.path)) return { gone: true };
        return { mode: "walk", pos: along(agent.path.slice().reverse(), back * SPEED), ph: back * 8 };
      }
      const seated = age - walk;
      return { mode: seated < 0.6 ? "sit" : "type", pos: seatOf(agent.desk), ph: Math.floor(seated * 6), seated };
    };
    const apply = (ev, t) => {
      if (ev.k === "walk") agents[ev.desk] = { ...ev, t0: t, path: pathTo(ev.desk), leaveAt: null };
      if (ev.k === "done" && agents[ev.desk]) { agents[ev.desk].leaveAt = t + 1.2; agents[ev.desk].note = ev.note; }
      onEvent(ev, t);
    };

    const draw = (t, yaw) => {
      const cw = canvas.clientWidth, ch = canvas.clientHeight, dpr = Math.min(2, window.devicePixelRatio || 1);
      if (canvas.width !== Math.round(cw * dpr) || canvas.height !== Math.round(ch * dpr)) { canvas.width = Math.round(cw * dpr); canvas.height = Math.round(ch * dpr); }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, cw, ch);
      // the room is the page: as big as the viewport allows, sitting a little right of centre so
      // the words have the top-left, and lifted a touch with the mouse
      // Sized by the ROOM, not the logical box: the diamond is (GX+GY)*TW wide and about 500
      // tall with its walls, and it sits centred on the screen - the one thing this page is
      // about. Wide screens keep a column free on each side (the feed lives in the right one,
      // beside the door); phones give the room the full width.
      const wide = cw > 820, DIA_W = (GX + GY) * TW, DIA_H = (GX + GY) * TH + WH + 18;
      const feedW = wide ? Math.min(320, Math.max(240, cw * 0.2)) : 0;
      // wide: the feed column, its 28px edge offset and a clear 56px gap are kept free on BOTH sides, so the room stays centred
      const s = wide ? Math.min((cw - 2 * (feedW + 28 + 56)) / DIA_W, ch * 0.86 / DIA_H) : Math.min(cw * 0.98 / DIA_W, ch * 0.92 / DIA_H);
      const ox0 = cw / 2 - W * s / 2, oy0 = ch / 2 - (H / 2 - 24) * s + (wide ? ch * 0.03 : 0) - mouse.lift;
      fit = { s, ox: ox0, oy: oy0 };
      ctx.setTransform(dpr * s, 0, 0, dpr * s, dpr * ox0, dpr * oy0);

      const mx = GX / 2, my = GY / 2, ca = Math.cos(yaw), sa = Math.sin(yaw);
      const map = (x, y) => [mx + (x - mx) * ca - (y - my) * sa, my + (x - mx) * sa + (y - my) * ca];
      const raw = (x, y, z) => { const [u, v] = map(x, y); return [(u - v) * TW, (u + v) * TH - z]; };
      const mid = raw(mx, my, 0), ox = W / 2 - mid[0], oy = H / 2 - mid[1] - 24;
      const P = (x, y, z) => { const p = raw(x, y, z); return [p[0] + ox, p[1] + oy]; };
      const dep = (x, y) => { const [u, v] = map(x, y); return u + v; };
      const SH_A = ca - sa, SH_B = (ca + sa) * (TH / TW);

      const prims = [];
      const poly = (z, pts, fill, o) => prims.push({ k: "p", z, pts, fill, o });
      const rect = (z, x, y, w, h, r, fill) => prims.push({ k: "r", z, x, y, w, h, r, fill });
      const oval = (z, cx, cy, rx, ry, fill) => prims.push({ k: "e", z, cx, cy, rx, ry, fill });
      const glass = (z, at, x, y, size, fill, text, weight) => { if (SH_A < 0.34) return; const o = P(0, at, 0); prims.push({ k: "t", z, m: [SH_A, SH_B, 0, 1, o[0], o[1]], x, y, s: size, fill, text, weight }); };
      const label = (z, x, y, lines) => prims.push({ k: "l", z, x, y, lines });
      const BGZ = -1e4;

      const c = [P(0, 0, 0), P(GX, 0, 0), P(GX, GY, 0), P(0, GY, 0)], dn = (p) => [p[0], p[1] + 18];
      // a soft shadow under the slab, so the room floats on the paper rather than being printed on it
      oval(BGZ - 1, (c[1][0] + c[3][0]) / 2, c[2][1] + 30, (c[1][0] - c[3][0]) * 0.56, 40, "rgba(38,37,33,.09)");
      poly(BGZ, [c[3], c[2], dn(c[2]), dn(c[3])], "#a8977a");
      poly(BGZ, [c[2], c[1], dn(c[1]), dn(c[2])], "#8e7f66");
      poly(BGZ, [c[0], c[1], c[2], c[3]], "#e6ded1");
      poly(BGZ, [P(0, 0, 0), P(GX, 0, 0), P(GX, 0, WH), P(0, 0, WH)], "#f2eee7");
      poly(BGZ, [P(0, 0, 0), P(0, GY, 0), P(0, GY, WH), P(0, 0, WH)], "#e2dbcf");
      poly(BGZ, [P(0, 0, 88), P(GX, 0, 88), P(GX, 0, 91), P(0, 0, 91)], "#cec4b1");
      for (let wx = 0.5; wx + 1.15 < DOOR - 0.1; wx += 1.32) {
        poly(BGZ, [P(wx - 0.07, 0, 26), P(wx + 1.22, 0, 26), P(wx + 1.22, 0, 90), P(wx - 0.07, 0, 90)], "#fffdfb");
        poly(BGZ, [P(wx, 0, 31), P(wx + 1.15, 0, 31), P(wx + 1.15, 0, 85), P(wx, 0, 85)], "#d5e5ed");
        poly(BGZ, [P(wx, 0, 57), P(wx + 1.15, 0, 57), P(wx + 1.15, 0, 59.5), P(wx, 0, 59.5)], "#fffdfb");
        // daylight on the floor under each window
        poly(BGZ + 0.5, [P(wx, 0.05, 0), P(wx + 1.15, 0.05, 0), P(wx + 1.55, 1.7, 0), P(wx + 0.4, 1.7, 0)], "rgba(255,253,251,.35)");
      }
      const wbA = 0.9, wbB = Math.min(wbA + 3.4, GY - 0.9);
      poly(BGZ, [P(0, wbA, 34), P(0, wbB, 34), P(0, wbB, 110), P(0, wbA, 110)], "#b8ae9a");
      poly(BGZ, [P(0, wbA + 0.11, 39), P(0, wbB - 0.11, 39), P(0, wbB - 0.11, 105), P(0, wbA + 0.11, 105)], "#fffdfb");
      [[0.95, 94], [1.35, 84], [0.65, 74], [1.1, 64]].forEach(([len, z]) => {
        const y0 = wbA + 0.34, y1 = Math.min(y0 + len, wbB - 0.3);
        poly(BGZ, [P(0, y0, z), P(0, y1, z), P(0, y1, z + 2.4), P(0, y0, z + 2.4)], "#5c7a90");
      });
      poly(BGZ, [P(0, wbB - 1.15, 46), P(0, wbB - 0.4, 46), P(0, wbB - 0.4, 60), P(0, wbB - 1.15, 60)], "#cfe0cf");

      const box = (x, y, w, d, h, top, left, right, zb) => {
        const z = dep(x + w / 2, y + d / 2) + (zb || 0);
        poly(z, [P(x, y + d, h), P(x + w, y + d, h), P(x + w, y + d, 0), P(x, y + d, 0)], left);
        poly(z, [P(x + w, y, h), P(x + w, y + d, h), P(x + w, y + d, 0), P(x + w, y, 0)], right);
        poly(z, [P(x, y, h), P(x + w, y, h), P(x + w, y + d, h), P(x, y + d, h)], top);
        return z;
      };
      const plx = 0.6, ply = GY - 0.6, plz = dep(plx, ply) + 0.2, pl = P(plx, ply, 0);
      oval(plz, pl[0], pl[1], 19, 7, "rgba(38,37,33,.13)");
      poly(plz + 0.01, [[pl[0] - 12, pl[1] - 24], [pl[0] + 12, pl[1] - 24], [pl[0] + 8, pl[1] - 1], [pl[0] - 8, pl[1] - 1]], "#c39274");
      poly(plz + 0.02, [[pl[0] - 2, pl[1] - 24], [pl[0] - 20, pl[1] - 56], [pl[0] - 7, pl[1] - 64], [pl[0] - 1, pl[1] - 38]], "#6f8a6e");
      poly(plz + 0.02, [[pl[0] + 2, pl[1] - 24], [pl[0] + 20, pl[1] - 60], [pl[0] + 6, pl[1] - 68], [pl[0] + 1, pl[1] - 38]], "#7d9a7c");
      poly(plz + 0.03, [[pl[0], pl[1] - 24], [pl[0] - 5, pl[1] - 62], [pl[0] + 4, pl[1] - 74], [pl[0] + 3, pl[1] - 38]], "#628060");

      // ── the door. Work walks in through it, and it is the way into the site: an EXIT plaque
      //    that lights when you look at it, a leaf that swings while somebody is on the threshold.
      const dx = DOOR, onStep = agents.some((a) => { const st = state(a, t); return st && st.mode === "walk" && st.pos[1] < 1.0; });
      const open = onStep || mouse.glow > 0.5;
      poly(BGZ, [P(dx, 0, 0), P(dx + 1.1, 0, 0), P(dx + 1.1, 0, 104), P(dx, 0, 104)], "#bfae8f");
      poly(BGZ, [P(dx + 0.11, 0, 0), P(dx + 0.99, 0, 0), P(dx + 0.99, 0, 97), P(dx + 0.11, 0, 97)], open ? "#d9d1c3" : "#fffdfb");
      if (open) poly(dep(dx + 0.2, 0.3), [P(dx + 0.11, 0, 0), P(dx + 0.11, 0.62, 0), P(dx + 0.11, 0.62, 97), P(dx + 0.11, 0, 97)], "#f4efe6");
      poly(BGZ, [P(dx + 0.11, 0, 0), P(dx + 0.99, 0, 0), P(dx + 1.3, 1.6, 0), P(dx - 0.2, 1.6, 0)], "#efe9de");
      const g = mouse.glow;
      poly(BGZ, [P(dx + 0.06, 0, 108), P(dx + 1.04, 0, 108), P(dx + 1.04, 0, 124), P(dx + 0.06, 0, 124)], g > 0.02 ? `rgba(${Math.round(85 + 80 * g)},${Math.round(105 + 60 * g)},${Math.round(122 + 30 * g)},1)` : "#55697a");
      glass(BGZ + 1, 0, (dx + 0.17) * TW, -112.5, 7.5, g > 0.5 ? "#ffffff" : "#e6ecef", "EXIT  →", "700");
      // remembered in CSS pixels for the hit test and for whoever wants to fly something at it
      doorQuad = [P(dx, 0, 0), P(dx + 1.1, 0, 0), P(dx + 1.1, 0, 124), P(dx, 0, 124)].map(toCss);
      doorTop = toCss(P(dx + 0.55, 0, 60));
      roomBox = [toCss(P(0, GY, 0))[0], toCss(P(0, 0, WH))[1], toCss(P(GX, 0, 0))[0], toCss(P(GX, GY, 0))[1] + 18 * fit.s];   // left, top, right, bottom (CSS px)

      const person = (x, y, s, mode, ph) => {
        const p = P(x, y, 0), z = dep(x, y) + (mode === "sit" ? -0.05 : 0.05);
        const bob = mode === "type" ? (ph % 2 ? 1 : 0) : 0, step = mode === "walk" ? Math.sin(ph * 0.9) * 4 : 0;
        const cx = p[0], base = p[1] - (mode === "sit" || mode === "type" ? 9 : 0), cy = base - bob;
        oval(z, cx, p[1], 13, 5, "rgba(40,60,46,.16)");
        if (mode !== "walk") { rect(z - 0.03, cx - 14, cy - 33, 28, 9, 4, "#7c8794"); rect(z - 0.02, cx - 15, cy - 13, 30, 8, 3.5, "#8e97a1"); }
        if (mode === "walk") { rect(z, cx - 7 + step * 0.5, cy - 9, 6, 12, 3, "#4a4741"); rect(z, cx + 1 - step * 0.5, cy - 9, 6, 12, 3, "#4a4741"); }
        rect(z + 0.01, cx - 11, cy - 32, 22, 26, 8, s.body);
        poly(z + 0.02, [[cx - 5, cy - 32], [cx + 5, cy - 32], [cx, cy - 23]], s.collar);
        const arm = mode === "type" ? cy - 20 + (ph % 2 ? 0 : 1.5) : cy - 24;
        rect(z + 0.03, cx - 15, arm, 6, 13, 3, s.body);
        rect(z + 0.03, cx + 9, arm, 6, 13, 3, s.body);
        rect(z + 0.04, cx - 10, cy - 51, 20, 20, 7.5, s.skin);
        rect(z + 0.05, cx - 11, cy - 53, 22, 10, 5, s.hair);
        rect(z + 0.06, cx - 11, cy - 49, 4.5, 11, 2.2, s.hair); rect(z + 0.06, cx + 6.5, cy - 49, 4.5, 11, 2.2, s.hair);
        oval(z + 0.07, cx - 3.6, cy - 39, 1.5, 2, "#2a2b2e"); oval(z + 0.07, cx + 3.6, cy - 39, 1.5, 2, "#2a2b2e");
      };

      for (let i = 0; i < N; i++) {
        const { gx, gy } = deskAt(i), a = agents[i], st = state(a, t);
        const here = st && !st.gone && st.mode !== "walk";
        const z = box(gx, gy, 2.0, 1.1, DH, "#d3c4a6", "#a8977a", "#bfae8f");
        const mxx = gx + 0.45, mw = 1.15, myy = gy + 0.3;
        box(mxx + 0.28, myy + 0.06, 0.3, 0.24, DH + 7, "#d3c4a6", "#a8977a", "#bfae8f", 0.01);
        poly(z + 0.02, [P(mxx - 0.05, myy, DH + 6), P(mxx + mw + 0.05, myy, DH + 6), P(mxx + mw + 0.05, myy, DH + 46), P(mxx - 0.05, myy, DH + 46)], "#333b45");
        poly(z + 0.03, [P(mxx, myy, DH + 9), P(mxx + mw, myy, DH + 9), P(mxx + mw, myy, DH + 43), P(mxx, myy, DH + 43)], here ? "#1b212a" : "#cfc7b4");
        if (here) {                                     // a lit screen throws light on the desk
          poly(z + 0.035, [P(mxx - 0.1, myy + 0.05, DH), P(mxx + mw + 0.1, myy + 0.05, DH), P(mxx + mw + 0.3, myy + 0.9, DH), P(mxx - 0.3, myy + 0.9, DH)], "rgba(143,179,201,.10)");
        }
        if (here && st.mode === "type") {
          const leaving = a.leaveAt != null && t >= a.leaveAt - 1.2;
          const n = Math.min(a.tail.length, 1 + Math.floor(st.seated / 1.1));   // lines appear one by one
          // the glass is mw*TW wide and the type is ~2.9px a character - the same arithmetic the
          // app uses, so a line never runs off the edge of the screen it is drawn on
          const fitN = Math.floor((mw * TW - 6) / 2.9);
          const rows = (leaving ? [a.note] : a.tail.slice(0, n)).map((l) => l.length > fitN ? l.slice(0, fitN - 1) + "…" : l);
          rows.forEach((line, k) => glass(z + 0.04, myy, (mxx + 0.06) * TW, -(DH + 38 - k * 7.4), 4.8, leaving ? "#a7c79a" : CODE[k % CODE.length], line));
          if (!leaving && st.seated > 2.4) glass(z + 0.04, myy, (mxx + 0.06) * TW, -(DH + 12), 4.4, "#7f8a96", "✎ " + a.files + " file" + (a.files === 1 ? "" : "s"));
          if (!leaving && Math.floor(st.seated * 2) % 2 === 0 && rows[rows.length - 1].length < fitN) glass(z + 0.04, myy, (mxx + 0.06) * TW + 2.9 * rows[rows.length - 1].length, -(DH + 38 - (rows.length - 1) * 7.4), 4.8, "#e6ecef", "▍");
        }
        box(gx + 0.35, gy + 0.7, 0.9, 0.28, DH + 2, "#cfc7b4", "#aea595", "#bdb3a0", 0.02);
        const lab = P(gx + 1.0, gy + 0.55, DH + 66);
        if (here) label(1e4, lab[0], lab[1], [[a.ref, "#262521", "700"], [a.who + " · " + (st.seated < 90 ? Math.round(st.seated) + "s" : Math.round(st.seated / 60) + "m"), "#55697a", "600"]]);
        else if (!st || st.gone) label(1e4, lab[0], lab[1], [["free desk", "#6e685f", "600"]]);
      }
      agents.forEach((a) => { const st = state(a, t); if (st && !st.gone) person(st.pos[0], st.pos[1], SKINS[a.skin], st.mode, st.ph); });

      prims.sort((p, q) => p.z - q.z);
      for (const p of prims) {
        ctx.globalAlpha = p.o == null ? 1 : p.o;
        if (p.k === "p") { ctx.beginPath(); p.pts.forEach((q, i) => i ? ctx.lineTo(q[0], q[1]) : ctx.moveTo(q[0], q[1])); ctx.closePath(); ctx.fillStyle = p.fill; ctx.fill(); }
        else if (p.k === "r") { ctx.beginPath(); ctx.roundRect(p.x, p.y, p.w, p.h, p.r); ctx.fillStyle = p.fill; ctx.fill(); }
        else if (p.k === "e") { ctx.beginPath(); ctx.ellipse(p.cx, p.cy, p.rx, p.ry, 0, 0, Math.PI * 2); ctx.fillStyle = p.fill; ctx.fill(); }
        else if (p.k === "t") {
          ctx.save(); ctx.transform(p.m[0], p.m[1], p.m[2], p.m[3], p.m[4], p.m[5]);
          ctx.font = (p.weight || "400") + " " + p.s + "px 'IBM Plex Mono', Consolas, monospace"; ctx.fillStyle = p.fill; ctx.textBaseline = "alphabetic"; ctx.fillText(p.text, p.x, p.y); ctx.restore();
        } else if (p.k === "l") {
          ctx.textAlign = "center"; ctx.textBaseline = "alphabetic";
          ctx.shadowColor = "rgba(255,253,251,.95)"; ctx.shadowBlur = 5;
          let y = p.y - (p.lines.length - 1) * 13;
          p.lines.forEach(([text, fill, weight], k) => {
            ctx.font = weight + " " + (k ? 11 : 12) + "px " + (k ? "'IBM Plex Sans', system-ui, sans-serif" : "'IBM Plex Mono', Consolas, monospace");
            ctx.fillStyle = fill; ctx.fillText(text, p.x, y); y += 13;
          });
          ctx.shadowBlur = 0; ctx.textAlign = "start";
        }
      }
      ctx.globalAlpha = 1;
    };

    const frame = () => {
      const t = ((performance.now() - t0) / 1000) % LOOP;
      if (t < last) { fired = new Set(); agents.fill(null); onEvent({ k: "reset" }, t); }
      last = t;
      STORY.forEach((ev, i) => { if (!fired.has(i) && ev.t <= t) { fired.add(i); apply(ev, t); } });
      // ease toward where the mouse wants the room, and toward the door's glow
      // the room follows the mouse - except while you are looking at the door, which holds still
      // so it can be clicked (a target that drifts away as you approach it is a joke, not a door)
      if (!mouse.overDoor) { mouse.yaw += ((mouse.x - 0.5) * 0.22 - mouse.yaw) * 0.05; mouse.lift += ((mouse.y - 0.5) * 18 - mouse.lift) * 0.05; }
      mouse.glow += ((mouse.overDoor ? 1 : 0) - mouse.glow) * 0.12;
      draw(t, 0.05 * Math.sin(t * 0.14) - 0.02 + mouse.yaw);
      raf = requestAnimationFrame(frame);
    };

    canvas.addEventListener("pointermove", (e) => {
      const r = canvas.getBoundingClientRect();
      mouse.x = (e.clientX - r.left) / r.width; mouse.y = (e.clientY - r.top) / r.height;
      mouse.overDoor = !!doorQuad && inPoly([e.clientX - r.left, e.clientY - r.top], doorQuad);
      canvas.style.cursor = mouse.overDoor ? "pointer" : "default";
    });
    canvas.addEventListener("pointerleave", () => { mouse.x = 0.5; mouse.y = 0.5; mouse.overDoor = false; canvas.style.cursor = "default"; });
    canvas.addEventListener("click", (e) => {
      const r = canvas.getBoundingClientRect();
      if (doorQuad && inPoly([e.clientX - r.left, e.clientY - r.top], doorQuad)) onDoor();
    });

    if (still) {                                  // one composed frame: three agents seated, no motion
      STORY.filter((e) => e.k === "walk" && e.t < 20).forEach((e) => apply({ ...e }, -100));
      draw(0, -0.02);
      return { stop() {}, door: () => doorTop, room: () => roomBox };
    }
    raf = requestAnimationFrame(frame);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) { cancelAnimationFrame(raf); last = -1; raf = requestAnimationFrame(frame); } });
    return { stop() { cancelAnimationFrame(raf); }, door: () => doorTop, room: () => roomBox };
  }

  window.TaskuaryFloor = { mount, STORY, LOOP };
})();
