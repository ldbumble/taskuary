// The Board, drawn as a floor instead of four columns. A desk IS a task, the figure at it is
// the agent working it, and an empty desk is spare capacity - so "how much can run at once"
// stops being a number in Settings and becomes something you can see. Nothing here is a new
// source of truth: desks come from /api/agents, occupancy from the same /api/tasks the columns
// read, and the wall ports from /api/sources.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { PANEL, BORDER, DIM, FAINT, INK, ACCENT, ACCENT2, ROLES, mono } from "./theme.jsx";

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
const stateOf = (t) => {
  if (!t) return { label: "free", color: ROLES.muted.solid };
  if (isLive(t)) return { label: `${t.Session?.agent || t.RunAgent || "agent"} is typing`, color: ROLES.working.solid };
  if (t.Status === "waiting" || t.ReviewStatus === "pending") return { label: "waiting on you", color: ROLES.you.solid };
  return { label: "open", color: ROLES.muted.solid };
};

export default function StudioView({ onOpenTask }) {
  const [tasks, setTasks] = useState(null);
  const [agents, setAgents] = useState([]);
  const [sources, setSources] = useState([]);
  const [cam, setCam] = useState({ yaw: 0, zoom: 1.32, px: 0, py: 0 });
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
  const [pick, setPick] = useState(null);
  const [frame, setFrame] = useState(0);          // the only clock the room has

  const load = useCallback(async () => {
    const [t, a, s] = await Promise.all([
      api.get("/api/tasks").catch(() => ({ data: {} })),
      api.get("/api/agents").catch(() => ({ data: {} })),
      api.get("/api/sources").catch(() => ({ data: {} })),
    ]);
    setTasks((t.data.data || []).filter((x) => x.Status !== "dropped"));
    setAgents(a.data.data || a.data.agents || []);
    setSources((s.data.data || []).filter((x) => x.Active));
  }, []);
  useEffect(() => { load(); const id = setInterval(load, 15000); return () => clearInterval(id); }, [load]);

  const desks = useMemo(() => {
    const n = Math.max(4, Math.min(12, agents.length || 4));
    const live = (tasks || []).filter(isLive);
    const mine = (tasks || []).filter((t) => !live.includes(t) && (t.Status === "waiting" || t.ReviewStatus === "pending"));
    const seated = [...live, ...mine].slice(0, n);
    return Array.from({ length: n }, (_, i) => seated[i] || null);
  }, [tasks, agents]);

  const queue = useMemo(() => (tasks || []).filter(
    (t) => t.Status === "open" && !isLive(t) && !desks.includes(t)), [tasks, desks]);

  // Only tick when there is something to animate - a still room should not repaint.
  const busy = desks.some(isLive), walking = queue.length > 0 && desks.some((d) => !d);
  useEffect(() => {
    if (!busy && !walking) return undefined;
    const id = setInterval(() => setFrame((f) => f + 1), 160);
    return () => clearInterval(id);
  }, [busy, walking]);

  const picked = (tasks || []).find((t) => t.TaskId === pick) || null;

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

    const box = (x, y, w, d, h, top, left, right, zbias) => {
      const z = dep(x + w / 2, y + d / 2) + (zbias || 0);
      poly(z, pts(P(x, y + d, h), P(x + w, y + d, h), P(x + w, y + d, 0), P(x, y + d, 0)), left);
      poly(z, pts(P(x + w, y, h), P(x + w, y + d, h), P(x + w, y + d, 0), P(x + w, y, 0)), right);
      poly(z, pts(P(x, y, h), P(x + w, y, h), P(x + w, y + d, h), P(x, y + d, h)), top);
      return z;
    };

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
      const st = stateOf(t), live = isLive(t);
      const z = box(gx, gy, 2.0, 1.1, DH, "#d3c4a6", "#a8977a", "#bfae8f");
      const mx = gx + 0.6, mw = 0.85, my = gy + 0.3;
      box(mx + 0.28, my + 0.06, 0.3, 0.24, DH + 7, "#7c8794", "#616b77", "#8e97a1", 0.01);   // stand
      poly(z + 0.02, pts(P(mx - 0.05, my, DH + 6), P(mx + mw + 0.05, my, DH + 6),
        P(mx + mw + 0.05, my, DH + 40), P(mx - 0.05, my, DH + 40)), "#333b45");
      poly(z + 0.03, pts(P(mx, my, DH + 9), P(mx + mw, my, DH + 9),
        P(mx + mw, my, DH + 37), P(mx, my, DH + 37)), live ? "#1b212a" : "#cfc7b4");
      const pose = poseOf(t);
      if (pose === "paper") {                                 // a form on the desk, not a diff
        box(gx + 0.3, gy + 0.62, 1.0, 0.3, DH + 2, "#fffdfb", "#ded7c8", "#e8e2d5", 0.03);
        for (let k = 0; k < 3; k++) {
          const yy = gy + 0.70 + k * 0.07;
          poly(z + 0.05, pts(P(gx + 0.42, yy, DH + 2.1), P(gx + 1.18, yy, DH + 2.1),
            P(gx + 1.18, yy + 0.02, DH + 2.1), P(gx + 0.42, yy + 0.02, DH + 2.1)), k ? "#a9a294" : "#4d4a43");
        }
      }
      if (live && pose === "type") for (let k = 0; k < 3; k++) {   // code, scrolling as it types
        const zz = DH + 31 - k * 7, w2 = mw * (0.3 + ((k + frame) % 3) * 0.2);
        poly(z + 0.04, pts(P(mx + 0.08, my, zz), P(mx + 0.08 + w2, my, zz),
          P(mx + 0.08 + w2, my, zz + 2.6), P(mx + 0.08, my, zz + 2.6)), CODE[k]);
      }
      box(gx + 0.35, gy + 0.7, 0.9, 0.28, DH + 2, "#cfc7b4", "#aea595", "#bdb3a0", 0.02);    // keyboard
      if (t) person(gx + 1.0, gy - 0.55, SKINS[i % SKINS.length], poseOf(t), frame);
      const lab = P(gx + 1.0, gy + 0.55, DH + 58);
      return { t, st, x: lab[0], y: lab[1] };
    });

    // every connector gets a port on the back wall, and its mail arrives at it
    const room = Math.max(1, Math.floor((GX - 2.6) / 1.7));
    const ports = sources.slice(0, Math.min(4, room)).map((s, i) => {
      const x = 0.8 + i * 1.7;
      poly(BGZ, pts(P(x, 0, 58), P(x + 1.1, 0, 58), P(x + 1.1, 0, 84), P(x, 0, 84)), "#ffffff");
      poly(BGZ, pts(P(x + 0.08, 0, 61), P(x + 1.02, 0, 61), P(x + 1.02, 0, 81), P(x + 0.08, 0, 81)), i === 0 ? "#eae4d8" : "#e9e3d8");
      const m = P(x + 0.55, 0, 71);
      prims.push({ k: "l", z: BGZ + 1, d: `M ${m[0] + 80} ${m[1] - 170} Q ${m[0] + 44} ${m[1] - 78} ${m[0]} ${m[1]}`,
        stroke: i === 0 ? ACCENT : "#cbc2b0", o: i === 0 ? 0.75 : 0.4 });
      return { x: m[0], y: m[1] - 9, name: s.Channel === "report" ? "report" : s.Channel };
    });

    // somebody is walking in for the next queued task, door → the first free desk
    const freeIx = desks.findIndex((d) => !d);
    if (queue.length && freeIx >= 0) {
      const tx = 0.9 + (freeIx % cols) * 2.7 + 1.0, ty = 2.4 + Math.floor(freeIx / cols) * 2.9 - 0.55;
      const q = ((frame % 36) / 36);
      const e = q < 0.5 ? 2 * q * q : 1 - (-2 * q + 2) ** 2 / 2;
      person(dx + 0.55 + (tx - dx - 0.55) * e, 0.9 + (ty - 0.9) * e, SKINS[4], "walk", frame);
    }

    prims.sort((a, b) => a.z - b.z);
    return { prims, tags, ports };
  }, [cam.yaw, desks, sources, queue.length, frame]);

  if (!tasks) return <CircularProgress size={22} sx={{ m: 4 }} />;
  const free = desks.filter((d) => !d).length;
  const vw = W / cam.zoom, vh = H / cam.zoom;
  const vx = cam.px + (W - vw) / 2, vy = cam.py + (H - vh) / 2;
  // The chips are HTML on top of the SVG, so they must be projected through the same viewBox -
  // otherwise they drift off their desks the moment you zoom.
  const sx = (x) => `${((x - vx) / vw) * 100}%`;
  const sy = (y) => `${((y - vy) / vh) * 100}%`;
  const flyTo = (x, y) => nudge({ zoom: 2.1, px: x - W / 2, py: y - H / 2 });
  const moved = Math.abs(cam.yaw) > 0.01 || Math.abs(cam.zoom - 1.32) > 0.01;

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
        onWheel={onWheel} onDoubleClick={() => nudge({ yaw: 0, zoom: 1.32, px: 0, py: 0 })}
        sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", touchAction: "none",
          cursor: drag.current ? "grabbing" : "grab" }}>
        {scene.prims.map((p, i) => (p.k === "p"
          ? <polygon key={i} points={p.pts} fill={p.fill} opacity={p.o} />
          : p.k === "r" ? <rect key={i} x={p.x} y={p.y} width={p.w} height={p.h} rx={p.r} fill={p.fill} />
            : p.k === "e" ? <ellipse key={i} cx={p.cx} cy={p.cy} rx={p.rx} ry={p.ry} fill={p.fill} opacity={p.o} />
              : <path key={i} d={p.d} fill="none" stroke={p.stroke} strokeWidth="1.6" strokeDasharray="1 6"
                strokeLinecap="round" opacity={p.o} />))}
      </Box>

      {scene.ports.map((p) => (
        <Box key={p.name + p.x} sx={{ position: "absolute", left: sx(p.x), top: sy(p.y),
          transform: "translateX(-50%)", display: "flex", alignItems: "center", gap: 0.6,
          bgcolor: "rgba(255,255,255,.94)", border: `1px solid ${BORDER}`, borderRadius: "5px", px: 0.7, height: 19,
          fontSize: 10, fontWeight: 600, color: DIM, whiteSpace: "nowrap" }}>
          <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: ACCENT }} />{p.name}
        </Box>
      ))}

      {scene.tags.map((g, i) => (
        <Box key={i} onClick={() => { if (g.t) { setPick(g.t.TaskId); flyTo(g.x, g.y); } }}
          sx={{ position: "absolute", left: sx(g.x), top: sy(g.y), transform: "translateX(-50%)",
            display: "flex", alignItems: "center", gap: 0.7, bgcolor: PANEL, border: `1px solid ${BORDER}`,
            borderRadius: "6px", px: 0.9, height: 21, boxShadow: "0 2px 6px rgba(30,50,38,.10)",
            fontSize: 10.5, fontWeight: 600, whiteSpace: "nowrap", opacity: g.t ? 1 : 0.55,
            cursor: g.t ? "pointer" : "default",
            ...(pick && g.t?.TaskId === pick ? { borderColor: ACCENT, boxShadow: `0 0 0 2px ${ACCENT}22` } : {}),
            "&:hover": g.t ? { borderColor: "#d8cfbe" } : {} }}>
          <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: g.st.color }} />
          {g.t
            ? <><Box component="span" sx={{ ...mono, color: DIM }}>{g.t.ref}</Box>
              <Box component="span" sx={{ color: FAINT, fontWeight: 500 }}>{g.st.label}</Box></>
            : <Box component="span" sx={{ color: FAINT, fontWeight: 500 }}>free desk</Box>}
        </Box>
      ))}

      <Box sx={{ position: "absolute", left: 16, top: 12, width: 268, bgcolor: PANEL, border: `1px solid ${BORDER}`,
        borderRadius: "11px", boxShadow: "0 10px 28px rgba(30,50,38,.11)", overflow: "hidden" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.75, pt: 1.4, pb: 1.1, borderBottom: `1px solid ${BORDER}` }}>
          <Typography sx={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.3, color: FAINT, flex: 1 }}>WAITING FOR A DESK</Typography>
          <Typography sx={{ fontSize: 11, color: FAINT }}>{queue.length}</Typography>
        </Box>
        {queue.slice(0, 3).map((t) => (
          <Box key={t.TaskId} onClick={() => onOpenTask(t.TaskId)}
            sx={{ px: 1.75, py: 1.1, borderBottom: `1px solid ${BORDER}`, cursor: "pointer", "&:hover": { bgcolor: "#f4f1ec" } }}>
            <Typography sx={{ ...mono, fontSize: 10.5, color: FAINT }}>{t.ref}</Typography>
            <Typography noWrap sx={{ fontSize: 12.5, fontWeight: 600, color: INK, pt: 0.4 }}>{t.Title}</Typography>
          </Box>
        ))}
        {!queue.length && <Typography sx={{ px: 1.75, py: 1.4, fontSize: 12, color: FAINT }}>Nothing is waiting — every open task has a desk.</Typography>}
        <Typography sx={{ px: 1.75, py: 1.1, fontSize: 11, color: FAINT, lineHeight: 1.5 }}>
          {desks.length} desks — one per agent you have connected. {free} free.
        </Typography>
      </Box>

      {picked && (
        <Box sx={{ position: "absolute", right: 16, top: 12, width: 292, bgcolor: PANEL, border: `1px solid ${BORDER}`,
          borderRadius: "11px", boxShadow: "0 10px 28px rgba(30,50,38,.11)", overflow: "hidden" }}>
          <Box sx={{ px: 1.75, pt: 1.4, pb: 1.2, borderBottom: `1px solid ${BORDER}` }}>
            <Typography sx={{ ...mono, fontSize: 10.5, color: FAINT }}>{picked.ref} · {stateOf(picked).label}</Typography>
            <Typography sx={{ fontSize: 13.5, fontWeight: 700, color: INK, pt: 0.6, lineHeight: 1.35 }}>{picked.Title}</Typography>
          </Box>
          {picked.Summary && (
            <Typography sx={{ px: 1.75, py: 1.2, fontSize: 12, color: DIM, lineHeight: 1.55,
              display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
              {picked.Summary}
            </Typography>
          )}
          <Box onClick={() => onOpenTask(picked.TaskId)}
            sx={{ px: 1.75, py: 1.2, borderTop: `1px solid ${BORDER}`, cursor: "pointer", color: ACCENT,
              fontSize: 12.5, fontWeight: 600, "&:hover": { bgcolor: "#f4f1ec" } }}>
            Open the task →
          </Box>
        </Box>
      )}

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
          <Box onClick={() => nudge({ yaw: 0, zoom: 1.32, px: 0, py: 0 })}
            sx={{ display: "inline-flex", alignItems: "center", height: 22, px: 1, borderRadius: "6px",
              cursor: "pointer", bgcolor: "#e2dacb", color: DIM, fontSize: 11, fontWeight: 600,
              "&:hover": { bgcolor: "#d8cfbe" } }}>Reset view</Box>
        )}
      </Box>

      <Typography sx={{ position: "absolute", right: 16, bottom: 14, fontSize: 11, color: FAINT, textAlign: "right", lineHeight: 1.6 }}>
        A desk is a task · an agent at a keyboard is a live session · a free desk is spare capacity<br />
        Mail lands on the wall port it came from
      </Typography>
    </Box>
  );
}
