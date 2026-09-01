// The Board, drawn as a floor instead of four columns. A desk IS a task, the figure at it is
// the agent working it, and an empty desk is spare capacity - so "how much can run at once"
// stops being a number in Settings and becomes something you can see. Nothing here is a new
// source of truth: desks come from /api/agents, occupancy from the same /api/tasks the columns
// read.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, CircularProgress, Slider, Typography } from "@mui/material";
import api from "./api";
import { pollWhileVisible } from "./visible.js";
import { onLive } from "./live.js";
import { PANEL, BORDER, DIM, FAINT, INK, ACCENT, ACCENT2, ROLES, mono } from "./theme.jsx";
import { cliName, FileChips } from "./BoardView.jsx";
import { WorkLine, isWaiting } from "./ui.jsx";

// Logical drawing space; the SVG scales it, so every number below is layout, not pixels.
const W = 1200, H = 640, TW = 40, TH = 22;

const SKINS = [
  { body: "#b8b2a9", collar: "#efe9de", skin: "#f0e2d2", hair: "#3e4a3c" },
  { body: "#6f8a6e", collar: "#e8f1ea", skin: "#eddfcf", hair: "#2c3a31" },
  { body: "#8a6a5c", collar: "#eef1ec", skin: "#eedfcd", hair: "#33403a" },
  { body: "#54707a", collar: "#e6f1ef", skin: "#f2e5d5", hair: "#2e3f3c" },
  { body: "#6a6480", collar: "#f2f4ee", skin: "#f2e5d5", hair: "#4b4636" },
];

const isLive = (t) => !!(t && (t.Session || t.RunStatus === "running"));
// how long this session has been going. "claude is typing" told you nothing you could act on;
// "claude · 14m" is the Board's own answer, and the two views should not disagree.
const since = (t, l) => {
  const at = l?.StartedAt || t?.Session?.started || t?.RunStartedAt;
  if (!at) return "";
  const sec = Math.max(0, (Date.now() - new Date(String(at).replace(" ", "T"))) / 1000);
  return sec < 90 ? `${Math.round(sec)}s` : sec < 5400 ? `${Math.round(sec / 60)}m` : `${(sec / 3600).toFixed(1)}h`;
};
// What the figure at the desk is DOING, which the floor never said before - it only ever
// coloured a dot. Hunched at the keyboard = a coding agent is writing code; pen on a form =
// an agent working a task with no code in it; hand up = it has stopped and is waiting on YOU.
// Colour only repeats what the posture already says, so the room reads small or greyscale.
const poseOf = (t) => {
  if (!t) return "free";
  if (t.Status === "waiting" || t.ReviewStatus === "pending") return "hand";
  if (isLive(t)) return (t.Kind === "coding" ? "type" : "paper");
  return "sit";
};
// A desk's colour comes off the same ROLES table the Timeline and the Board read, so a task
// that is "waiting on you" is the one colour that means that, everywhere in the app.
const stateOf = (t, l) => {
  if (!t) return { label: "free", color: ROLES.muted.solid };
  if (isLive(t)) {
    const who = cliName(l?.AgentName || t.Session?.agent || t.RunAgent || "agent"), ago = since(t, l);
    return { label: ago ? `${who} · ${ago}` : who, color: ROLES.working.solid };
  }
  if (t.Status === "waiting" || t.ReviewStatus === "pending") return { label: "waiting on you", color: ROLES.you.solid };
  return { label: "open", color: ROLES.muted.solid };
};

export default function StudioView({ onOpenTask, refresh = 0 }) {
  const [tasks, setTasks] = useState(null);
  const [agents, setAgents] = useState([]);
  const [cam, setCam] = useState({ yaw: 0, zoom: 1.1, px: 0, py: 0 });
  const camRef = useRef(cam), goal = useRef(cam), raf = useRef(0), drag = useRef(null);
  // One exponential ease per frame toward the goal. No spring, no overshoot: a room that
  // bounces past the desk you asked for is a toy, and this has to stay legible while it moves.
  const tick = useCallback(() => {
    const c = camRef.current, g = goal.current, k = 0.16;
    const n = { yaw: c.yaw + (g.yaw - c.yaw) * k, zoom: c.zoom + (g.zoom - c.zoom) * k,
                px: c.px + (g.px - c.px) * k, py: c.py + (g.py - c.py) * k };
    const near = Math.abs(g.yaw - n.yaw) < 2e-4 && Math.abs(g.zoom - n.zoom) < 2e-4
      && Math.abs(g.px - n.px) < 0.2 && Math.abs(g.py - n.py) < 0.2;
    camRef.current = near ? { ...g } : n;
    setCam(camRef.current);
    raf.current = near ? 0 : requestAnimationFrame(tick);
  }, []);
  const nudge = useCallback((patch) => {
    goal.current = { ...goal.current, ...patch };
    if (!raf.current) raf.current = requestAnimationFrame(tick);
  }, [tick]);
  useEffect(() => () => raf.current && cancelAnimationFrame(raf.current), []);
  const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v);
  const [cap, setCap] = useState(null);   // Settings -> Agents at once; the floor IS this number
  const [live, setLive] = useState({});   // TaskId -> the same {tail, files, StartedAt} the Board reads
  const [pick, setPick] = useState(null);
  const [frame, setFrame] = useState(0);          // the only clock the room has

  const load = useCallback(async () => {
    const [t, a, cfg] = await Promise.all([
      api.get("/api/tasks", { params: { active: 1 } }).catch(() => ({ data: {} })),
      api.get("/api/agents").catch(() => ({ data: {} })),
      api.get("/api/settings").catch(() => ({ data: {} })),
    ]);
    setTasks((t.data.data || []).filter((x) => x.Status !== "dropped"));
    setAgents(a.data.data || a.data.agents || []);
    const row = (cfg.data.data || []).find((x) => x.Name === "auto_sessions");
    setCap((c) => (c == null ? Math.max(1, Math.min(8, parseInt(row?.Value, 10) || 4)) : c));
  }, []);
  useEffect(() => { load(); return onLive("task-changed", load); }, [load]);
  useEffect(() => { if (refresh) load(); }, [refresh, load]); // the Board just started a session: seat it now, not on the next event
  // the tails arrive as run-tail, exactly as the Board's do: a screen you are watching is a status wall
  useEffect(() => {
    const tick = () => api.get("/api/runs/live").then(({ data }) =>
      setLive(Object.fromEntries((data.data || []).map((r) => [r.TaskId, r])))).catch(() => {});
    tick();
    return onLive("run-tail", tick);
  }, []);

  const desks = useMemo(() => {
    const n = Math.max(1, Math.min(8, cap ?? 4));
    const live = (tasks || []).filter(isLive);
    const mine = (tasks || []).filter((t) => !live.includes(t) && (t.Status === "waiting" || t.ReviewStatus === "pending"));
    const seated = [...live, ...mine].slice(0, n);
    return Array.from({ length: n }, (_, i) => seated[i] || null);
  }, [tasks, cap]);

  const queue = useMemo(() => (tasks || []).filter(
    (t) => t.Status === "open" && !isLive(t) && !desks.includes(t)), [tasks, desks]);

  // Only tick when there is something to animate - a still room should not repaint.
  const busy = desks.some(isLive), walking = queue.length > 0 && desks.some((d) => !d);
  useEffect(() => {
    if (!busy && !walking) return undefined;
    return pollWhileVisible(() => setFrame((f) => f + 1), 160);
  }, [busy, walking]);


  const scene = useMemo(() => {
    // The floor is sized to the desks, not the other way round: four agents in an eleven-square
    // room read as an empty warehouse with a diagonal line of furniture in it.
    const cols = desks.length <= 4 ? 2 : desks.length <= 6 ? 3 : 4;
    const rows = Math.ceil(desks.length / cols);
    const GX = Math.max(7, 0.9 + cols * 2.7 + 0.9), GY = Math.max(6.4, 2.4 + rows * 2.9 + 0.7);

    // Yaw the floor about its own centre, then project. The old four-corner remap was this
    // same idea quantised to 90 degrees; nothing here is a 3D engine either.
    const mx = GX / 2, my = GY / 2, ca = Math.cos(cam.yaw), sa = Math.sin(cam.yaw);
    const map = (x, y) => [mx + (x - mx) * ca - (y - my) * sa, my + (x - mx) * sa + (y - my) * ca];
    const raw = (x, y, z) => { const [u, v] = map(x, y); return [(u - v) * TW, (u + v) * TH - z]; };
    // Centre on the floor's MIDDLE, which rotation leaves fixed. Centring on the bounding box
    // instead makes the whole room breathe in and out as it turns.
    const mid = raw(mx, my, 0);
    const ox = W / 2 - mid[0], oy = H / 2 - mid[1] - 24;
    const P = (x, y, z) => { const p = raw(x, y, z); return [p[0] + ox, p[1] + oy]; };
    const pts = (...ps) => ps.map((p) => p.join(",")).join(" ");
    const dep = (x, y) => { const [u, v] = map(x, y); return u + v; };

    const prims = [];
    const poly = (z, p, fill, o) => prims.push({ k: "p", z, pts: p, fill, o: o == null ? 1 : o });
    const rect = (z, x, y, w, h, r, fill) => prims.push({ k: "r", z, x, y, w, h, r, fill });
    const oval = (z, cx, cy, rx, ry, fill, o) => prims.push({ k: "e", z, cx, cy, rx, ry, fill, o: o == null ? 1 : o });
    /* Type on the monitor's own plane. Varying x on the plane y=const moves the screen point
       by ((ca-sa)*TW, (ca+sa)*TH), and z moves it straight up - so that pair IS the shear, and
       at yaw 0 it collapses to the (1, TH/TW) the first cut hard-coded. Past about 70 degrees
       the plane is edge-on: the type would compress to a smear and then mirror, so it stops. */
    const SH_A = ca - sa, SH_B = (ca + sa) * (TH / TW);
    const glass = (z, at, x, y, size, fill, str) => {
      if (SH_A < 0.34) return;                           // turned too far to read: draw nothing
      const o = P(0, at, 0);                             // in-plane origin; x/y below are local px
      prims.push({ k: "t", z, m: `matrix(${SH_A.toFixed(4)},${SH_B.toFixed(4)},0,1,${o[0]},${o[1]})`,
                   x, y, s: size, fill, text: str });
    };
    const BGZ = -1e4;

    const c = [P(0, 0, 0), P(GX, 0, 0), P(GX, GY, 0), P(0, GY, 0)];
    const dn = (p) => [p[0], p[1] + 18];
    poly(BGZ, pts(c[3], c[2], dn(c[2]), dn(c[3])), "#a8977a");
    poly(BGZ, pts(c[2], c[1], dn(c[1]), dn(c[2])), "#8e7f66");
    poly(BGZ, pts(c[0], c[1], c[2], c[3]), "#e6ded1");
    const WH = 132;
    poly(BGZ, pts(P(0, 0, 0), P(GX, 0, 0), P(GX, 0, WH), P(0, 0, WH)), "#f2eee7");
    poly(BGZ, pts(P(0, 0, 0), P(0, GY, 0), P(0, GY, WH), P(0, 0, WH)), "#e2dbcf");
    poly(BGZ, pts(P(0, 0, 88), P(GX, 0, 88), P(GX, 0, 91), P(0, 0, 91)), "#cec4b1");

    /* Windows, a whiteboard and a plant. None of them carries data; that is the point - a room
       with a window in it reads as a place, and this floor is asking to be read as one. The
       windows have the back wall to themselves now, corner to door. */
    const doorAt = GX - 2.0;
    for (let wx = 0.5; wx + 1.15 < doorAt - 0.1; wx += 1.32) {
      poly(BGZ, pts(P(wx - 0.07, 0, 26), P(wx + 1.22, 0, 26), P(wx + 1.22, 0, 90), P(wx - 0.07, 0, 90)), "#fffdfb");
      poly(BGZ, pts(P(wx, 0, 31), P(wx + 1.15, 0, 31), P(wx + 1.15, 0, 85), P(wx, 0, 85)), "#d5e5ed");
      poly(BGZ, pts(P(wx, 0, 57), P(wx + 1.15, 0, 57), P(wx + 1.15, 0, 59.5), P(wx, 0, 59.5)), "#fffdfb");
    }
    // the whiteboard, on the one wall with nothing on it. Fixed size: derived from GY it grew
    // to four tiles wide and its strokes ran the whole length of it.
    // About half the side wall, with strokes measured in tiles rather than as a fraction of the
    // board - a fraction meant the board's own size decided how long they were, so widening it
    // turned three notes into three lines running the length of the room.
    const wbA = 0.9, wbB = Math.min(wbA + 3.4, GY - 0.9);
    poly(BGZ, pts(P(0, wbA, 34), P(0, wbB, 34), P(0, wbB, 110), P(0, wbA, 110)), "#b8ae9a");
    poly(BGZ, pts(P(0, wbA + 0.11, 39), P(0, wbB - 0.11, 39), P(0, wbB - 0.11, 105), P(0, wbA + 0.11, 105)), "#fffdfb");
    [[0.95, 94], [1.35, 84], [0.65, 74], [1.1, 64]].forEach(([len, z]) => {
      const y0 = wbA + 0.34, y1 = Math.min(y0 + len, wbB - 0.3);
      poly(BGZ, pts(P(0, y0, z), P(0, y1, z), P(0, y1, z + 2.4), P(0, y0, z + 2.4)), "#5c7a90");
    });
    poly(BGZ, pts(P(0, wbB - 1.15, 46), P(0, wbB - 0.4, 46), P(0, wbB - 0.4, 60), P(0, wbB - 1.15, 60)), "#cfe0cf");

    const box = (x, y, w, d, h, top, left, right, zbias) => {
      const z = dep(x + w / 2, y + d / 2) + (zbias || 0);
      poly(z, pts(P(x, y + d, h), P(x + w, y + d, h), P(x + w, y + d, 0), P(x, y + d, 0)), left);
      poly(z, pts(P(x + w, y, h), P(x + w, y + d, h), P(x + w, y + d, 0), P(x + w, y, 0)), right);
      poly(z, pts(P(x, y, h), P(x + w, y, h), P(x + w, y + d, h), P(x, y + d, h)), top);
      return z;
    };

    // a plant in the far corner. It is the cheapest thing on this list and does the most.
    const plx = 0.6, ply = GY - 0.6, plz = dep(plx, ply) + 0.2, pl = P(plx, ply, 0);
    oval(plz, pl[0], pl[1], 19, 7, "rgba(38,37,33,.13)");
    poly(plz + 0.01, pts([pl[0] - 12, pl[1] - 24], [pl[0] + 12, pl[1] - 24], [pl[0] + 8, pl[1] - 1], [pl[0] - 8, pl[1] - 1]), "#c39274");
    poly(plz + 0.02, pts([pl[0] - 2, pl[1] - 24], [pl[0] - 20, pl[1] - 56], [pl[0] - 7, pl[1] - 64], [pl[0] - 1, pl[1] - 38]), "#6f8a6e");
    poly(plz + 0.02, pts([pl[0] + 2, pl[1] - 24], [pl[0] + 20, pl[1] - 60], [pl[0] + 6, pl[1] - 68], [pl[0] + 1, pl[1] - 38]), "#7d9a7c");
    poly(plz + 0.03, pts([pl[0], pl[1] - 24], [pl[0] - 5, pl[1] - 62], [pl[0] + 4, pl[1] - 74], [pl[0] + 3, pl[1] - 38]), "#628060");

    // the door work walks in through
    const dx = GX - 2.0;
    poly(BGZ, pts(P(dx, 0, 0), P(dx + 1.1, 0, 0), P(dx + 1.1, 0, 104), P(dx, 0, 104)), "#bfae8f");
    poly(BGZ, pts(P(dx + 0.11, 0, 0), P(dx + 0.99, 0, 0), P(dx + 0.99, 0, 97), P(dx + 0.11, 0, 97)), "#fffdfb");
    poly(BGZ, pts(P(dx + 0.11, 0, 0), P(dx + 0.99, 0, 0), P(dx + 1.3, 1.6, 0), P(dx - 0.2, 1.6, 0)), "#efe9de");

    // ── a person. Arms are separate so they can be put on a keyboard, and legs so they can walk.
    const person = (x, y, s, mode, ph) => {
      const p = P(x, y, 0), z = dep(x, y) + (mode === "sit" ? -0.05 : 0.05);
      const bob = mode === "type" ? (ph % 2 ? 1 : 0) : 0;
      const step = mode === "walk" ? Math.sin(ph * 0.9) * 4 : 0;
      const cx = p[0], base = p[1] - (mode === "sit" || mode === "type" ? 9 : 0), cy = base - bob;
      oval(z, cx, p[1], 13, 5, "rgba(40,60,46,.16)");
      if (mode !== "walk") {                                  // seat under, backrest behind
        rect(z - 0.03, cx - 14, cy - 33, 28, 9, 4, "#7c8794");
        rect(z - 0.02, cx - 15, cy - 13, 30, 8, 3.5, "#8e97a1");
      }
      if (mode === "walk") {                                  // legs only show when standing up
        rect(z, cx - 7 + step * 0.5, cy - 9, 6, 12, 3, "#4a4741");
        rect(z, cx + 1 - step * 0.5, cy - 9, 6, 12, 3, "#4a4741");
      }
      rect(z + 0.01, cx - 11, cy - 32, 22, 26, 8, s.body);     // torso
      poly(z + 0.02, pts([cx - 5, cy - 32], [cx + 5, cy - 32], [cx, cy - 23]), s.collar);
      const arm = mode === "type" ? cy - 20 + (ph % 2 ? 0 : 1.5) : cy - 24;
      rect(z + 0.03, cx - 15, arm, 6, 13, 3, s.body);          // arms
      if (mode === "hand") {                                   // one straight up, palm open
        rect(z + 0.03, cx + 9, cy - 52, 6, 30, 3, s.body);
        rect(z + 0.04, cx + 7.5, cy - 62, 9, 12, 4, s.skin);
      } else {
        rect(z + 0.03, cx + 9, mode === "paper" ? cy - 18 : arm, 6, 13, 3, s.body);
        if (mode === "paper") rect(z + 0.05, cx + 13, cy - 22, 3, 12, 1.5, "#3a3f42");   // pen
      }
      rect(z + 0.04, cx - 10, cy - 51, 20, 20, 7.5, s.skin);   // head
      rect(z + 0.05, cx - 11, cy - 53, 22, 10, 5, s.hair);
      rect(z + 0.06, cx - 11, cy - 49, 4.5, 11, 2.2, s.hair);  // fringe either side
      rect(z + 0.06, cx + 6.5, cy - 49, 4.5, 11, 2.2, s.hair);
      oval(z + 0.07, cx - 3.6, cy - 39, 1.5, 2, "#2a2b2e");
      oval(z + 0.07, cx + 3.6, cy - 39, 1.5, 2, "#2a2b2e");
    };

    // ── a workstation. The monitor stands ON the desk (its foot is the desk's height), which
    // is the bug in the first cut: it floated behind the desk like a poster.
    const CODE = ["#8fb3c9", "#a7c79a", "#d9d3c6", "#7f8a96"];
    const DH = 30;                                            // desk height
    const tags = desks.map((t, i) => {
      const gx = 0.9 + (i % cols) * 2.7, gy = 2.4 + Math.floor(i / cols) * 2.9;
      const l = t ? live[t.TaskId] : null;
      const st = stateOf(t, l), liveNow = isLive(t);
      const z = box(gx, gy, 2.0, 1.1, DH, "#d3c4a6", "#a8977a", "#bfae8f");
      const mx = gx + 0.45, mw = 1.15, my = gy + 0.3;      // wider: it has to carry text now
      box(mx + 0.28, my + 0.06, 0.3, 0.24, DH + 7, "#d3c4a6", "#a8977a", "#bfae8f", 0.01);   // stand
      poly(z + 0.02, pts(P(mx - 0.05, my, DH + 6), P(mx + mw + 0.05, my, DH + 6),
        P(mx + mw + 0.05, my, DH + 46), P(mx - 0.05, my, DH + 46)), "#333b45");
      poly(z + 0.03, pts(P(mx, my, DH + 9), P(mx + mw, my, DH + 9),
        P(mx + mw, my, DH + 43), P(mx, my, DH + 43)), liveNow ? "#1b212a" : "#cfc7b4");
      const pose = poseOf(t);
      if (pose === "paper") {                                 // a form on the desk, not a diff
        box(gx + 0.3, gy + 0.62, 1.0, 0.3, DH + 2, "#fffdfb", "#ded7c8", "#e8e2d5", 0.03);
        for (let k = 0; k < 3; k++) {
          const yy = gy + 0.70 + k * 0.07;
          poly(z + 0.05, pts(P(gx + 0.42, yy, DH + 2.1), P(gx + 1.18, yy, DH + 2.1),
            P(gx + 1.18, yy + 0.02, DH + 2.1), P(gx + 0.42, yy + 0.02, DH + 2.1)), k ? "#a9a294" : "#4d4a43");
        }
      }
      /* The run's OWN last lines, laid on the glass. This used to be three coloured bars whose
         widths came off a frame counter - decoration that looked like data, which is worse than
         no data. At overview zoom it reads as code; fly to the desk and you can read it, which
         is what the camera is for. */
      if (liveNow && pose === "type") {
        const tail = (l?.tail || []).slice(-4);
        const rows = tail.length ? tail : ["waiting for output…"];
        rows.forEach((line, k) => {
          const fit = Math.floor((mw * TW - 5) / 2.9);        // characters that fit the glass
          const clean = String(line).replace(/\s+/g, " ").trim().slice(0, fit);
          glass(z + 0.04, my, (mx + 0.06) * TW, -(DH + 38 - k * 7.4), 4.8,
            CODE[k % CODE.length], clean);
        });
        if (l?.files?.length) {
          glass(z + 0.04, my, (mx + 0.06) * TW, -(DH + 12), 4.4, "#7f8a96",
            `✎ ${l.files.length} file${l.files.length === 1 ? "" : "s"}`);
        }
      }
      box(gx + 0.35, gy + 0.7, 0.9, 0.28, DH + 2, "#cfc7b4", "#aea595", "#bdb3a0", 0.02);    // keyboard
      if (t) person(gx + 1.0, gy - 0.55, SKINS[i % SKINS.length], poseOf(t), frame);
      const lab = P(gx + 1.0, gy + 0.55, DH + 66);
      return { t, st, x: lab[0], y: lab[1] };
    });

    // painter's order: the walls at BGZ first, then everything by depth - without this the figure,
    // pushed last, was drawn OVER the monitor it sits behind
    prims.sort((a, b) => a.z - b.z);
    return { prims, tags };
  }, [cam.yaw, desks, live, queue.length, frame]);

  if (!tasks) return <CircularProgress size={22} sx={{ m: 4 }} />;
  const free = desks.filter((d) => !d).length;
  const seated = desks.filter(Boolean);
  const deskAt = (id) => scene.tags.find((g) => g.t?.TaskId === id);
  const vw = W / cam.zoom, vh = H / cam.zoom;
  const vx = cam.px + (W - vw) / 2, vy = cam.py + (H - vh) / 2;
  // The chips are HTML on top of the SVG, so they must be projected through the same viewBox -
  // otherwise they drift off their desks the moment you zoom.
  const sx = (x) => `${((x - vx) / vw) * 100}%`;
  const sy = (y) => `${((y - vy) / vh) * 100}%`;
  const flyTo = (x, y) => nudge({ zoom: 2.1, px: x - W / 2, py: y - H / 2 });
  const moved = Math.abs(cam.yaw) > 0.01 || Math.abs(cam.zoom - 1.1) > 0.01;

  const onDown = (e) => {
    if (e.button !== 0 && e.button !== 1) return;
    drag.current = { x: e.clientX, y: e.clientY, ...goal.current, pan: e.shiftKey || e.button === 1, far: 0 };
    e.currentTarget.setPointerCapture(e.pointerId);
  };
  const onMove = (e) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    d.far = Math.max(d.far, Math.abs(dx) + Math.abs(dy));
    if (d.pan) nudge({ px: d.px - dx / cam.zoom, py: d.py - dy / cam.zoom });
    else nudge({ yaw: d.yaw + dx * 0.0055, py: clamp(d.py - dy * 0.5, -220, 220) });
  };
  const onUp = () => { drag.current = null; };
  const onWheel = (e) => {
    e.preventDefault();
    nudge({ zoom: clamp(goal.current.zoom * (e.deltaY < 0 ? 1.12 : 1 / 1.12), 0.75, 3.2) });
  };

  return (
    <Box sx={{ position: "relative", width: "100%", height: "calc(100vh - 190px)", minHeight: 520, overflow: "hidden" }}>
      <Box component="svg" viewBox={`${vx} ${vy} ${vw} ${vh}`} preserveAspectRatio="xMidYMid meet"
        onPointerDown={onDown} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}
        onWheel={onWheel} onDoubleClick={() => nudge({ yaw: 0, zoom: 1.1, px: 0, py: 0 })}
        sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", touchAction: "none",
          cursor: drag.current ? "grabbing" : "grab" }}>
        {scene.prims.map((p, i) => (p.k === "p"
          ? <polygon key={i} points={p.pts} fill={p.fill} opacity={p.o} />
          : p.k === "r" ? <rect key={i} x={p.x} y={p.y} width={p.w} height={p.h} rx={p.r} fill={p.fill} />
            : p.k === "t" ? <text key={i} transform={p.m} x={p.x} y={p.y} fontSize={p.s} fill={p.fill}
            fontFamily="'IBM Plex Mono', Consolas, monospace" style={{ whiteSpace: "pre" }}>{p.text}</text>
            : p.k === "e" ? <ellipse key={i} cx={p.cx} cy={p.cy} rx={p.rx} ry={p.ry} fill={p.fill} opacity={p.o} />
              : <path key={i} d={p.d} fill="none" stroke={p.stroke} strokeWidth="1.6" strokeDasharray="1 6"
                strokeLinecap="round" opacity={p.o} />))}
      </Box>

      {scene.tags.map((g, i) => (
        <Box key={i} onClick={() => { if (g.t) { setPick(g.t.TaskId); flyTo(g.x, g.y); } }}
          sx={{ position: "absolute", left: sx(g.x), top: sy(g.y),
            transform: "translate(-50%, -100%)", textAlign: "center", whiteSpace: "nowrap",
            cursor: g.t ? "pointer" : "default", lineHeight: 1.3,
            // no pill: the room shows through, as in the design. A double text-shadow keeps it
            // legible whether it lands on pale wall or on a dark monitor.
            textShadow: "0 0 3px rgba(255,253,251,.95), 0 0 8px rgba(255,253,251,.85)",
            "&:hover .thubRef": g.t ? { textDecoration: "underline" } : {} }}>
          {g.t
            ? <>
              <Box className="thubRef" sx={{ ...mono, fontSize: 12, fontWeight: 700, color: INK,
                textDecoration: pick === g.t.TaskId ? "underline" : "none" }}>{g.t.ref}</Box>
              <Box sx={{ fontSize: 11, fontWeight: 600, color: g.st.color }}>{g.st.label}</Box>
            </>
            : <Box sx={{ fontSize: 11, fontWeight: 600, color: FAINT }}>free desk</Box>}
        </Box>
      ))}

      <Box sx={{ position: "absolute", left: 16, top: 12, width: 286, bgcolor: PANEL, border: `1px solid ${BORDER}`,
        borderRadius: "11px", boxShadow: "0 10px 28px rgba(30,50,38,.11)", overflow: "hidden",
        display: "flex", flexDirection: "column", maxHeight: "calc(100% - 84px)" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.75, pt: 1.4, pb: 1.1, borderBottom: `1px solid ${BORDER}` }}>
          <Typography sx={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.3, color: FAINT, flex: 1 }}>ON THE FLOOR</Typography>
          <Typography sx={{ fontSize: 11, color: FAINT }}>{seated.length}/{desks.length}</Typography>
        </Box>
        <Box sx={{ overflowY: "auto", minHeight: 0 }}>
          {/* one row per occupied desk. Clicking flies the camera to it, and picking a desk in
              the room highlights the row here - the two are the same selection. */}
          {seated.map((t) => {
            const st = stateOf(t, live[t.TaskId]), on = pick === t.TaskId;
            return (
              <Box key={t.TaskId} onClick={() => { setPick(t.TaskId); const d = deskAt(t.TaskId); if (d) flyTo(d.x, d.y); }}
                sx={{ px: 1.75, py: 1.05, borderBottom: `1px solid ${BORDER}`, cursor: "pointer",
                  borderLeft: `3px solid ${on ? st.color : "transparent"}`,
                  bgcolor: on ? "#f4f1ec" : "transparent", "&:hover": { bgcolor: "#f4f1ec" } }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
                  <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: st.color, flexShrink: 0 }} />
                  <Typography sx={{ ...mono, fontSize: 10.5, color: FAINT }}>{t.ref}</Typography>
                  <Typography noWrap sx={{ fontSize: 10.5, color: st.color, fontWeight: 600, flex: 1, minWidth: 0 }}>{st.label}</Typography>
                  {t.Waiting > 0 && <Typography sx={{ ...mono, fontSize: 10, color: "#6b5f45", fontWeight: 700, flexShrink: 0 }}
                    title={`${t.Waiting} queued prompt${t.Waiting === 1 ? "" : "s"} waiting in the funnel`}>✎ {t.Waiting}</Typography>}
                </Box>
                <Typography noWrap sx={{ fontSize: 12.5, fontWeight: 600, color: INK, pt: 0.3 }}>{t.Title}</Typography>
                {/* what the agent holds right now (its hook / rollout), then the same git-attributed
                    file list the Board card shows */}
                {live[t.TaskId]?.work && <Box sx={{ pt: 0.5 }}><WorkLine work={live[t.TaskId].work} who={live[t.TaskId].cli || cliName(live[t.TaskId].AgentName || "agent")}
                  waiting={live[t.TaskId].kind === "session" && isWaiting(live[t.TaskId])} asking={live[t.TaskId].asking} startedAt={live[t.TaskId].StartedAt} /></Box>}
                {live[t.TaskId]?.files?.length > 0 && <Box sx={{ pt: 0.6 }}><FileChips files={live[t.TaskId].files} /></Box>}
                {on && (
                  <Typography onClick={(e) => { e.stopPropagation(); onOpenTask(t.TaskId); }}
                    sx={{ fontSize: 11.5, fontWeight: 600, color: ACCENT, pt: 0.5, "&:hover": { textDecoration: "underline" } }}>
                    Open the task →
                  </Typography>
                )}
              </Box>
            );
          })}
          {!seated.length && (
            <Typography sx={{ px: 1.75, py: 1.4, fontSize: 12, color: FAINT }}>
              Every desk is free — nothing is being worked right now.
            </Typography>
          )}
          {queue.length > 0 && (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.75, pt: 1.2, pb: 0.9,
              bgcolor: "#f4f1ec", borderBottom: `1px solid ${BORDER}` }}>
              <Typography sx={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.3, color: FAINT, flex: 1 }}>WAITING FOR A DESK</Typography>
              <Typography sx={{ fontSize: 11, color: FAINT }}>{queue.length}</Typography>
            </Box>
          )}
          {queue.slice(0, 6).map((t) => (
            <Box key={t.TaskId} onClick={() => onOpenTask(t.TaskId)}
              sx={{ px: 1.75, py: 0.9, borderBottom: `1px solid ${BORDER}`, cursor: "pointer", "&:hover": { bgcolor: "#f4f1ec" } }}>
              <Typography sx={{ ...mono, fontSize: 10.5, color: FAINT }}>
                {t.ref}{t.Waiting > 0 ? <Box component="span" sx={{ color: "#6b5f45", fontWeight: 700, ml: 0.75 }}>✎ {t.Waiting}</Box> : null}
              </Typography>
              <Typography noWrap sx={{ fontSize: 12.5, color: DIM, pt: 0.2 }}>{t.Title}</Typography>
            </Box>
          ))}
          {queue.length > 6 && (
            <Typography sx={{ px: 1.75, py: 0.9, fontSize: 11, color: FAINT }}>+{queue.length - 6} more waiting — the Columns view lists them all</Typography>
          )}
        </Box>
        {/* the desk count IS the Agents-at-once setting, so this writes it. Move the slider and
            the room widens; open Settings and you find the same number. */}
        <Box sx={{ px: 1.75, pt: 1.1, pb: 1.3, borderTop: `1px solid ${BORDER}`, flexShrink: 0 }}>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.75 }}>
            <Typography sx={{ fontSize: 11, color: DIM, flex: 1 }}>Agents at once</Typography>
            <Typography sx={{ ...mono, fontSize: 12.5, fontWeight: 700, color: INK }}>{cap ?? "—"}</Typography>
            <Typography sx={{ fontSize: 11, color: FAINT }}>{free} free</Typography>
          </Box>
          <Slider size="small" min={1} max={8} step={1} marks value={cap ?? 4}
            onChange={(_, v) => setCap(v)}
            onChangeCommitted={(_, v) => api.patch("/api/settings", { name: "auto_sessions", value: String(v) }).catch(() => {})}
            sx={{ mt: 0.25, color: ACCENT, "& .MuiSlider-markActive": { bgcolor: PANEL } }} />
        </Box>
      </Box>

      <Box sx={{ position: "absolute", left: 16, bottom: 14, display: "flex", alignItems: "center", gap: 1.1,
        bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: "11px", px: 1.4, py: 1,
        boxShadow: "0 10px 28px rgba(30,50,38,.11)" }}>
        {/* One line that teaches the gesture, and a way back. The four corner buttons said which
            side you stood on; they could not answer "what is on THAT desk", which is the question
            you actually arrive with. */}
        <Typography sx={{ fontSize: 11, color: FAINT }}>
          {moved ? "double-click to reset" : "drag to turn · scroll to zoom · shift-drag to pan · click a desk"}
        </Typography>
        {moved && (
          <Box onClick={() => nudge({ yaw: 0, zoom: 1.1, px: 0, py: 0 })}
            sx={{ display: "inline-flex", alignItems: "center", height: 22, px: 1, borderRadius: "6px",
              cursor: "pointer", bgcolor: "#e2dacb", color: DIM, fontSize: 11, fontWeight: 600,
              "&:hover": { bgcolor: "#d8cfbe" } }}>Reset view</Box>
        )}
      </Box>

      <Typography sx={{ position: "absolute", right: 16, bottom: 14, fontSize: 11, color: FAINT, textAlign: "right", lineHeight: 1.6 }}>
        A desk is a task · an agent at a keyboard is a live session · a free desk is spare capacity
      </Typography>
    </Box>
  );
}
