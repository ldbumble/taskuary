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
import {
  ZONES, zoneMeta, zoneItems, needsYou, bossHp, matchFor, award, levelOf, loadGame, saveGame, shareCard,
  MOVE_WORDS, ACHIEVEMENTS, QUESTS, questProgress, COMBO_WINDOW, comboMult,
} from "./assistantGame.js";

const GameScene = React.lazy(() => import("./GameScene.jsx"));

// the game wears its own dark glass over the warm room - the one screen in the app that is meant to be loud
const G = { bg: "rgba(20,24,30,.9)", line: "rgba(255,255,255,.1)", ink: "#f3f1ec", dim: "#aeb6bf", faint: "#7c8590",
  gold: "#f0c05a", mint: "#7fd1c6", red: "#e0697d", green: "#8fcf8f", card: "rgba(255,255,255,.05)" };
const glass = { bgcolor: G.bg, color: G.ink, border: `1px solid ${G.line}`, borderRadius: "14px",
  boxShadow: "0 18px 50px rgba(10,14,20,.35)", backdropFilter: "blur(10px)" };
const errText = (e) => e?.response?.data?.detail || e?.message || "that did not go through";

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

export default function AssistantGame({ onOpenTask, onExit, active = true }) {
  const [tasks, setTasks] = useState(null);
  const [agents, setAgents] = useState([]);
  const [cap, setCap] = useState(null);
  const [live, setLive] = useState({});
  const [pick, setPick] = useState(null);
  const [clock, setClock] = useState(Date.now());
  const [pile, setPile] = useState([]);
  const [hub, setHub] = useState({ topics: [], data: [] });
  const [reviews, setReviews] = useState({});
  const [focus, setFocus] = useState("all");
  const [picked, setPicked] = useState(null);     // the lobby/coffee/archive item or cabinet topic in hand
  const [game, setGame] = useState(() => loadGame());
  const [toasts, setToasts] = useState([]);
  const [banner, setBanner] = useState(null);     // a level-up or trophy, big and brief
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
    setTasks((taskResponse.data.data || []).filter((task) => task.Status !== "dropped" && isAgentKind(task.Kind)));
    setAgents(agentResponse.data.data || agentResponse.data.agents || []);
    const row = (settingResponse.data.data || []).find((setting) => setting.Name === "auto_sessions");
    setCap((current) => current == null ? Math.max(1, Math.min(8, parseInt(row?.Value, 10) || 4)) : current);
  }, []);
  // the rest of the office: the assistant's pile (people, fyi's, ghosts), the Hub's cabinets, and the drafts behind "reply ready"
  const loadWorld = useCallback(async () => {
    const [p, h, r] = await Promise.all([
      api.get("/api/funnel/pile").catch(() => null),
      api.get("/api/hub").catch(() => null),
      api.get("/api/reviews").catch(() => null),
    ]);
    if (p) setPile(p.data?.items || []);
    if (h) setHub({ topics: h.data?.topics || [], data: h.data?.data || [] });
    if (r) setReviews(Object.fromEntries((r.data?.data || []).map((v) => [v.ReviewId, v])));
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
  const zones = useMemo(() => zoneItems(pile), [pile]);
  const npcs = useMemo(() => ["lobby", "coffee", "archive"].flatMap((zone) => zones[zone].map((i) => ({
    key: i.key, zone, who: i.who || laneMeta(i.lane).word, title: i.title, mark: markOf(i),
  }))), [zones]);
  const zoneCounts = useMemo(() => ({
    floor: zones.floor.filter(needsYou).length, lobby: zones.lobby.filter(needsYou).length,
    coffee: zones.coffee.length, archive: zones.archive.length, hq: 0,
  }), [zones]);
  const byKey = useMemo(() => Object.fromEntries(pile.map((i) => [i.key, i])), [pile]);
  const hp = bossHp(pile), hpMax = useRef(1);
  hpMax.current = Math.max(hpMax.current, hp, 1);

  useEffect(() => {
    if (pick && !desks.some((task) => task?.TaskId === pick)) setPick(null);
  }, [desks, pick]);

  // keys: 1-5 jump into a space, Esc walks back out. Never while you are typing.
  useEffect(() => {
    if (!active) return undefined;
    const onKey = (e) => {
      if (e.target?.closest?.("input, textarea, [contenteditable=true]") || e.metaKey || e.ctrlKey || e.altKey) return;
      const z = ZONES.find((x) => x.hotkey === e.key);
      if (z) { e.preventDefault(); go(z.key); }
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
    setBusy(key || move || "ask");
    try {
      const out = await run();
      const left = key ? pileRef.current.filter((i) => i.key !== key || move === "draft") : pileRef.current;
      pileRef.current = left;
      const world = { lobby: zoneItems(left).lobby.filter(needsYou).length, coffee: zoneItems(left).coffee.length };
      if (!move) { if (key) setPile(left); return out; }       // a move that does not score (a second question inside a minute)
      const r = award(gameRef.current, move, Date.now(), world);
      gameRef.current = r.state; setGame(r.state); saveGame(r.state);
      if (r.gained > 0) { sound.coin(); toast({ kind: "xp", text: `+${r.gained} XP`, sub: `${MOVE_WORDS[move]}${r.mult > 1 ? ` · combo x${r.mult}` : ""}` }); }
      r.quests.forEach((q) => toast({ kind: "quest", text: `Quest done +${q.xp}`, sub: q.says, ms: 3600 }));
      r.unlocked.forEach((a, i) => setTimeout(() => { sound.level(); setBanner({ kind: "trophy", title: a.name, sub: a.says }); }, 500 + i * 1800));
      if (r.levelUp) setTimeout(() => { sound.level(); setBanner({ kind: "level", title: `Level ${r.levelUp.level}`, sub: r.levelUp.title }); }, 300);
      if (key) setPile(left);
      setPicked((p) => p === key && move !== "draft" ? null : p);
      loadWorld(); load();
      return out;
    } catch (e) { sound.nope(); toast({ kind: "err", text: "Didn't land", sub: errText(e), ms: 4200 }); return null; }
    finally { setBusy(""); }
  };
  useEffect(() => { if (!banner) return undefined; const t = setTimeout(() => setBanner(null), 2600); return () => clearTimeout(t); }, [banner]);

  const settle = (item, verb, move) => play(move, item.key, () => api.post("/api/funnel/settle", { key: item.key, verb }));
  const draft = (item) => play("draft", item.key, () => api.post(`/api/messages/${item.mid}/reply`, { draft: true, instruction: null }));
  const approve = (item, text) => play("approve", item.key, () => api.post(`/api/reviews/${item.rid}/decide`, { verb: "approve", final_text: text, note: null }));
  const dispatch = (item, kind) => play("dispatch", item.key, async () => {
    const { data } = await api.post(`/api/messages/${item.mid}/dispatch`, { kind });
    if (data?.dispatch === "needs_repo") { toast({ kind: "info", text: "Pick a checkout", sub: `${data.ref || "the task"} needs to know which repository`, ms: 4200 }); if (data.taskId) onOpenTask(data.taskId); }
    else toast({ kind: "info", text: `${data?.ref || "It"} → ${data?.agent || kind === "coding" ? "the coder" : "an agent"}`, sub: "you'll hear when it's done" });
    return data;
  });
  const answer = (item, text) => play("answer", item.key, () => api.post(`/api/tasks/${item.tid}/worker/answer`, { request_id: item.request_id, text }));
  const ghost = (item, verb) => play(verb === "followup" ? "followup" : "rest", item.key, () => api.post("/api/concierge/act", { key: item.key, verb }));
  const jumpIn = (tid) => {
    if (!opened.current.has(tid)) { opened.current.add(tid); const r = award(gameRef.current, "open"); gameRef.current = r.state; setGame(r.state); saveGame(r.state); toast({ kind: "xp", text: `+${r.gained} XP`, sub: "Jumped into the code space" }); }
    onOpenTask(tid);
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
    if (data) setChat((c) => [...c, { who: "core", text: data.say || "Done." }]);
  };
  const share = async () => {
    try { await navigator.clipboard.writeText(shareCard(game)); toast({ kind: "info", text: "Run copied", sub: "counts only - no names, no subjects" }); }
    catch { toast({ kind: "err", text: "Couldn't copy", sub: "your browser blocked the clipboard" }); }
  };

  if (!tasks) return <CircularProgress size={22} sx={{ m: 4 }} />;
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
            onPick={(key) => { const i = byKey[key]; if (i) { const z = zoneItems([i]); go(Object.keys(z).find((k) => z[k].length), key); } }}
            onCabinet={(topic) => go("archive", topic)} onCore={() => go("hq")}
            inset={wide ? { left: 180, right: folded ? 0 : 344 } : { left: 0, right: 0 }} active={active} />
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
            <Typography sx={{ ...mono, fontSize: 10.5, color: G.dim, ml: "auto" }}>{hp ? `${hp} waiting on you` : "defeated ✦"}</Typography>
          </Box>
          <Box sx={{ height: 9, mt: 0.5, borderRadius: 5, bgcolor: "rgba(255,255,255,.08)", overflow: "hidden", border: `1px solid ${G.line}` }}>
            <Box sx={{ height: "100%", width: `${(hp / hpMax.current) * 100}%`, transition: "width .6s cubic-bezier(.2,.9,.3,1.2)",
              background: hp ? "linear-gradient(90deg, #b04a5c, #e0697d)" : G.green }} />
          </Box>
        </Box>

        <Box sx={{ display: { xs: "none", xl: "flex" }, gap: 0.75 }}>
          {QUESTS.map((q) => {
            const n = questProgress(game, q), done = game.quests?.includes(q.key);
            return (
              <Box key={q.key} title={`+${q.xp} XP when done today`} sx={{ px: 1, py: 0.5, borderRadius: "9px", bgcolor: done ? "rgba(143,207,143,.15)" : G.card,
                border: `1px solid ${done ? "rgba(143,207,143,.5)" : G.line}`, minWidth: 118 }}>
                <Typography noWrap sx={{ fontSize: 10.5, fontWeight: 700, color: done ? G.green : G.ink }}>{done ? "✓ " : ""}{q.says}</Typography>
                <Box sx={{ height: 3, mt: 0.4, borderRadius: 2, bgcolor: "rgba(255,255,255,.1)" }}>
                  <Box sx={{ height: "100%", width: `${(n / q.n) * 100}%`, borderRadius: 2, bgcolor: done ? G.green : G.mint }} />
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
          {focus === "all" && <Briefing pile={pile} agents={agents} onGo={(i) => { const z = zoneItems([i]); go(Object.keys(z).find((k) => z[k].length), i.key); }} />}
          {focus === "floor" && <FloorSpace seated={seated} queue={queue} live={live} agents={agents} clock={clock} pick={pick} setPick={setPick}
            items={zones.floor} busy={busy} onAnswer={answer} onJump={jumpIn} cap={cap} setCap={setCap} free={free} desks={desks} />}
          {focus === "lobby" && <PeopleSpace items={zones.lobby} picked={picked} setPicked={setPicked} agents={agents} reviews={reviews} busy={busy}
            onDraft={draft} onApprove={approve} onDispatch={dispatch} onSettle={settle} onOpenTask={jumpIn} />}
          {focus === "coffee" && <CoffeeSpace items={zones.coffee} picked={picked} setPicked={setPicked} busy={busy} onSettle={settle} />}
          {focus === "archive" && <ArchiveSpace ghosts={zones.archive} hub={hub} picked={picked} setPicked={setPicked} busy={busy} onGhost={ghost}
            play={play} reload={loadWorld} />}
          {focus === "hq" && <CoreSpace chat={chat} onAsk={ask} busy={busy} pile={pile} agents={agents} picked={picked && byKey[picked]}
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
      {banner && (
        <Box onClick={() => setBanner(null)} sx={{ position: "absolute", inset: 0, zIndex: 10, display: "grid", placeItems: "center", cursor: "pointer",
          background: "radial-gradient(circle, rgba(20,24,30,.35), rgba(20,24,30,0) 60%)" }}>
          <Box sx={{ ...glass, px: 5, py: 3, textAlign: "center", borderColor: G.gold, animation: "sgBoom .5s cubic-bezier(.2,.9,.3,1.5)",
            "@keyframes sgBoom": { from: { opacity: 0, transform: "scale(.6) rotate(-3deg)" }, to: { opacity: 1, transform: "none" } } }}>
            <Typography sx={{ fontSize: 11, letterSpacing: 3, color: G.gold, fontWeight: 900 }}>{banner.kind === "level" ? "LEVEL UP" : "TROPHY UNLOCKED"}</Typography>
            <Typography sx={{ fontSize: 34, fontWeight: 900 }}>{banner.kind === "level" ? "⬆ " : "🏆 "}{banner.title}</Typography>
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

function Btn({ children, onClick, disabled, kind = "ghost", title }) {
  const bg = { gold: G.gold, mint: G.mint, ghost: G.card, red: "rgba(224,105,125,.15)" }[kind];
  return (
    <Box component="button" type="button" onClick={onClick} disabled={disabled} title={title}
      sx={{ border: `1px solid ${kind === "ghost" ? G.line : "transparent"}`, bgcolor: bg, color: kind === "gold" || kind === "mint" ? "#1c1f24" : G.ink,
        borderRadius: "9px", px: 1.2, py: 0.6, fontSize: 12, fontWeight: 800, cursor: disabled ? "default" : "pointer", opacity: disabled ? 0.5 : 1,
        "&:hover": { filter: disabled ? "none" : "brightness(1.12)" } }}>{children}</Box>
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

const Who = ({ item }) => (
  <Box sx={{ display: "flex", alignItems: "center", gap: 0.7 }}>
    <Typography noWrap sx={{ fontSize: 11, fontWeight: 800, color: G.dim }}>{item.who || "—"}</Typography>
    <Typography sx={{ fontSize: 10, color: G.faint }}>· {item.channel}</Typography>
    <Typography sx={{ fontSize: 10, fontWeight: 800, color: needsYou(item) ? G.red : G.faint, ml: "auto", letterSpacing: 0.5 }}>{laneMeta(item.lane).word}</Typography>
  </Box>
);

const Match = ({ item, agents }) => {
  const m = matchFor(item, agents);
  return (
    <Box sx={{ mt: 0.8, px: 1, py: 0.6, borderRadius: "8px", bgcolor: "rgba(127,209,198,.08)", border: "1px dashed rgba(127,209,198,.35)" }}>
      <Typography sx={{ fontSize: 11, color: G.mint }}>✦ Best match: <b>{m.who}</b> — {m.why}</Typography>
    </Box>
  );
};

function Briefing({ pile, agents, onGo }) {
  const top = pile.filter(needsYou).slice(0, 4);
  const rest = pile.length - top.length;
  if (!pile.length) return <Empty text="Nothing is waiting anywhere in the office. Inbox Boss defeated - go get a coffee." />;
  return <>
    {top.map((i) => {
      const m = matchFor(i, agents);
      return (
        <Card key={i.key} onClick={() => onGo(i)} accent={G.red}>
          <Who item={i} />
          <Typography sx={{ fontSize: 13, fontWeight: 700, mt: 0.3 }}>{i.title}</Typography>
          <Typography sx={{ fontSize: 11, color: G.mint, mt: 0.4 }}>✦ {m.who} · {m.why}</Typography>
        </Card>
      );
    })}
    {rest > 0 && <Typography sx={{ fontSize: 11.5, color: G.faint, px: 0.5 }}>+{rest} more around the office that don't need you - fyi's in the coffee room, agents at work.</Typography>}
  </>;
}

function FloorSpace({ seated, queue, live, agents, clock, pick, setPick, items, busy, onAnswer, onJump, cap, setCap, free, desks }) {
  const blocked = Object.fromEntries(items.filter((i) => i.lane === "blocked" && i.tid).map((i) => [i.tid, i]));
  return <>
    {seated.map((task) => {
      const liveRow = live[task.TaskId];
      const state = studioTaskState(task, liveRow, agents, clock);
      const selected = pick === task.TaskId, ask = blocked[task.TaskId];
      return (
        <Card key={task.TaskId} on={selected} onClick={() => setPick(task.TaskId)} accent={state.tone === "waiting" ? G.red : G.green}>
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
          {selected && ask && (
            <Box sx={{ mt: 0.9 }}>
              <Typography sx={{ fontSize: 12, color: G.gold, fontWeight: 700 }}>✋ {ask.preview || ask.why}</Typography>
              {!!ask.request_id && (ask.choices || []).length > 0 && (
                <Box sx={{ display: "flex", flexDirection: "column", gap: 0.5, mt: 0.6 }}>
                  {ask.choices.map((c) => <Btn key={c} kind="mint" disabled={!!busy} onClick={(e) => { e.stopPropagation(); onAnswer(ask, c); }}>{c} · +60</Btn>)}
                </Box>
              )}
            </Box>
          )}
          {selected && (
            <Box sx={{ display: "flex", gap: 0.6, mt: 0.9 }}>
              <Btn kind="gold" onClick={(e) => { e.stopPropagation(); onJump(task.TaskId); }}>⌨ Jump into the code space</Btn>
            </Box>
          )}
        </Card>
      );
    })}
    {!seated.length && <Empty text="The floor is quiet. New work will bring an agent to a desk." />}
    {queue.length > 0 && <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1.2, color: G.faint, px: 0.5, mt: 1.2, mb: 0.6 }}>WAITING FOR A DESK · {queue.length}</Typography>}
    {queue.slice(0, 6).map((task) => (
      <Card key={task.TaskId} onClick={() => onJump(task.TaskId)}>
        <Typography sx={{ ...mono, fontSize: 10.5, color: G.faint }}>{task.ref}{task.Waiting > 0 ? ` · ✎ ${task.Waiting}` : ""}</Typography>
        <Typography noWrap sx={{ fontSize: 12.5, color: G.dim }}>{task.Title}</Typography>
      </Card>
    ))}
    {queue.length > 6 && <Typography sx={{ fontSize: 11, color: G.faint, px: 0.5 }}>+{queue.length - 6} more waiting · Columns lists them all</Typography>}
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

function PeopleSpace({ items, picked, setPicked, agents, reviews, busy, onDraft, onApprove, onDispatch, onSettle, onOpenTask }) {
  const [text, setText] = useState({});
  if (!items.length) return <Empty text="Nobody is waiting in the lobby. Lobby Zero." />;
  return items.map((i) => {
    const on = picked === i.key, rv = i.rid ? reviews[i.rid] : null, m = matchFor(i, agents);
    const draft = text[i.key] ?? rv?.DraftText ?? "";
    const stop = (f) => (e) => { e.stopPropagation(); f(); };
    return (
      <Card key={i.key} on={on} onClick={() => setPicked(on ? null : i.key)} accent={needsYou(i) ? G.red : null}>
        <Who item={i} />
        <Typography sx={{ fontSize: 13, fontWeight: 700, mt: 0.3 }}>{i.title}</Typography>
        {on && <>
          {i.preview && <Typography sx={{ fontSize: 12, color: G.dim, mt: 0.6, whiteSpace: "pre-wrap" }}>“{i.preview}”</Typography>}
          <Match item={i} agents={agents} />
          {i.lane === "approve" && (
            <Box onClick={(e) => e.stopPropagation()} sx={{ mt: 0.8 }}>
              <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1, color: G.faint, mb: 0.4 }}>THE DRAFT - EDIT, THEN SEND</Typography>
              <Box component="textarea" value={draft} onChange={(e) => setText((t) => ({ ...t, [i.key]: e.target.value }))} rows={5}
                sx={{ width: "100%", boxSizing: "border-box", bgcolor: "rgba(0,0,0,.25)", color: G.ink, border: `1px solid ${G.line}`, borderRadius: "8px",
                  p: 1, fontSize: 12.5, fontFamily: "inherit", resize: "vertical" }} />
            </Box>
          )}
          <Box sx={{ display: "flex", gap: 0.6, mt: 0.9, flexWrap: "wrap" }}>
            {i.lane === "approve" && i.rid && <Btn kind="gold" disabled={!!busy || !draft.trim()} onClick={stop(() => onApprove(i, draft))} title="Sends it for real">📨 Send it · +40</Btn>}
            {i.lane !== "approve" && i.mid && <Btn kind={m.verb === "draft" ? "gold" : "ghost"} disabled={!!busy} onClick={stop(() => onDraft(i))}>✍ Draft a reply · +20</Btn>}
            {i.lane !== "approve" && i.mid && <Btn kind={m.verb === "dispatch" ? "gold" : "ghost"} disabled={!!busy} onClick={stop(() => onDispatch(i, m.kind || "general"))}>🤖 Hand to {m.verb === "dispatch" ? m.who : "an agent"} · +45</Btn>}
            <Btn disabled={!!busy} onClick={stop(() => onSettle(i, "done", "done"))}>✓ Done · +12</Btn>
            <Btn disabled={!!busy} onClick={stop(() => onSettle(i, "later", "later"))}>⏭ Later</Btn>
            {i.tid && <Btn onClick={stop(() => onOpenTask(i.tid))}>Open {i.ref}</Btn>}
          </Box>
        </>}
      </Card>
    );
  });
}

function CoffeeSpace({ items, picked, setPicked, busy, onSettle }) {
  if (!items.length) return <Empty text="The pot is empty and so is the room. Nothing to catch up on." />;
  const readable = items.filter((i) => i.lane !== "broken");
  const drain = async () => { for (const i of readable) await onSettle(i, "done", "read"); };
  return <>
    {readable.length > 1 && <Box sx={{ mb: 1 }}><Btn kind="mint" disabled={!!busy} onClick={drain}>☕ Drain the pot - catch up on all {readable.length}</Btn></Box>}
    {items.map((i) => {
      const on = picked === i.key;
      return (
        <Card key={i.key} on={on} onClick={() => setPicked(on ? null : i.key)} accent={i.lane === "broken" ? G.red : G.mint}>
          <Who item={i} />
          <Typography sx={{ fontSize: 13, fontWeight: 700, mt: 0.3 }}>{i.title}</Typography>
          {(on || i.lane === "broken") && (i.preview || i.why) && <Typography sx={{ fontSize: 12, color: G.dim, mt: 0.5 }}>{i.preview || i.why}</Typography>}
          {on && (
            <Box sx={{ display: "flex", gap: 0.6, mt: 0.8 }}>
              {i.lane === "broken"
                ? <Typography sx={{ fontSize: 11.5, color: G.gold }}>The machine's broken: sign it back in from Connections.</Typography>
                : <Btn kind="mint" disabled={!!busy} onClick={(e) => { e.stopPropagation(); onSettle(i, "done", "read"); }}>☕ Sip · got it · +8</Btn>}
              <Btn disabled={!!busy} onClick={(e) => { e.stopPropagation(); onSettle(i, "later", "later"); }}>Later</Btn>
            </Box>
          )}
        </Card>
      );
    })}
  </>;
}

function ArchiveSpace({ ghosts, hub, picked, setPicked, busy, onGhost, play, reload }) {
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
    {ghosts.length > 0 && <Typography sx={{ fontSize: 10, fontWeight: 800, letterSpacing: 1.2, color: "#b9c3ff", px: 0.5, mb: 0.6 }}>👻 GHOSTS · THREADS THAT SLIPPED · {ghosts.length}</Typography>}
    {ghosts.map((i) => {
      const on = picked === i.key;
      return (
        <Card key={i.key} on={on} onClick={() => setPicked(on ? null : i.key)} accent="#b9c3ff">
          <Who item={i} />
          <Typography sx={{ fontSize: 13, fontWeight: 700, mt: 0.3 }}>{i.title}</Typography>
          {on && <>
            <Typography sx={{ fontSize: 12, color: G.dim, mt: 0.5 }}>{i.why}</Typography>
            <Box sx={{ display: "flex", gap: 0.6, mt: 0.8 }}>
              <Btn kind="gold" disabled={!!busy} onClick={(e) => { e.stopPropagation(); onGhost(i, "followup"); }}>📨 Bust it - follow up · +35</Btn>
              <Btn disabled={!!busy} onClick={(e) => { e.stopPropagation(); onGhost(i, "dismiss"); }}>🕯 Let it rest · +6</Btn>
            </Box>
          </>}
        </Card>
      );
    })}
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
          <Btn disabled={voted.current.has(f.LoreId) || !!busy} onClick={(e) => { e.stopPropagation(); vote(f); }}>👍 Useful · +10</Btn>
        </Box>
      </Card>
    ))}
  </>;
}

function CoreSpace({ chat, onAsk, busy, pile, agents, picked, onGo }) {
  const [text, setText] = useState("");
  const end = useRef(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "end" }); }, [chat.length]);
  const send = (t) => { onAsk(t); setText(""); };
  const board = pile.filter((i) => needsYou(i) || i.kind === "agent").slice(0, 5);
  return <>
    <Box sx={{ mb: 1 }}>
      {chat.map((m, n) => (
        <Box key={n} sx={{ display: "flex", justifyContent: m.who === "you" ? "flex-end" : "flex-start", mb: 0.6 }}>
          <Box sx={{ maxWidth: "88%", px: 1.1, py: 0.7, borderRadius: m.who === "you" ? "11px 11px 2px 11px" : "11px 11px 11px 2px",
            bgcolor: m.who === "you" ? G.gold : "rgba(127,209,198,.12)", color: m.who === "you" ? "#1c1f24" : G.ink,
            border: m.who === "you" ? "none" : "1px solid rgba(127,209,198,.3)" }}>
            <Typography sx={{ fontSize: 12.5, whiteSpace: "pre-wrap" }}>{m.text}</Typography>
          </Box>
        </Box>
      ))}
      {busy === "ask" && <Typography sx={{ fontSize: 11.5, color: G.mint, px: 0.5 }}>✦ thinking…</Typography>}
      <div ref={end} />
    </Box>
    {picked && <Typography sx={{ fontSize: 11, color: G.faint, mb: 0.5 }}>Asking about: <b style={{ color: G.dim }}>{picked.title}</b></Typography>}
    <Box sx={{ display: "flex", gap: 0.6, flexWrap: "wrap", mb: 0.8 }}>
      {["What should I do next?", "Who should take the top thing?", "What's slipping?"].map((q) =>
        <Btn key={q} disabled={!!busy} onClick={() => send(q)}>{q}</Btn>)}
    </Box>
    <Box component="form" onSubmit={(e) => { e.preventDefault(); send(text); }} sx={{ display: "flex", gap: 0.6, mb: 1.5 }}>
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

const Empty = ({ text }) => <Typography sx={{ fontSize: 12, color: G.faint, px: 0.75, py: 1, lineHeight: 1.55 }}>{text}</Typography>;
