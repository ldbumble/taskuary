// The Board, drawn as a floor instead of four columns. A desk IS a task, the figure at it is
// the agent working it, and an empty desk is spare capacity - so "how much can run at once"
// stops being a number in Settings and becomes something you can see. Nothing here is a new
// source of truth: desks come from /api/agents, occupancy from the same /api/tasks the columns
// read, and the wall ports from /api/sources.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Box, CircularProgress, Typography } from "@mui/material";
import api from "./api";
import { PANEL, BORDER, DIM, FAINT, INK, ACCENT, ACCENT2, mono } from "./theme.jsx";

// Logical drawing space; the SVG scales it, so every number below is layout, not pixels.
const W = 1200, H = 640;
const GX = 11, GY = 8;                     // floor in grid squares
const TW = 40, TH = 22;                    // half-width / half-height of one square

// Four corners to stand in. A rotation is a coordinate remap, not a 3D engine - the whole
// feature is these four lines, which is why it was worth doing.
const ROT = [
  (x, y) => [x, y],
  (x, y) => [y, GX - x],
  (x, y) => [GX - x, GY - y],
  (x, y) => [GY - y, x],
];
const CORNERS = ["north-west", "north-east", "south-east", "south-west"];

// Sitting DOWN is the whole reason for a depth sort: a figure placed behind a desk has to be
// painted before it, or it floats on top of the furniture.
const byDepth = (a, b) => a.z - b.z;

const SKINS = [
  { body: "#7d9e6c", collar: "#eef3e6", skin: "#f0e2d2", hair: "#3e4a3c" },
  { body: "#4f7a63", collar: "#e8f1ea", skin: "#eddfcf", hair: "#2c3a31" },
  { body: "#8a978f", collar: "#eef1ec", skin: "#eedfcd", hair: "#33403a" },
  { body: "#6f9b94", collar: "#e6f1ef", skin: "#f2e5d5", hair: "#2e3f3c" },
  { body: "#b3bcaa", collar: "#f2f4ee", skin: "#f2e5d5", hair: "#4b4636" },
];

// Which colour a desk's state gets. Same three the Timeline uses, for the same three meanings.
const stateOf = (t) => {
  if (!t) return { label: "spare capacity", color: "#9aa39b" };
  if (t.Session || t.RunStatus === "running") return { label: `${t.Session?.agent || t.AgentName || "agent"} working`, color: ACCENT2 };
  if (t.Status === "waiting" || t.ReviewStatus === "pending") return { label: "waiting on you", color: ACCENT };
  return { label: "open", color: "#7d9e6c" };
};

export default function StudioView({ onOpenTask }) {
  const [tasks, setTasks] = useState(null);
  const [agents, setAgents] = useState([]);
  const [sources, setSources] = useState([]);
  const [rot, setRot] = useState(0);
  const [pick, setPick] = useState(null);          // TaskId of the desk you clicked

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

  // A desk per agent you actually have - that is what "how many can run at once" means here.
  // Busy tasks take the desks first so the room reads left-to-right by urgency.
  const desks = useMemo(() => {
    const n = Math.max(4, Math.min(12, agents.length || 4));
    const live = (tasks || []).filter((t) => t.Session || t.RunStatus === "running");
    const mine = (tasks || []).filter((t) => !live.includes(t) && (t.Status === "waiting" || t.ReviewStatus === "pending"));
    const seated = [...live, ...mine].slice(0, n);
    return Array.from({ length: n }, (_, i) => seated[i] || null);
  }, [tasks, agents]);

  const queue = useMemo(() => (tasks || []).filter(
    (t) => t.Status === "open" && !t.Session && t.RunStatus !== "running" && !desks.includes(t)), [tasks, desks]);

  const picked = (tasks || []).find((t) => t.TaskId === pick) || null;

  // ── the room ──────────────────────────────────────────────────────────────────────────
  const scene = useMemo(() => {
    const map = ROT[rot];
    const raw = (x, y, z) => { const [u, v] = map(x, y); return [(u - v) * TW, (u + v) * TH - z]; };
    // centre whatever the rotation produced, so all four corners frame the same way
    const cs = [[0, 0], [GX, 0], [GX, GY], [0, GY]].map(([x, y]) => raw(x, y, 0));
    const xs = cs.map((p) => p[0]), ys = cs.map((p) => p[1]);
    const ox = W / 2 - (Math.min(...xs) + Math.max(...xs)) / 2;
    const oy = H / 2 - (Math.min(...ys) + Math.max(...ys)) / 2 - 30;
    const P = (x, y, z) => { const p = raw(x, y, z); return [p[0] + ox, p[1] + oy]; };
    const pts = (...ps) => ps.map((p) => p.join(",")).join(" ");
    const prims = [];
    const poly = (z, p, fill, o) => prims.push({ k: "p", z, pts: p, fill, o: o == null ? 1 : o });
    const rect = (z, x, y, w, h, r, fill) => prims.push({ k: "r", z, x, y, w, h, r, fill });
    const oval = (z, cx, cy, rx, ry, fill, o) => prims.push({ k: "e", z, cx, cy, rx, ry, fill, o: o == null ? 1 : o });
    const dep = (x, y) => { const [u, v] = map(x, y); return u + v; };
    const BGZ = -1e4;

    const c = [P(0, 0, 0), P(GX, 0, 0), P(GX, GY, 0), P(0, GY, 0)];
    const dn = (p) => [p[0], p[1] + 20];
    poly(BGZ, pts(c[3], c[2], dn(c[2]), dn(c[3])), "#3f6b52");
    poly(BGZ, pts(c[2], c[1], dn(c[1]), dn(c[2])), "#345a44");
    poly(BGZ, pts(c[0], c[1], c[2], c[3]), "#e6e9e0");
    const WH = 150;
    poly(BGZ, pts(P(0, 0, 0), P(GX, 0, 0), P(GX, 0, WH), P(0, 0, WH)), "#f1f3ed");
    poly(BGZ, pts(P(0, 0, 0), P(0, GY, 0), P(0, GY, WH), P(0, 0, WH)), "#e3e7dd");
    poly(BGZ, pts(P(0, 0, 100), P(GX, 0, 100), P(GX, 0, 103), P(0, 0, 103)), "#cfd8ca");

    const box = (x, y, w, d, h, top, left, right, o) => {
      const z = dep(x + w / 2, y + d / 2);
      poly(z, pts(P(x, y + d, h), P(x + w, y + d, h), P(x + w, y + d, 0), P(x, y + d, 0)), left, o);
      poly(z, pts(P(x + w, y, h), P(x + w, y + d, h), P(x + w, y + d, 0), P(x + w, y, 0)), right, o);
      poly(z, pts(P(x, y, h), P(x + w, y, h), P(x + w, y + d, h), P(x, y + d, h)), top, o);
      return z;
    };

    // the door work walks in through
    poly(BGZ, pts(P(9.3, 0, 0), P(10.4, 0, 0), P(10.4, 0, 118), P(9.3, 0, 118)), "#aeb5a7");
    poly(BGZ, pts(P(9.42, 0, 0), P(10.28, 0, 0), P(10.28, 0, 110), P(9.42, 0, 110)), "#f7fbf4");
    poly(BGZ, pts(P(9.42, 0, 0), P(10.28, 0, 0), P(10.6, 1.7, 0), P(9.1, 1.7, 0)), "#eef3e6");

    const person = (x, y, s, seated) => {
      const p = P(x, y, 0), z = dep(x, y) + (seated ? -0.02 : 0);
      const cx = p[0], cy = p[1] - (seated ? 8 : 0);
      oval(z, cx, p[1], 12, 5, "rgba(40,60,46,.15)");
      rect(z, cx - 10, cy - 29, 20, 29, 8, s.body);
      poly(z + 0.001, pts([cx - 5, cy - 29], [cx + 5, cy - 29], [cx, cy - 20]), s.collar);
      rect(z + 0.002, cx - 9, cy - 46, 18, 18, 7, s.skin);
      rect(z + 0.003, cx - 10, cy - 48, 20, 9.5, 4.5, s.hair);
      oval(z + 0.004, cx - 3.4, cy - 35.5, 1.4, 1.8, "#26302a");
      oval(z + 0.004, cx + 3.4, cy - 35.5, 1.4, 1.8, "#26302a");
    };

    // a workstation: desk, a monitor facing the room with code on it, keyboard, mouse
    const CODE = ["#7d9e6c", "#2f6b4f", "#8fae7e", "#a8b8a0"];
    const XS = [0.9, 3.4, 5.9, 8.4], YS = [2.3, 5.1];
    const tags = desks.map((t, i) => {
      const x = XS[i % 4], y = YS[Math.floor(i / 4) % 2] + (i >= 8 ? 2.6 : 0);
      const st = stateOf(t);
      const z = box(x, y, 2.0, 1.15, 32, "#cfd5c8", "#9aa294", "#aeb5a7");
      const mx = x + 0.45, mw = 0.95, my = y + 0.18;
      box(mx + 0.3, my + 0.12, 0.35, 0.3, 38, "#b9c0b2", "#98a094", "#a9b0a2");
      poly(z + 0.01, pts(P(mx - 0.06, my, 36), P(mx + mw + 0.06, my, 36), P(mx + mw + 0.06, my, 88), P(mx - 0.06, my, 88)), "#2b3630");
      poly(z + 0.02, pts(P(mx, my, 40), P(mx + mw, my, 40), P(mx + mw, my, 84), P(mx, my, 84)), t ? "#141d18" : "#e8ebe4");
      if (t) for (let k = 0; k < 4; k++) {
        const zz = 75 - k * 9, w2 = mw * (0.32 + (k % 3) * 0.21);
        poly(z + 0.03, pts(P(mx + 0.09, my, zz), P(mx + 0.09 + w2, my, zz), P(mx + 0.09 + w2, my, zz + 3.5), P(mx + 0.09, my, zz + 3.5)), CODE[k]);
      }
      box(x + 0.35, y + 0.72, 0.95, 0.3, 34, "#dfe4da", "#bcc3b6", "#ccd2c5");
      box(x + 1.45, y + 0.78, 0.22, 0.22, 34, "#dfe4da", "#bcc3b6", "#ccd2c5");
      if (t) person(x + 1.0, y - 0.62, SKINS[i % SKINS.length], true);
      const lab = P(x + 1.0, y + 0.55, 94);
      return { t, st, x: lab[0], y: lab[1] };
    });

    // every connector gets a port on the back wall, and its mail arrives at it
    const ports = sources.slice(0, 4).map((s, i) => {
      const x = 1.0 + i * 1.85;
      poly(BGZ, pts(P(x, 0, 70), P(x + 1.1, 0, 70), P(x + 1.1, 0, 100), P(x, 0, 100)), "#ffffff");
      poly(BGZ, pts(P(x + 0.08, 0, 73), P(x + 1.02, 0, 73), P(x + 1.02, 0, 97), P(x + 0.08, 0, 97)), i === 0 ? "#e4efe8" : "#eef1eb");
      const m = P(x + 0.55, 0, 85);
      prims.push({ k: "l", z: BGZ + 1, d: `M ${m[0] + 90} ${m[1] - 190} Q ${m[0] + 48} ${m[1] - 88} ${m[0]} ${m[1]}`,
        stroke: i === 0 ? ACCENT : "#c2cabb", o: i === 0 ? 0.8 : 0.45 });
      return { x: m[0], y: m[1] - 10, name: (s.Channel === "report" ? "report" : s.Channel), addr: s.Address };
    });

    if (queue.length) person(9.55, 1.0, SKINS[4], false);   // one walking in for the queue
    prims.sort(byDepth);
    return { prims, tags, ports };
  }, [rot, desks, sources, queue.length]);

  if (!tasks) return <CircularProgress size={22} sx={{ m: 4 }} />;

  const free = desks.filter((d) => !d).length;
  const pc = (v, total) => `${(v / total) * 100}%`;

  return (
    <Box sx={{ position: "relative", width: "100%", height: "calc(100vh - 190px)", minHeight: 520, overflow: "hidden" }}>
      <Box component="svg" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet"
        sx={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}>
        {scene.prims.map((p, i) => (p.k === "p"
          ? <polygon key={i} points={p.pts} fill={p.fill} opacity={p.o} />
          : p.k === "r" ? <rect key={i} x={p.x} y={p.y} width={p.w} height={p.h} rx={p.r} fill={p.fill} />
            : p.k === "e" ? <ellipse key={i} cx={p.cx} cy={p.cy} rx={p.rx} ry={p.ry} fill={p.fill} opacity={p.o} />
              : <path key={i} d={p.d} fill="none" stroke={p.stroke} strokeWidth="1.6" strokeDasharray="1 6"
                strokeLinecap="round" opacity={p.o} />))}
      </Box>

      {/* the wall ports, in words */}
      {scene.ports.map((p) => (
        <Box key={p.name + p.addr} sx={{ position: "absolute", left: pc(p.x, W), top: pc(p.y, H),
          transform: "translateX(-50%)", display: "flex", alignItems: "center", gap: 0.6,
          bgcolor: "rgba(255,255,255,.94)", border: `1px solid ${BORDER}`, borderRadius: "5px", px: 0.7, height: 19,
          fontSize: 10, fontWeight: 600, color: DIM, whiteSpace: "nowrap" }}>
          <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: ACCENT }} />
          {p.name}
        </Box>
      ))}

      {/* a desk carries what a board card carries */}
      {scene.tags.map((g, i) => (
        <Box key={i} onClick={() => g.t && setPick(g.t.TaskId)}
          sx={{ position: "absolute", left: pc(g.x, W), top: pc(g.y, H), transform: "translateX(-50%)",
            display: "flex", alignItems: "center", gap: 0.7, bgcolor: PANEL, border: `1px solid ${BORDER}`,
            borderRadius: "6px", px: 0.9, height: 21, boxShadow: "0 2px 6px rgba(30,50,38,.10)",
            fontSize: 10.5, fontWeight: 600, whiteSpace: "nowrap", opacity: g.t ? 1 : 0.62,
            cursor: g.t ? "pointer" : "default",
            ...(pick && g.t?.TaskId === pick ? { borderColor: ACCENT, boxShadow: `0 0 0 2px ${ACCENT}22` } : {}),
            "&:hover": g.t ? { borderColor: "#b6d0c2" } : {} }}>
          <Box sx={{ width: 6, height: 6, borderRadius: "50%", bgcolor: g.st.color }} />
          {g.t ? <Box component="span" sx={{ ...mono, color: DIM }}>{g.t.ref}</Box> : <Box component="span" sx={{ color: FAINT }}>free desk</Box>}
          <Box component="span" sx={{ color: FAINT, fontWeight: 500 }}>{g.st.label}</Box>
        </Box>
      ))}

      {/* who is waiting for a desk */}
      <Box sx={{ position: "absolute", left: 16, top: 12, width: 272, bgcolor: PANEL, border: `1px solid ${BORDER}`,
        borderRadius: "11px", boxShadow: "0 10px 28px rgba(30,50,38,.11)", overflow: "hidden" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.75, pt: 1.4, pb: 1.1, borderBottom: `1px solid ${BORDER}` }}>
          <Typography sx={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.3, color: FAINT, flex: 1 }}>WAITING FOR A DESK</Typography>
          <Typography sx={{ fontSize: 11, color: FAINT }}>{queue.length}</Typography>
        </Box>
        {queue.slice(0, 3).map((t) => (
          <Box key={t.TaskId} onClick={() => onOpenTask(t.TaskId)}
            sx={{ px: 1.75, py: 1.1, borderBottom: `1px solid ${BORDER}`, cursor: "pointer", "&:hover": { bgcolor: "#f7f9f5" } }}>
            <Typography sx={{ ...mono, fontSize: 10.5, color: FAINT }}>{t.ref}</Typography>
            <Typography noWrap sx={{ fontSize: 12.5, fontWeight: 600, color: INK, pt: 0.4 }}>{t.Title}</Typography>
          </Box>
        ))}
        {!queue.length && <Typography sx={{ px: 1.75, py: 1.4, fontSize: 12, color: FAINT }}>Nothing is waiting — every open task has a desk.</Typography>}
        <Typography sx={{ px: 1.75, py: 1.1, fontSize: 11, color: FAINT, lineHeight: 1.5 }}>
          {desks.length} desks — one per agent you have connected. {free} free.
        </Typography>
      </Box>

      {/* the desk you clicked */}
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
              fontSize: 12.5, fontWeight: 600, "&:hover": { bgcolor: "#f7f9f5" } }}>
            Open the task →
          </Box>
        </Box>
      )}

      {/* stand somewhere else. A rotation is a coordinate remap - see ROT. */}
      <Box sx={{ position: "absolute", left: 16, bottom: 14, display: "flex", alignItems: "center", gap: 1.1,
        bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: "11px", px: 1.4, py: 1,
        boxShadow: "0 10px 28px rgba(30,50,38,.11)" }}>
        <Typography sx={{ fontSize: 10, fontWeight: 700, letterSpacing: 1.3, color: FAINT }}>VIEW FROM</Typography>
        <Box sx={{ display: "flex", gap: 0.4 }}>
          {CORNERS.map((c, i) => (
            <Box key={c} onClick={() => setRot(i)} title={c}
              sx={{ width: 26, height: 24, borderRadius: "6px", cursor: "pointer", display: "flex",
                alignItems: "center", justifyContent: "center", bgcolor: rot === i ? ACCENT : "#eef1eb" }}>
              <Box component="svg" width="13" height="13" viewBox="0 0 24 24" fill="none"
                stroke={rot === i ? "#f4faf6" : FAINT} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
                sx={{ transform: `rotate(${i * 90}deg)` }}>
                <path d="M4 20 12 4l8 16" />
              </Box>
            </Box>
          ))}
        </Box>
        <Typography sx={{ fontSize: 11, color: FAINT }}>{CORNERS[rot]} corner</Typography>
      </Box>

      <Typography sx={{ position: "absolute", right: 16, bottom: 14, fontSize: 11, color: FAINT, textAlign: "right", lineHeight: 1.6 }}>
        A desk is a task · the figure at it is the agent on it · a free desk is spare capacity<br />
        Mail lands on the wall port it came from
      </Typography>
    </Box>
  );
}
