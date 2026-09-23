// The Assistant, played as a game: the same pile the chat walks you through, drawn as an office you
// walk around. Every figure is a real task, message, fyi or Hub file, and every real move (send, hand
// off, unblock, follow up) scores. Walk with WASD/arrows, E to talk to whoever you are next to, 1-5
// to jump to a room, Esc back out. It is a third way to use the Assistant tab (Chat | Task | Game),
// not a Board view - the Studio stays the Board's floor.
import React, { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import { Box, CircularProgress, Slider, Typography, useMediaQuery } from "@mui/material";

import api from "./api";
import { pollWhileVisible } from "./visible.js";
import { onLive } from "./live.js";
import { isAgentKind } from "./autostart.js";
import { mono } from "./theme.jsx";
import { FileChips } from "./BoardView.jsx";
import { WorkLine, isWaiting } from "./ui.jsx";
import { studioSeats, studioTaskIsLive, studioTaskState } from "./studioModel.js";
import { laneMeta } from "./funnelPile.js";
import { proposalOf } from "./proposalCard.js";
import { Btn, G, ItemInspector, Moves, Who, errText, glass } from "./gameItem.jsx";
import { runOperation } from "./taskOps.js";
import {
  channelKind, ZONES, zoneMeta, zoneItems, needsYou, bossHp, matchFor, award, levelOf, loadGame, saveGame, shareCard,
  MOVE_WORDS, ACHIEVEMENTS, questsFor, questProgress, COMBO_WINDOW, comboMult,
} from "./assistantGame.js";

const GameScene = React.lazy(() => import("./GameScene.jsx"));

// the game wears its own dark glass over the warm room - the one screen in the app that is meant to be loud (gameItem.jsx)

// a few synthesized blips; nothing to download, off with one click
function useSound() {
  const [on, setOn] = useState(() => { try { return localStorage.getItem("taskuary.assistantGame.sound") !== "0"; } catch { return true; } });
  const ctx = useRef(null);
  const play = useCallback((notes) => {
    if (!on) return;
    try {
      ctx.current ||= new (window.AudioContext || window.webkitAudioContext)();
      const c = ctx.current, t0 = c.currentTime;
      notes.forEach(([f, at, len = 0.09, type = "square"]) => {
        const o = c.createOscillator(), g = c.createGain();
        o.type = type; o.frequency.value = f;
        g.gain.setValueAtTime(0.0001, t0 + at); g.gain.exponentialRampToValueAtTime(0.05, t0 + at + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, t0 + at + len);
        o.connect(g).connect(c.destination); o.start(t0 + at); o.stop(t0 + at + len + 0.02);
      });
    } catch { /* no audio device: the game plays silent */ }
  }, [on]);
  const toggle = () => setOn((v) => { try { localStorage.setItem("taskuary.assistantGame.sound", v ? "0" : "1"); } catch { /* */ } return !v; });
  return { on, toggle, coin: () => play([[988, 0], [1319, 0.07, 0.16]]),
    level: () => play([[523, 0], [659, 0.1], [784, 0.2], [1047, 0.3, 0.3]]),
    whoosh: () => play([[220, 0, 0.12, "sine"], [330, 0.05, 0.12, "sine"]]),
    nope: () => play([[196, 0, 0.18, "sawtooth"]]) };
}

const MARKS = { approve: { glyph: "✓", tone: "send" }, fyi: { glyph: "i", tone: "info" }, report: { glyph: "i", tone: "info" },
  broken: { glyph: "!", tone: "bad" }, forgotten: { glyph: "?", tone: "ask" } };
const markOf = (item) => MARKS[item.lane] || (needsYou(item) ? { glyph: "!", tone: "need" } : null);

export default function AssistantGame({ onOpenTask, onExit, onNavigate, active = true }) {
  const [tasks, setTasks] = useState(null);
  const [agents, setAgents] = useState([]);
  const [cap, setCap] = useState(null);
  const [live, setLive] = useState({});
  const [pick, setPick] = useState(null);
  const [clock, setClock] = useState(Date.now());
  const [pile, setPile] = useState([]);
  const [hub, setHub] = useState({ topics: [], data: [] });
  const [focus, setFocus] = useState("all");
  const [picked, setPicked] = useState(null);     // the item (or cabinet topic, or gym task) in hand
  const [mine, setMine] = useState([]);            // your own tasks (Kind "task") - the gym's stations
  const [passed, setPassed] = useState(() => new Set());   // what Next already read this visit
  const [game, setGame] = useState(() => loadGame());
  const [toasts, setToasts] = useState([]);
  // big moments, one at a time: a queue, so a trophy won by the same move never covers the boss falling.
  // setBanner(b) queues it (the bottom and a cleared gym jump the line); setBanner(null) puts the shown one down.
  const [banners, setBanners] = useState([]);
  const banner = banners[0] || null;
  const setBanner = (b) => setBanners((q) => !b ? q.slice(1) : q.some((x) => x.title === b.title && x.kind === b.kind) ? q
    : b.kind === "bottom" || b.kind === "gymclear" ? [b, ...q] : [...q, b]);
  const [busy, setBusy] = useState("");
  const [trophies, setTrophies] = useState(false);
  const [folded, setFolded] = useState(false);    // the room panel, down to its title bar
  const [chat, setChat] = useState([{ who: "core", text: "I'm the Assistant Core. Ask me who should take what, or what to do next - I read the same pile you do." }]);
  const sound = useSound();
  const wide = useMediaQuery("(min-width:900px)");
  const opened = useRef(new Set());
  // moves can land back to back (Drain the pot): each must score on the one before it, not on a render's snapshot
  const gameRef = useRef(game), pileRef = useRef(pile), lastAsk = useRef(0);
  pileRef.current = pile;

  const load = useCallback(async () => {
    const [taskResponse, agentResponse, settingResponse] = await Promise.all([
      api.get("/api/tasks", { params: { active: 1 } }).catch(() => ({ data: {} })),
      api.get("/api/agents").catch(() => ({ data: {} })),
      api.get("/api/settings").catch(() => ({ data: {} })),
    ]);
    // the same floor as the columns, so the same rule: only work an agent runs (isAgentKind)
    const all = (taskResponse.data.data || []).filter((task) => task.Status !== "dropped");
    setTasks(all.filter((task) => isAgentKind(task.Kind)));
    // ...and the rest of the list, the one the Board leaves out: yours to do, nothing works it
    setMine(all.filter((task) => task.Kind === "task" && task.Status !== "done"));
    setAgents(agentResponse.data.data || agentResponse.data.agents || []);
    const row = (settingResponse.data.data || []).find((setting) => setting.Name === "auto_sessions");
    setCap((current) => current == null ? Math.max(1, Math.min(8, parseInt(row?.Value, 10) || 4)) : current);
  }, []);
  // the rest of the office: the assistant's pile (people, fyi's, ghosts), the Hub's cabinets, and the drafts behind "reply ready"
  const loadWorld = useCallback(async () => {
    const [p, h] = await Promise.all([
      api.get("/api/funnel/pile").catch(() => null),
      api.get("/api/hub").catch(() => null),
    ]);
    if (p) setPile(p.data?.items || []);
    if (h) setHub({ topics: h.data?.topics || [], data: h.data?.data || [] });
  }, []);

  useEffect(() => {
    if (!active) return undefined;
    load(); loadWorld();
    const offTask = onLive("task-changed", load);
    const offWorld = onLive(["feed-changed", "task-changed"], loadWorld, { wait: 1200, max: 5000 });
    return () => { offTask?.(); offWorld?.(); };
  }, [active, load, loadWorld]);
  useEffect(() => {
    const update = () => api.get("/api/runs/live").then(({ data }) => {
      setLive(Object.fromEntries((data.data || []).map((run) => [run.TaskId, run])));
    }).catch(() => {});
    if (!active) return undefined;
    update();
    const interval = setInterval(update, 3000);
    return () => clearInterval(interval);
  }, [active]);
  useEffect(() => active ? pollWhileVisible(() => setClock(Date.now()), 30000) : undefined, [active]);
  useEffect(() => active ? pollWhileVisible(loadWorld, 20000) : undefined, [active, loadWorld]);
  // the combo meter drains on screen, so it needs a faster tick than the clock above
  const [, beat] = useReducer((n) => n + 1, 0);
  useEffect(() => { if (!active) return undefined; const t = setInterval(beat, 1000); return () => clearInterval(t); }, [active]);

  const desks = useMemo(() => studioSeats(tasks || [], cap ?? 4), [tasks, cap]);
  const queue = useMemo(() => (tasks || []).filter((task) => task.Status === "open"
    && !studioTaskIsLive(task) && !desks.includes(task)), [tasks, desks]);
  const sceneSeats = useMemo(() => desks.map((task) => task ? {
    task,
    liveRow: live[task.TaskId] || null,
    state: studioTaskState(task, live[task.TaskId], agents, clock),
  } : null), [desks, live, agents, clock]);
  // Next read these: what only wanted knowing leaves the room; what still needs you stays, read
  const shown = useMemo(() => pile.filter((i) => !passed.has(i.key) || needsYou(i)), [pile, passed]);
  const zones = useMemo(() => zoneItems(shown), [shown]);
  // the gym: every task of yours, with its pile item when the assistant has one on it (that brings the moves)
  const gym = useMemo(() => {
    const byTid = Object.fromEntries(zones.gym.filter((i) => i.tid).map((i) => [i.tid, i]));
    const rows = mine.map((t) => ({ key: byTid[t.TaskId]?.key || `task:${t.TaskId}`, task: t, item: byTid[t.TaskId] || null }));
    const seen = new Set(mine.map((t) => t.TaskId));
    return [...rows, ...zones.gym.filter((i) => !seen.has(i.tid)).map((i) => ({ key: i.key, task: null, item: i }))];
  }, [mine, zones]);
  const npcs = useMemo(() => [
    ...["meeting", "coffee", "archive"].flatMap((zone) => zones[zone].filter((i) => i.kind !== "meeting").map((i) => ({
      key: i.key, zone, sub: channelKind(i), who: i.who || laneMeta(i.lane).word, title: i.title, mark: markOf(i) }))),
    ...gym.map((g) => {
      const list = rowChecklist(g.task), done = list.filter((c) => c.done).length;
      return { key: g.key, zone: "gym", who: g.task?.ref || g.item?.ref || "your task", title: g.task?.Title || g.item?.title,
        mark: g.item && needsYou(g.item) ? { glyph: "!", tone: "need" } : list.length ? { glyph: `${done}/${list.length}`, tone: "send" } : null };
    }),
  ], [zones, gym]);
  const meetings = useMemo(() => zones.meeting.filter((i) => i.kind === "meeting" || i.lane === "time")
    .map((i) => ({ title: i.title, when: String(i.event?.start || i.when || "").slice(11, 16) })), [zones]);
  const zoneCounts = useMemo(() => ({
    floor: zones.floor.filter(needsYou).length, gym: gym.length, meeting: zones.meeting.filter(needsYou).length,
    coffee: zones.coffee.length, archive: zones.archive.length, hq: 0,
  }), [zones, gym]);
  const byKey = useMemo(() => Object.fromEntries(pile.map((i) => [i.key, i])), [pile]);
  // the boss: what is left before the bottom. Its bar is measured against the most it has had this visit.
  const hp = bossHp(pile, passed), hpMax = useRef(1);
  hpMax.current = Math.max(hpMax.current, hp, 1);
  // today's quests, sized to what is actually here (questsFor): replies you could send, things an agent could
  // take, fyi's to read, boxes left to tick
  const quests = useMemo(() => questsFor(game, {
    approve: pile.filter((i) => i.lane === "approve" || (i.lane === "asked" && i.mid)).length,
    dispatch: pile.filter((i) => matchFor(i, agents).verb === "dispatch").length,
    read: pile.filter((i) => (i.lane === "fyi" || i.lane === "report" || i.kind === "fyis") && !i.bad && !passed.has(i.key)).length,
    rep: mine.reduce((n, t) => n + rowChecklist(t).filter((c) => !c.done).length, 0),
  }), [game, pile, agents, mine, passed]);
  const questsRef = useRef(quests);
  questsRef.current = quests;

  useEffect(() => {
    if (pick && !desks.some((task) => task?.TaskId === pick)) setPick(null);
  }, [desks, pick]);

  // keys: 1-6 jump into a space, N is Next, Esc walks back out. Never while you are typing.
  useEffect(() => {
    if (!active) return undefined;
    const onKey = (e) => {
      if (e.target?.closest?.("input, textarea, [contenteditable=true]") || e.metaKey || e.ctrlKey || e.altKey) return;
      const z = ZONES.find((x) => x.hotkey === e.key);
      if (z) { e.preventDefault(); go(z.key); }
      else if ((e.key === "n" || e.key === "N") && byKey[picked]) { e.preventDefault(); next(byKey[picked]); }
      else if (e.key === "Escape") { e.preventDefault(); go("all"); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const toast = (t) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((xs) => [...xs.slice(-3), { id, ...t }]);
    setTimeout(() => setToasts((xs) => xs.filter((x) => x.id !== id)), t.ms || 2600);
  };
  const go = (zone, key = null) => { if (zone !== focus) sound.whoosh(); setFocus(zone); setPicked(key); };

  // the one door every real move goes through: do it, and only if it went through, score it
  const play = async (move, key, run) => {
    setBusy(key || move || "busy");
    try {
      const out = await run();
      const left = key ? pileRef.current.filter((i) => i.key !== key || move === "draft") : pileRef.current;
      pileRef.current = left;
      const world = { meeting: zoneItems(left).meeting.filter(needsYou).length, coffee: zoneItems(left).coffee.length, quests: questsRef.current };
      if (!move) { if (key) setPile(left); return out; }       // a move that does not score (a second question inside a minute)
      const r = award(gameRef.current, move, Date.now(), world);
      gameRef.current = r.state; setGame(r.state); saveGame(r.state);
      if (r.gained > 0) { sound.coin(); toast({ kind: "xp", text: `+${r.gained} XP`, sub: `${MOVE_WORDS[move]}${r.mult > 1 ? ` · combo x${r.mult}` : ""}` }); }
      r.quests.forEach((q) => toast({ kind: "quest", text: `Quest done +${q.xp}`, sub: q.label || q.says(q.n), ms: 3600 }));
      if (r.levelUp) { sound.level(); setBanner({ kind: "level", title: `Level ${r.levelUp.level}`, sub: r.levelUp.title }); }
      r.unlocked.forEach((a) => { sound.level(); setBanner({ kind: "trophy", title: a.name, sub: a.says }); });
      if (key) setPile(left);
      setPicked((p) => p === key && move !== "draft" ? null : p);
      loadWorld(); load();
      return out;
    } catch (e) { sound.nope(); toast({ kind: "err", text: "Didn't land", sub: errText(e), ms: 4200 }); return null; }
    finally { setBusy(""); }
  };
  useEffect(() => { if (!banner) return undefined; const t = setTimeout(() => setBanner(null), banner.kind === "bottom" || banner.kind === "gymclear" ? 4200 : 2600); return () => clearTimeout(t); }, [banner]);

  const settle = (item, verb, move) => play(move, item.key, () => api.post("/api/funnel/settle", { key: item.key, verb }));
  // NEXT, the chat's own: this one is read (settle surfaced, read - "shown is read"), and the next thing in
  // the assistant's ranked order comes up, wherever in the office it stands - you walk there
  const knowOnly = (i) => (i.lane === "fyi" || i.lane === "report" || i.kind === "fyis") && !i.bad;
  const nextAfter = (key) => {
    const order = pileRef.current.filter((i) => i.key !== key && !passedRef.current.has(i.key) && i.lane !== "working");
    const at = pile.findIndex((i) => i.key === key);
    return order.find((i) => pile.indexOf(i) > at) || order[0] || null;
  };
  const passedRef = useRef(passed);
  // THE BOTTOM: the boss falls the moment nothing is left unseen - by your moves here, the chat, or the pile
  // moving on its own. Confetti every time; the points once a day (the bottom is a daily walk, not a farm).
  const [confetti, setConfetti] = useState(0);
  const win = (move, title, sub) => {
    setConfetti((n) => n + 1);
    sound.level();
    if (gameRef.current.dayBy?.[move]) { setBanner({ kind: move, title, sub }); return; }
    const r = award(gameRef.current, move);
    gameRef.current = r.state; setGame(r.state); saveGame(r.state);
    setBanner({ kind: move, title: `${title} · +${r.gained} XP`, sub });
    r.unlocked.forEach((a) => setBanner({ kind: "trophy", title: a.name, sub: a.says }));
  };
  const prevHp = useRef(null), prevGym = useRef(null);
  useEffect(() => {
    if (prevHp.current > 0 && hp === 0) win("bottom", "Inbox Boss defeated", "The bottom of the pile - everything seen, nothing left behind");
    prevHp.current = hp;
  }, [hp]);          // win() reads refs, so the count alone decides when it runs
  useEffect(() => {
    if (prevGym.current > 0 && gym.length === 0) win("gymclear", "Gym cleared", "Every one of your own tasks is done");
    prevGym.current = gym.length;
  }, [gym.length]);
  const next = async (item) => {
    const read = knowOnly(item);
    const ok = await play(read ? "read" : "next", read ? item.key : null,
      () => api.post("/api/funnel/settle", { key: item.key, verb: "surfaced", read: true }));
    if (ok == null) return;
    passedRef.current = new Set([...passedRef.current, item.key]);
    setPassed(passedRef.current);
    const n = nextAfter(item.key);
    if (!n) { toast({ kind: "quest", text: "Pile walked ✦", sub: "nothing left you haven't seen" }); go("all"); return; }
    const z = zoneItems([n]);
    go(Object.keys(z).find((k) => z[k].length), n.key);
  };
  const jumpIn = (tid, opts) => {
    if (!opened.current.has(tid)) { opened.current.add(tid); const r = award(gameRef.current, "open"); gameRef.current = r.state; setGame(r.state); saveGame(r.state); toast({ kind: "xp", text: `+${r.gained} XP`, sub: "Jumped into the code space" }); }
    onOpenTask(tid, opts);
  };
  const ask = async (text) => {
    if (!text.trim()) return;
    setChat((c) => [...c, { who: "you", text }]);
    const key = picked && byKey[picked] ? picked : null;
    // a question scores once a minute: talking to the core is how you find the move, not the move itself
    const scored = Date.now() - lastAsk.current > 60000;
    if (scored) lastAsk.current = Date.now();
    setBusy("ask");
    const data = await play(scored ? "ask" : null, null, async () => (await api.post("/api/concierge/say", { text, key })).data);
    if (!data) return;
    // the answer arrives the way the chat's does: words, the buttons that go with them, a proposal to confirm,
    // or the thing it pointed at. A reply request drafts at once, as it does in the chat (PW-126).
    const item = data.item || (key ? byKey[key] : null);
    setChat((c) => [...c, { who: "core", text: data.say || "Done.", chips: data.chips || [], options: data.options || [],
      proposal: proposalOf(data), item }]);
    if (data.decision?.verb === "reply" && item?.mid) play("draft", item.key, () => api.post(`/api/messages/${item.mid}/reply`, { draft: true, instruction: data.decision.text || null }));
  };
  const share = async () => {
    try { await navigator.clipboard.writeText(shareCard(game)); toast({ kind: "info", text: "Run copied", sub: "counts only - no names, no subjects" }); }
    catch { toast({ kind: "err", text: "Couldn't copy", sub: "your browser blocked the clipboard" }); }
  };

  if (!tasks) return <CircularProgress size={22} sx={{ m: 4 }} />;
  // what every room hands its items: the one in hand, the moves, and the roads out
  const room = { picked, setPicked, agents, busy, play, onOpenTask: jumpIn, onNavigate, onNext: next };
  const lv = levelOf(game.xp);
  const comboLeft = Math.max(0, 1 - (Date.now() - game.lastAt) / COMBO_WINDOW);
  const combo = comboLeft > 0 ? game.combo : 0;
  const seated = desks.filter(Boolean);
  const free = desks.filter((desk) => !desk).length;
  const runSecs = Math.max(0, Math.round((Date.now() - (game.runStart || Date.now())) / 1000));

  return (
    <Box sx={{ position: "relative", width: "100%", height: "calc(100vh - 84px)", minHeight: 560, overflow: "hidden",
      borderRadius: "14px", background: "radial-gradient(ellipse at 50% 40%, #f7f2e9 0%, #e7dfd1 70%, #d9d0c0 100%)" }}>
      <Box sx={{ position: "absolute", inset: 0 }}>
        <React.Suspense fallback={<Box sx={{ position: "absolute", inset: 0, display: "grid", placeItems: "center" }}><CircularProgress size={22} /></Box>}>
          <GameScene seats={sceneSeats} selectedId={pick} onSelect={(id) => { setPick(id); go("floor"); }}
            focus={focus} onZone={(z) => go(z)} npcs={npcs} cabinets={hub.topics} picked={picked} zoneCounts={zoneCounts}
            onPick={(key) => { const i = byKey[key]; if (i) { const z = zoneItems([i]); go(Object.keys(z).find((k) => z[k].length), key); } else if (key.startsWith("task:")) go("gym", key); }}
            onCabinet={(topic) => go("archive", topic)} onCore={() => go("hq")} onExit={onExit}
            inset={wide ? { left: 180, right: folded ? 0 : 344 } : { left: 0, right: 0 }} active={active} meetings={meetings} />
        </React.Suspense>
      </Box>

      {/* ── the HUD ─────────────────────────────────────────────────────────────────────────── */}
      <Box sx={{ ...glass, position: "absolute", zIndex: 8, top: 10, left: 12, right: 12, px: 1.25, py: 0.6,
        display: "flex", alignItems: "center", gap: 1.75, flexWrap: "wrap" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.1, minWidth: 210 }}>
          <Box sx={{ width: 40, height: 40, borderRadius: "50%", display: "grid", placeItems: "center", flexShrink: 0,
            background: `conic-gradient(${G.gold} ${lv.pct * 360}deg, rgba(255,255,255,.12) 0deg)` }}>
            <Box sx={{ width: 32, height: 32, borderRadius: "50%", bgcolor: "#171b21", display: "grid", placeItems: "center",
              fontWeight: 900, fontSize: 14, color: G.gold }}>{lv.level}</Box>
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography sx={{ fontSize: 10, letterSpacing: 1.4, color: G.faint, fontWeight: 800, textTransform: "uppercase" }}>Assistant game</Typography>
            <Typography noWrap sx={{ fontSize: 14, fontWeight: 800, color: G.ink }}>{lv.title}</Typography>
            <Typography sx={{ ...mono, fontSize: 10.5, color: G.dim }}>{game.xp} XP · {lv.span - lv.into} to Lv {lv.level + 1}</Typography>
          </Box>
        </Box>

        <Box sx={{ minWidth: 92, textAlign: "center" }}>
          <Typography sx={{ fontSize: 22, fontWeight: 900, lineHeight: 1, color: combo > 1 ? G.gold : G.faint,
            transform: combo > 1 ? `scale(${1 + Math.min(combo, 6) * 0.04})` : "none", transition: "transform .2s" }}>x{comboMult(Math.max(combo, 1))}</Typography>
          <Box sx={{ height: 3, mt: 0.5, borderRadius: 2, bgcolor: "rgba(255,255,255,.1)", overflow: "hidden" }}>
            <Box sx={{ height: "100%", width: `${comboLeft * 100}%`, bgcolor: G.gold, transition: "width 1s linear" }} />
          </Box>
          <Typography sx={{ fontSize: 9.5, color: G.faint, letterSpacing: 1, fontWeight: 700, mt: 0.25 }}>{combo > 1 ? `${combo} COMBO` : "COMBO"}</Typography>
        </Box>

        <Box sx={{ flex: "1 1 220px", minWidth: 180 }}>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 1 }}>
            <Typography sx={{ fontSize: 10, letterSpacing: 1.3, fontWeight: 800, color: G.red }}>INBOX BOSS</Typography>
            <Typography sx={{ ...mono, fontSize: 10.5, color: G.dim, ml: "auto" }}>{hp ? `${hp} to the bottom` : "defeated ✦ you're at the bottom"}</Typography>
          </Box>
          <Box sx={{ height: 9, mt: 0.5, borderRadius: 5, bgcolor: "rgba(255,255,255,.08)", overflow: "hidden", border: `1px solid ${G.line}` }}>
            <Box sx={{ height: "100%", width: `${(hp / hpMax.current) * 100}%`, transition: "width .6s cubic-bezier(.2,.9,.3,1.2)",
              background: hp ? "linear-gradient(90deg, #b04a5c, #e0697d)" : G.green }} />
          </Box>
        </Box>

        <Box sx={{ display: { xs: "none", xl: "flex" }, gap: 0.75 }}>
          {quests.map((q) => {
            const n = questProgress(game, q), done = game.quests?.includes(q.key);
            return (
              <Box key={q.key} title={`+${q.xp} XP when done today`} sx={{ px: 1, py: 0.5, borderRadius: "9px", bgcolor: done ? "rgba(143,207,143,.15)" : G.card,
                border: `1px solid ${done ? "rgba(143,207,143,.5)" : G.line}`, minWidth: 118 }}>
                <Typography noWrap sx={{ fontSize: 10.5, fontWeight: 700, color: done ? G.green : G.ink }}>{done ? "✓ " : ""}{q.label}</Typography>
                <Box sx={{ height: 3, mt: 0.4, borderRadius: 2, bgcolor: "rgba(255,255,255,.1)" }}>
                  <Box sx={{ height: "100%", width: `${q.n ? (n / q.n) * 100 : 100}%`, borderRadius: 2, bgcolor: done ? G.green : G.mint }} />
                </Box>
              </Box>
            );
          })}
        </Box>

        <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
          <Typography title="time since today's run started" sx={{ ...mono, fontSize: 12, color: G.dim, mr: 0.5 }}>
            ⏱ {Math.floor(runSecs / 3600) ? `${Math.floor(runSecs / 3600)}h ` : ""}{Math.floor((runSecs % 3600) / 60)}m
          </Typography>
          <HudButton onClick={() => setTrophies((v) => !v)} title="Trophies">🏆 {game.got.length}/{ACHIEVEMENTS.length}</HudButton>
          <HudButton onClick={sound.toggle} title={sound.on ? "Sound on" : "Sound off"}>{sound.on ? "🔊" : "🔇"}</HudButton>
          <HudButton onClick={share} title="Copy your run to share - counts only" gold>Share run</HudButton>
          <HudButton onClick={onExit} title="Back to the Assistant's chat - the same items, as a conversation">💬 Back to chat</HudButton>
        </Box>
      </Box>

      {/* ── the map: five spaces, and the way back out ───────────────────────────────────────── */}
      <Box sx={{ position: "absolute", zIndex: 7, left: 12, top: 84, display: "flex", flexDirection: "column", gap: 0.5, width: { xs: 54, md: 158 } }}>
        <MapButton on={focus === "all"} onClick={() => go("all")} k="Esc" name="Whole office" />
        {ZONES.map((z) => <MapButton key={z.key} on={focus === z.key} onClick={() => go(z.key)} k={z.hotkey} name={z.name} n={zoneCounts[z.key]} />)}
      </Box>

      {/* ── the space you jumped into ─────────────────────────────────────────────────────────── */}
      {/* compact on purpose: the office is the screen, this is the clipboard you carry. It folds to its title. */}
      <Box sx={{ ...glass, position: "absolute", zIndex: 7, right: 12, top: 84, width: { xs: "calc(100% - 90px)", sm: 320 },
        maxHeight: folded ? "none" : "calc(100% - 100px)", display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <Box onClick={() => setFolded((v) => !v)} title={folded ? "Open the panel" : "Fold the panel"}
          sx={{ display: "flex", alignItems: "center", gap: 1, px: 1.4, py: 0.9, cursor: "pointer", borderBottom: folded ? "none" : `1px solid ${G.line}` }}>
          <Box sx={{ ...mono, px: 0.6, borderRadius: "5px", fontSize: 10, fontWeight: 800, bgcolor: "rgba(240,192,90,.15)", color: G.gold }}>
            {focus === "all" ? "Esc" : zoneMeta(focus)?.hotkey}</Box>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography noWrap sx={{ fontSize: 13.5, fontWeight: 900 }}>{focus === "all" ? "Briefing" : zoneMeta(focus)?.name}</Typography>
            {!folded && <Typography noWrap sx={{ fontSize: 10.5, color: G.faint }}>{focus === "all" ? "who should take what" : zoneMeta(focus)?.blurb}</Typography>}
          </Box>
          <Typography sx={{ fontSize: 14, color: G.dim }}>{folded ? "▾" : "▴"}</Typography>
        </Box>
        <Box sx={{ overflowY: "auto", minHeight: 0, px: 1, py: 0.9, display: folded ? "none" : "block" }}>
          {focus === "all" && <Briefing pile={pile} agents={agents} hp={hp} passed={passed} onGo={(i) => { const z = zoneItems([i]); go(Object.keys(z).find((k) => z[k].length), i.key); }} />}
          {focus === "floor" && <FloorSpace seated={seated} queue={queue} live={live} agents={agents} clock={clock} pick={pick} setPick={setPick}
            {...room} items={zones.floor} onJump={jumpIn} cap={cap} setCap={setCap} free={free} desks={desks} />}
          {focus === "meeting" && <MeetingSpace {...room} items={zones.meeting} />}
          {focus === "gym" && <GymSpace {...room} gym={gym} reload={() => { load(); loadWorld(); }} />}
          {focus === "coffee" && <CoffeeSpace {...room} items={zones.coffee} onSettle={settle} />}
          {focus === "archive" && <ArchiveSpace {...room} ghosts={zones.archive} hub={hub} reload={loadWorld} />}
          {focus === "hq" && <CoreSpace chat={chat} onAsk={ask} {...room} pile={pile}
            onGo={(i) => { const z = zoneItems([i]); go(Object.keys(z).find((k) => z[k].length), i.key); }} />}
        </Box>
      </Box>

      {/* ── rewards ───────────────────────────────────────────────────────────────────────────── */}
      <Box sx={{ position: "absolute", zIndex: 9, top: 88, left: "50%", transform: "translateX(-50%)", display: "flex", flexDirection: "column",
        alignItems: "center", gap: 0.6, pointerEvents: "none" }}>
        {toasts.map((t) => (
          <Box key={t.id} sx={{ ...glass, px: 1.6, py: 0.8, display: "flex", alignItems: "baseline", gap: 1, animation: "sgPop .35s cubic-bezier(.2,.9,.3,1.4)",
            borderColor: t.kind === "err" ? G.red : t.kind === "quest" ? G.green : t.kind === "xp" ? G.gold : G.line,
            "@keyframes sgPop": { from: { opacity: 0, transform: "translateY(-10px) scale(.9)" }, to: { opacity: 1, transform: "none" } } }}>
            <Typography sx={{ fontWeight: 900, fontSize: t.kind === "xp" ? 18 : 14, color: t.kind === "err" ? G.red : t.kind === "quest" ? G.green : G.gold }}>{t.text}</Typography>
            <Typography sx={{ fontSize: 12, color: G.dim, maxWidth: 360 }} noWrap>{t.sub}</Typography>
          </Box>
        ))}
      </Box>
      <Confetti burst={confetti} />
      {banner && (
        <Box onClick={() => setBanner(null)} sx={{ position: "absolute", inset: 0, zIndex: 10, display: "grid", placeItems: "center", cursor: "pointer",
          background: "radial-gradient(circle, rgba(20,24,30,.35), rgba(20,24,30,0) 60%)" }}>
          <Box sx={{ ...glass, px: 5, py: 3, textAlign: "center", borderColor: G.gold, animation: "sgBoom .5s cubic-bezier(.2,.9,.3,1.5)",
            "@keyframes sgBoom": { from: { opacity: 0, transform: "scale(.6) rotate(-3deg)" }, to: { opacity: 1, transform: "none" } } }}>
            <Typography sx={{ fontSize: 11, letterSpacing: 3, color: G.gold, fontWeight: 900 }}>{banner.kind === "level" ? "LEVEL UP" : banner.kind === "bottom" ? "BOTTOM OF THE PILE" : banner.kind === "gymclear" ? "EVERY SET DONE" : "TROPHY UNLOCKED"}</Typography>
            <Typography sx={{ fontSize: 34, fontWeight: 900 }}>{banner.kind === "level" ? "⬆ " : banner.kind === "bottom" ? "⚔ " : banner.kind === "gymclear" ? "💪 " : "🏆 "}{banner.title}</Typography>
            <Typography sx={{ fontSize: 14, color: G.dim }}>{banner.sub}</Typography>
          </Box>
        </Box>
      )}
      {trophies && (
        <Box sx={{ ...glass, position: "absolute", zIndex: 9, top: 84, left: { xs: 12, md: 180 }, width: 300, maxHeight: "calc(100% - 110px)", overflowY: "auto", p: 1.5 }}>
          <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
            <Typography sx={{ fontWeight: 900, flex: 1 }}>Trophies</Typography>
            <HudButton onClick={() => setTrophies(false)}>Close</HudButton>
          </Box>
          {ACHIEVEMENTS.map((a) => {
            const got = game.got.includes(a.key);
            return (
              <Box key={a.key} sx={{ display: "flex", gap: 1, alignItems: "center", py: 0.7, opacity: got ? 1 : 0.45 }}>
                <Box sx={{ fontSize: 20, filter: got ? "none" : "grayscale(1)" }}>🏆</Box>
                <Box><Typography sx={{ fontSize: 12.5, fontWeight: 800 }}>{a.name}</Typography>
                  <Typography sx={{ fontSize: 11, color: G.dim }}>{a.says}</Typography></Box>
              </Box>
            );
          })}
          <Typography sx={{ ...mono, fontSize: 10.5, color: G.faint, mt: 1 }}>{game.moves} moves · best combo x{game.best} · {game.today} XP today</Typography>
        </Box>
      )}
    </Box>
  );
}

function HudButton({ children, onClick, title, gold }) {
  return (
    <Box component="button" type="button" onClick={onClick} title={title}
      sx={{ border: `1px solid ${gold ? G.gold : G.line}`, bgcolor: gold ? G.gold : G.card, color: gold ? "#1c1f24" : G.ink,
        borderRadius: "9px", px: 1.1, py: 0.55, fontSize: 12, fontWeight: 800, cursor: "pointer", whiteSpace: "nowrap",
        "&:hover": { filter: "brightness(1.15)" } }}>{children}</Box>
  );
}

function MapButton({ on, onClick, k, name, n }) {
  return (
    <Box component="button" type="button" onClick={onClick} title={name}
      sx={{ ...glass, display: "flex", alignItems: "center", gap: 0.8, px: 0.8, py: 0.5, cursor: "pointer", textAlign: "left", borderRadius: "10px",
        bgcolor: on ? G.gold : G.bg, color: on ? "#1c1f24" : G.ink, borderColor: on ? G.gold : G.line, transition: "transform .12s",
        "&:hover": { transform: "translateX(3px)" } }}>
      <Box sx={{ ...mono, minWidth: 26, height: 22, borderRadius: "6px", display: "grid", placeItems: "center", fontSize: 10.5, fontWeight: 800,
        bgcolor: on ? "rgba(0,0,0,.15)" : "rgba(255,255,255,.08)" }}>{k}</Box>
      <Typography noWrap sx={{ display: { xs: "none", md: "block" }, fontSize: 12, fontWeight: 800, flex: 1 }}>{name}</Typography>
      {!!n && <Box sx={{ display: { xs: "none", md: "block" }, px: 0.7, borderRadius: 99, bgcolor: "#b04a5c", color: "#fff", fontSize: 10.5, fontWeight: 800 }}>{n}</Box>}
    </Box>
  );
}

function Card({ on, onClick, children, accent }) {
  return (
    <Box onClick={onClick} sx={{ mb: 0.9, p: 1.15, borderRadius: "11px", cursor: onClick ? "pointer" : "default",
      bgcolor: on ? "rgba(240,192,90,.08)" : G.card, border: `1px solid ${on ? G.gold : G.line}`,
      borderLeft: `3px solid ${accent || (on ? G.gold : "transparent")}`, "&:hover": onClick ? { borderColor: on ? G.gold : "rgba(255,255,255,.25)" } : {} }}>
      {children}
    </Box>
  );
}

const Match = ({ item, agents }) => {
  const m = matchFor(item, agents);
  return (
    <Box sx={{ mt: 0.8, px: 1, py: 0.6, borderRadius: "8px", bgcolor: "rgba(127,209,198,.08)", border: "1px dashed rgba(127,209,198,.35)" }}>
      <Typography sx={{ fontSize: 11, color: G.mint }}>✦ Best match: <b>{m.who}</b> — {m.why}</Typography>
    </Box>
  );
};

// a room's list: one row per item; the one in hand opens into the inspector, with every move it carries
function ItemList({ items, picked, setPicked, agents, busy, play, onOpenTask, onNavigate, onNext, accent }) {
  return items.map((i) => {
    const on = picked === i.key;
    return (
      <Card key={i.key} on={on} onClick={() => setPicked(on ? null : i.key)} accent={accent?.(i) || (needsYou(i) ? G.red : null)}>
        <Who item={i} />
        <Typography sx={{ fontSize: 13, fontWeight: 700, mt: 0.3 }}>{i.title}</Typography>
        {!on && (i.preview || i.why) && <Typography noWrap sx={{ fontSize: 11.5, color: G.faint, mt: 0.2 }}>{i.preview || i.why}</Typography>}
        {on && <><Match item={i} agents={agents} />
          <ItemInspector item={i} agents={agents} busy={busy} play={play} onOpenTask={onOpenTask} onNavigate={onNavigate} onNext={onNext} /></>}
      </Card>
    );
  });
}

// the briefing reads the walk: what you have not seen yet comes first (the boss's health), then what you have
// seen that is still on you - so the bottom never looks like a to-do list that did not move
function Briefing({ pile, agents, onGo, hp, passed }) {
  const fresh = pile.filter((i) => i.lane !== "working" && !i.surfaced && !passed.has(i.key));
  const onYou = pile.filter((i) => needsYou(i) && !fresh.includes(i));
  if (!pile.length) return <Empty text="Nothing is waiting anywhere in the office. Inbox Boss defeated - go get a coffee." />;
  const row = (i, accent) => {
    const m = matchFor(i, agents);
    return (
      <Card key={i.key} onClick={() => onGo(i)} accent={accent}>
        <Who item={i} />
        <Typography sx={{ fontSize: 13, fontWeight: 700, mt: 0.3 }}>{i.title}</Typography>
        <Typography sx={{ fontSize: 11, color: G.mint, mt: 0.4 }}>✦ {m.who} · {m.why}</Typography>
      </Card>
    );
  };
  const head = (text, color) => <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1.2, color, px: 0.5, mb: 0.6, mt: 0.4 }}>{text}</Typography>;
  return <>
    {hp > 0 ? <>
      {head(`⚔ NOT SEEN YET · ${hp} TO THE BOTTOM`, G.red)}
      {fresh.slice(0, 4).map((i) => row(i, G.red))}
      {fresh.length > 4 && <Typography sx={{ fontSize: 11.5, color: G.faint, px: 0.5, mb: 1 }}>+{fresh.length - 4} more - press N on any of them to walk the lot</Typography>}
    </> : (
      <Box sx={{ mb: 1, p: 1.1, borderRadius: "11px", bgcolor: "rgba(143,207,143,.1)", border: "1px solid rgba(143,207,143,.4)" }}>
        <Typography sx={{ fontSize: 13, fontWeight: 900, color: G.green }}>⚔ You're at the bottom</Typography>
        <Typography sx={{ fontSize: 11.5, color: G.dim }}>Everything has been seen. {onYou.length ? "What is left is still yours to settle:" : "Nothing is left on you."}</Typography>
      </Box>
    )}
    {onYou.length > 0 && <>
      {hp > 0 && head(`SEEN, STILL ON YOU · ${onYou.length}`, G.gold)}
      {onYou.slice(0, 4).map((i) => row(i, G.gold))}
    </>}
  </>;
}

function FloorSpace({ seated, queue, live, agents, clock, pick, setPick, items, busy, play, onJump, onOpenTask, onNavigate, onNext, picked, setPicked, cap, setCap, free, desks }) {
  // what the floor wants from you that is not just a desk at work: a raised hand, a stopped or saved
  // session, a finished job to read, a task nobody is on - each opens into the inspector
  const seatedIds = new Set(seated.map((t) => t.TaskId));
  const calls = items.filter((i) => !(i.lane === "working" && seatedIds.has(i.tid)));
  const byTid = Object.fromEntries(items.filter((i) => i.tid).map((i) => [i.tid, i]));
  return <>
    {calls.length > 0 && <>
      <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1.2, color: G.red, px: 0.5, mb: 0.6 }}>ON THE FLOOR FOR YOU · {calls.length}</Typography>
      <ItemList items={calls} picked={picked} setPicked={setPicked} agents={agents} busy={busy} play={play} onOpenTask={onOpenTask} onNavigate={onNavigate} onNext={onNext} />
    </>}
    <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1.2, color: G.faint, px: 0.5, mb: 0.6, mt: calls.length ? 1.2 : 0 }}>AT THE DESKS · {seated.length}</Typography>
    {seated.map((task) => {
      const liveRow = live[task.TaskId];
      const state = studioTaskState(task, liveRow, agents, clock);
      const selected = pick === task.TaskId, item = byTid[task.TaskId];
      return (
        <Card key={task.TaskId} on={selected} onClick={() => setPick(selected ? null : task.TaskId)} accent={state.tone === "waiting" ? G.red : G.green}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.7 }}>
            <Typography noWrap sx={{ fontSize: 11, fontWeight: 800, color: state.tone === "waiting" ? G.red : G.green }}>{state.agent}</Typography>
            <Typography sx={{ ...mono, fontSize: 10, color: G.faint, ml: "auto" }}>{task.ref}</Typography>
            {task.Waiting > 0 && <Typography sx={{ ...mono, fontSize: 10, color: G.gold, fontWeight: 700 }}
              title={`${task.Waiting} queued prompt${task.Waiting === 1 ? "" : "s"} waiting in the funnel`}>✎ {task.Waiting}</Typography>}
          </Box>
          <Typography noWrap sx={{ fontSize: 13, fontWeight: 700, pt: 0.3 }}>{task.Title}</Typography>
          <Typography sx={{ fontSize: 11, color: G.dim, pt: 0.2 }}>{state.label}</Typography>
          {(liveRow?.work || liveRow?.promptPending) && (
            <Box sx={{ pt: 0.5, bgcolor: "#f6f2ea", borderRadius: "6px", px: 0.75, pb: 0.5, mt: 0.5 }}>
              <WorkLine work={liveRow.work} who={state.agent} waiting={liveRow.kind === "session" && isWaiting(liveRow)}
                asking={liveRow.asking} state={liveRow.state} detail={liveRow.request?.text} startedAt={liveRow.StartedAt} promptPending={liveRow.promptPending} />
            </Box>
          )}
          {liveRow?.files?.length > 0 && <Box sx={{ pt: 0.6 }}><FileChips files={liveRow.files} /></Box>}
          {selected && (item
            ? <ItemInspector item={item} agents={agents} busy={busy} play={play} onOpenTask={onOpenTask} onNavigate={onNavigate} onNext={onNext} />
            : <Box sx={{ display: "flex", gap: 0.6, mt: 0.9 }}><Btn kind="gold" onClick={() => onJump(task.TaskId)}>⌨ Jump into the code space</Btn></Box>)}
        </Card>
      );
    })}
    {!seated.length && <Empty text="The desks are quiet. New work will bring an agent to one." />}
    {queue.length > 0 && <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1.2, color: G.faint, px: 0.5, mt: 1.2, mb: 0.6 }}>WAITING FOR A DESK · {queue.length}</Typography>}
    {queue.slice(0, 6).map((task) => (
      <Card key={task.TaskId} onClick={() => onJump(task.TaskId)}>
        <Typography sx={{ ...mono, fontSize: 10.5, color: G.faint }}>{task.ref}{task.Waiting > 0 ? ` · ✎ ${task.Waiting}` : ""}</Typography>
        <Typography noWrap sx={{ fontSize: 12.5, color: G.dim }}>{task.Title}</Typography>
      </Card>
    ))}
    {queue.length > 6 && <Typography sx={{ fontSize: 11, color: G.faint, px: 0.5 }}>+{queue.length - 6} more waiting</Typography>}
    <Box sx={{ mt: 1.5, px: 0.5 }}>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 0.75 }}>
        <Typography sx={{ fontSize: 11.5, color: G.dim, flex: 1 }}>Desks (agents at once)</Typography>
        <Typography sx={{ ...mono, fontSize: 13, fontWeight: 800 }}>{cap ?? "—"}</Typography>
        <Typography sx={{ fontSize: 11, color: G.faint }}>{free} free of {desks.length}</Typography>
      </Box>
      <Slider size="small" min={1} max={8} step={1} marks value={cap ?? 4} onChange={(_, value) => setCap(value)}
        onChangeCommitted={(_, value) => api.patch("/api/settings", { name: "auto_sessions", value: String(value) }).catch(() => {})}
        sx={{ mt: 0.25, color: G.gold }} />
    </Box>
  </>;
}

// the checklist rides on every task row (store.list_tasks selects t.*), so a station draws its reps for free
const rowChecklist = (t) => {
  try { const a = JSON.parse(t?.Checklist || "[]"); return Array.isArray(a) ? a.filter((i) => i && i.text) : []; }
  catch { return []; }
};

// the meeting room, split the way the people reached you: coming up, mail, chat, and the tools that pinged
function MeetingSpace({ items, ...room }) {
  if (!items.length) return <Empty text="The meeting room is empty. Nobody is waiting on you." />;
  const groups = [
    ["📅 COMING UP", items.filter((i) => i.kind === "meeting" || i.lane === "time"), "#7fd1c6"],
    ["✉ EMAIL · AT THE TABLE", items.filter((i) => i.kind !== "meeting" && i.lane !== "time" && channelKind(i) === "email"), "#f0c05a"],
    ["💬 CHAT · IN THE HUDDLE", items.filter((i) => i.kind !== "meeting" && i.lane !== "time" && channelKind(i) === "chat"), "#b9c3ff"],
    ["🔧 FROM YOUR TOOLS", items.filter((i) => i.kind !== "meeting" && i.lane !== "time" && channelKind(i) === "tool"), "#aeb6bf"],
  ].filter(([, list]) => list.length);
  return groups.map(([label, list, color], n) => (
    <Box key={label} sx={{ mt: n ? 1.2 : 0 }}>
      <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1.2, color, px: 0.5, mb: 0.6 }}>{label} · {list.length}</Typography>
      <ItemList {...room} items={list} />
    </Box>
  ));
}

// THE GYM: your own tasks as stations. Each checklist box is a rep, the last one (or Finish) is the set.
function GymSpace({ gym, picked, setPicked, busy, play, reload, onOpenTask, onNext, ...room }) {
  if (!gym.length) return <Empty text="No tasks of your own. Rest day." />;
  const tick = (t, c) => play(c.done ? null : "rep", null, async () => {
    const { data } = await api.patch(`/api/tasks/${t.TaskId}/checklist/${c.id}`, { done: !c.done });
    // the last tick closes the task (server: tick_checklist) - that is the set, scored on its own
    if (data?.closed) await play("set", null, async () => true);
    reload();
    return data;
  });
  const finish = (g) => play("set", g.item?.key || null, async () => { const out = await runOperation(api, "task.complete", g.task.TaskId); reload(); return out || true; });
  return gym.map((g) => {
    const on = picked === g.key, list = rowChecklist(g.task), done = list.filter((c) => c.done).length;
    const title = g.task?.Title || g.item?.title, ref = g.task?.ref || g.item?.ref;
    return (
      <Card key={g.key} on={on} onClick={() => setPicked(on ? null : g.key)} accent={g.item && needsYou(g.item) ? G.red : G.gold}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.7 }}>
          <Typography sx={{ fontSize: 11, fontWeight: 800, color: G.gold }}>🏋 {ref}</Typography>
          {list.length > 0 && <Typography sx={{ ...mono, fontSize: 10.5, color: G.dim, ml: "auto" }}>{done}/{list.length} reps</Typography>}
        </Box>
        <Typography sx={{ fontSize: 13, fontWeight: 700, mt: 0.3 }}>{title}</Typography>
        {list.length > 0 && (
          <Box sx={{ height: 5, mt: 0.6, borderRadius: 3, bgcolor: "rgba(255,255,255,.08)", overflow: "hidden" }}>
            <Box sx={{ height: "100%", width: `${(done / list.length) * 100}%`, bgcolor: done === list.length ? G.green : G.gold, transition: "width .4s" }} />
          </Box>
        )}
        {on && <Box onClick={(e) => e.stopPropagation()}>
          {g.task?.Summary && <Typography sx={{ fontSize: 12, color: G.dim, mt: 0.7, whiteSpace: "pre-wrap" }}>{g.task.Summary}</Typography>}
          {list.length > 0 && <Box sx={{ mt: 0.8 }}>
            {list.map((c) => (
              <Box key={c.id || c.text} component="button" type="button" disabled={!!busy || !c.id} onClick={() => tick(g.task, c)}
                sx={{ display: "flex", alignItems: "center", gap: 0.8, width: "100%", textAlign: "left", border: 0, bgcolor: "transparent", color: G.ink,
                  px: 0.4, py: 0.45, borderRadius: "6px", cursor: "pointer", "&:hover": { bgcolor: G.card } }}>
                <Box sx={{ width: 16, height: 16, borderRadius: "4px", flexShrink: 0, display: "grid", placeItems: "center", fontSize: 11, fontWeight: 900,
                  border: `2px solid ${c.done ? G.green : G.faint}`, bgcolor: c.done ? G.green : "transparent", color: "#1c1f24" }}>{c.done ? "✓" : ""}</Box>
                <Typography sx={{ fontSize: 12.5, color: c.done ? G.faint : G.ink, textDecoration: c.done ? "line-through" : "none", flex: 1 }}>{c.text}</Typography>
                {!c.done && <Typography sx={{ fontSize: 10.5, color: G.gold, fontWeight: 800 }}>+5</Typography>}
              </Box>
            ))}
          </Box>}
          {g.item && <ItemInspector item={g.item} agents={room.agents} busy={busy} play={play} onOpenTask={onOpenTask} onNavigate={room.onNavigate} onNext={onNext} />}
          <Box sx={{ display: "flex", gap: 0.5, mt: 0.9, flexWrap: "wrap" }}>
            {g.task && <Btn kind="gold" disabled={!!busy} onClick={() => finish(g)} title="Closes the task - every box on it is ticked">🏁 Finish the set · +30</Btn>}
            {(g.task || g.item?.tid) && <Btn onClick={() => onOpenTask((g.task || g.item).TaskId || g.item.tid)}>Open {ref}</Btn>}
          </Box>
        </Box>}
      </Card>
    );
  });
}

function CoffeeSpace({ items, onSettle, ...room }) {
  if (!items.length) return <Empty text="The pot is empty and so is the room. Nothing to catch up on." />;
  // THE WHOLE POT, the count the room's badge shows: what is only there to be known is read away (done), and a
  // broken connection or a failed report is put down the way Next puts it down (read, back if the error changes) -
  // never marked done, because nothing fixed it
  const knowOnly = (i) => (i.lane === "fyi" || i.lane === "report" || i.kind === "fyis") && !i.bad;
  const drain = async () => {
    for (const i of items) {
      if (knowOnly(i)) await onSettle(i, "done", "read");
      else await room.play("next", i.key, () => api.post("/api/funnel/settle", { key: i.key, verb: "surfaced", read: true }));
    }
  };
  const broken = items.filter((i) => !knowOnly(i)).length;
  return <>
    {items.length > 1 && <Box sx={{ mb: 1 }}><Btn kind="mint" disabled={!!room.busy} onClick={drain}
      title={broken ? `${broken} broken - set aside until its error changes, never marked fixed` : undefined}>☕ Drain the pot - all {items.length}</Btn></Box>}
    <ItemList {...room} items={items} accent={(i) => i.lane === "broken" || i.bad ? G.red : G.mint} />
  </>;
}

function ArchiveSpace({ ghosts, hub, picked, setPicked, busy, play, reload, ...room }) {
  const [files, setFiles] = useState(null);
  const [form, setForm] = useState(null);
  const pulled = useRef(new Set()), voted = useRef(new Set());
  const topic = hub.topics.find((t) => t.Topic === picked)?.Topic || null;
  useEffect(() => {
    if (!topic) { setFiles(null); return; }
    api.get("/api/hub", { params: { topic } }).then(({ data }) => setFiles(data.data || []))
      .catch(() => setFiles(hub.data.filter((d) => d.Topic === topic)));
  }, [topic, hub.data]);
  const pull = (f) => { if (pulled.current.has(f.LoreId)) return; pulled.current.add(f.LoreId); play("pull", null, async () => true); };
  const vote = (f) => { if (voted.current.has(f.LoreId)) return; voted.current.add(f.LoreId); play("vote", null, () => api.post(`/api/hub/${f.LoreId}/vote?up=true`)); };
  const file = async () => {
    const ok = await play("file", null, () => api.post("/api/hub", { title: form.title.trim(), body: form.body.trim(), topic: form.topic.trim(), kind: "new_idea" }));
    if (ok) { setForm(null); reload(); }
  };
  const input = { width: "100%", boxSizing: "border-box", bgcolor: "rgba(0,0,0,.25)", color: G.ink, border: `1px solid ${G.line}`, borderRadius: "8px",
    p: 0.9, fontSize: 12.5, fontFamily: "inherit", mb: 0.6 };
  return <>
    {ghosts.length > 0 && <>
      <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1.2, color: "#b9c3ff", px: 0.5, mb: 0.6 }}>👻 GHOSTS · THREADS THAT SLIPPED · {ghosts.length}</Typography>
      <ItemList {...room} items={ghosts} picked={picked} setPicked={setPicked} busy={busy} play={play} accent={() => "#b9c3ff"} />
    </>}
    <Box sx={{ display: "flex", alignItems: "center", px: 0.5, mt: ghosts.length ? 1.4 : 0, mb: 0.6 }}>
      <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1.2, color: G.faint, flex: 1 }}>🗄 FILING CABINETS · THE HUB · {hub.topics.length}</Typography>
      <Btn kind="mint" onClick={() => setForm({ title: "", body: "", topic: topic || "" })}>+ File a lesson</Btn>
    </Box>
    {form && (
      <Card on>
        <Box component="input" placeholder="What did we learn? (title)" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} sx={input} />
        <Box component="textarea" rows={4} placeholder="The lesson, so the next person (or agent) doesn't relearn it" value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} sx={input} />
        <Box component="input" placeholder="cabinet (topic)" value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} sx={input} />
        <Box sx={{ display: "flex", gap: 0.6 }}>
          <Btn kind="gold" disabled={!!busy || !form.title.trim() || !form.body.trim() || !form.topic.trim()} onClick={file}>🗂 File it · +25</Btn>
          <Btn onClick={() => setForm(null)}>Cancel</Btn>
        </Box>
      </Card>
    )}
    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.6, mb: 1 }}>
      {hub.topics.map((t) => (
        <Box key={t.Topic} component="button" type="button" onClick={() => setPicked(t.Topic === picked ? null : t.Topic)}
          sx={{ ...mono, border: `1px solid ${t.Topic === picked ? G.gold : G.line}`, bgcolor: t.Topic === picked ? "rgba(240,192,90,.12)" : G.card,
            color: G.ink, borderRadius: "8px", px: 1, py: 0.5, fontSize: 11.5, cursor: "pointer" }}>🗄 {t.Topic} <span style={{ color: G.faint }}>{t.n}</span></Box>
      ))}
      {!hub.topics.length && <Empty text="The cabinets are empty. File the first lesson." />}
    </Box>
    {topic && (files || []).map((f) => (
      <Card key={f.LoreId} onClick={() => pull(f)}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 0.6 }}>
          <Typography sx={{ fontSize: 10.5, fontWeight: 800, color: G.dim }}>{f.Author}</Typography>
          <Typography sx={{ ...mono, fontSize: 10, color: G.faint, ml: "auto" }}>▲ {f.Score + (voted.current.has(f.LoreId) ? 1 : 0)}</Typography>
        </Box>
        <Typography sx={{ fontSize: 13, fontWeight: 700, mt: 0.3 }}>{f.Title}</Typography>
        <Typography sx={{ fontSize: 12, color: G.dim, mt: 0.4 }}>{f.Body}</Typography>
        <Box sx={{ mt: 0.7 }}>
          <Btn disabled={voted.current.has(f.LoreId) || !!busy} onClick={() => vote(f)}>👍 Useful · +10</Btn>
        </Box>
      </Card>
    ))}
  </>;
}

function CoreSpace({ chat, onAsk, busy, play, pile, agents, picked, onGo }) {
  const [text, setText] = useState("");
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [chat.length]);
  const send = (t) => { onAsk(t); setText(""); };
  const board = pile.filter((i) => needsYou(i) || i.kind === "agent").slice(0, 5);
  const inHand = pile.find((i) => i.key === picked);
  return <>
    <Box sx={{ mb: 1 }}>
      {chat.map((m, n) => (
        <Box key={n} sx={{ display: "flex", flexDirection: "column", alignItems: m.who === "you" ? "flex-end" : "flex-start", mb: 0.6 }}>
          <Box sx={{ maxWidth: "88%", px: 1.1, py: 0.7, borderRadius: m.who === "you" ? "11px 11px 2px 11px" : "11px 11px 11px 2px",
            bgcolor: m.who === "you" ? G.gold : "rgba(127,209,198,.12)", color: m.who === "you" ? "#1c1f24" : G.ink,
            border: m.who === "you" ? "none" : "1px solid rgba(127,209,198,.3)" }}>
            <Typography sx={{ fontSize: 12.5, whiteSpace: "pre-wrap" }}>{m.text}</Typography>
          </Box>
          {/* what came with the answer - the thing it pointed at, its choices, and the buttons for it, all live */}
          {m.who === "core" && n === chat.length - 1 && <Box sx={{ maxWidth: "94%", width: "100%" }}>
            {m.item && <Box sx={{ mt: 0.5 }}><Btn kind="mint" onClick={() => onGo(m.item)}>Go to it → {m.item.title}</Btn></Box>}
            {!!m.options?.length && <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mt: 0.5 }}>
              {m.options.map((o) => <Btn key={o} disabled={!!busy} onClick={() => send(o)}>{o}</Btn>)}</Box>}
            {(!!m.chips?.length || m.proposal) && m.item?.key && (
              <Moves item={m.item} given={m.chips} initial={m.proposal} busy={busy} play={play} />
            )}
          </Box>}
        </Box>
      ))}
      {busy === "busy" && <Typography sx={{ fontSize: 11.5, color: G.mint, px: 0.5 }}>✦ thinking…</Typography>}
      <div ref={end} />
    </Box>
    {inHand && <Typography sx={{ fontSize: 11, color: G.faint, mb: 0.5 }}>Asking about: <b style={{ color: G.dim }}>{inHand.title}</b></Typography>}
    <Box sx={{ display: "flex", gap: 0.5, flexWrap: "wrap", mb: 0.8 }}>
      {["What should I do next?", "Who should take the top thing?", "What's slipping?"].map((q) =>
        <Btn key={q} disabled={!!busy} onClick={() => send(q)}>{q}</Btn>)}
    </Box>
    <Box component="form" onSubmit={(e) => { e.preventDefault(); if (text.trim()) send(text); }} sx={{ display: "flex", gap: 0.6, mb: 1.5 }}>
      <Box component="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask the core…"
        sx={{ flex: 1, bgcolor: "rgba(0,0,0,.25)", color: G.ink, border: `1px solid ${G.line}`, borderRadius: "9px", px: 1, py: 0.7, fontSize: 12.5, fontFamily: "inherit" }} />
      <Btn kind="mint" disabled={!!busy || !text.trim()} onClick={() => send(text)}>Ask</Btn>
    </Box>
    <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1.2, color: G.faint, px: 0.5, mb: 0.6 }}>✦ MATCHMAKER · WHO SHOULD TAKE WHAT</Typography>
    {board.map((i) => {
      const m = matchFor(i, agents);
      return (
        <Card key={i.key} onClick={() => onGo(i)}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 0.8 }}>
            <Typography noWrap sx={{ fontSize: 12.5, fontWeight: 700, flex: 1 }}>{i.title}</Typography>
            <Typography sx={{ fontSize: 11, fontWeight: 800, color: m.who === "you" ? G.gold : G.mint, whiteSpace: "nowrap" }}>→ {m.who}</Typography>
          </Box>
          <Typography sx={{ fontSize: 11, color: G.faint }}>{i.who} · {m.why}</Typography>
        </Card>
      );
    })}
    {!board.length && <Empty text="Nothing to match. Everyone has what they need." />}
  </>;
}

// CONFETTI, when the boss falls: a canvas over the game that pours for a few seconds, then clears itself.
// Nothing at all under reduced motion - the banner still says it.
function Confetti({ burst }) {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!burst || !canvas || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return undefined;
    const ctx = canvas.getContext("2d"), dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = canvas.clientWidth, h = canvas.clientHeight;
    canvas.width = w * dpr; canvas.height = h * dpr; ctx.scale(dpr, dpr);
    const colors = [G.gold, G.mint, G.red, "#b9c3ff", G.green, "#ffffff"];
    // speeds are per second, so a slow machine pours the same shower in the same time, just in fewer frames
    const bits = Array.from({ length: 280 }, () => ({ x: Math.random() * w, y: -10 - Math.random() * h * 0.35, vx: (Math.random() - 0.5) * 120,
      vy: 160 + Math.random() * 260, r: Math.random() * Math.PI, vr: (Math.random() - 0.5) * 12, s: 6 + Math.random() * 8,
      c: colors[Math.floor(Math.random() * colors.length)], round: Math.random() < 0.25 }));
    const t0 = performance.now();
    let raf = 0, last = t0;
    const frame = (now) => {
      const age = (now - t0) / 1000, dt = Math.min(0.1, (now - last) / 1000);
      last = now;
      ctx.clearRect(0, 0, w, h);
      ctx.globalAlpha = Math.max(0, Math.min(1, 4.2 - age));
      for (const b of bits) {
        b.x += (b.vx + Math.sin(now / 400 + b.r) * 40) * dt; b.y += b.vy * dt; b.r += b.vr * dt;
        ctx.save(); ctx.translate(b.x, b.y); ctx.rotate(b.r); ctx.fillStyle = b.c;
        if (b.round) { ctx.beginPath(); ctx.arc(0, 0, b.s / 2.5, 0, Math.PI * 2); ctx.fill(); } else ctx.fillRect(-b.s / 2, -b.s / 4, b.s, b.s / 2);
        ctx.restore();
      }
      if (age < 4.2) raf = requestAnimationFrame(frame); else ctx.clearRect(0, 0, w, h);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [burst]);
  return <Box component="canvas" ref={ref} sx={{ position: "absolute", inset: 0, width: "100%", height: "100%", zIndex: 11, pointerEvents: "none" }} />;
}

const Empty = ({ text }) => <Typography sx={{ fontSize: 12, color: G.faint, px: 0.75, py: 1, lineHeight: 1.55 }}>{text}</Typography>;
