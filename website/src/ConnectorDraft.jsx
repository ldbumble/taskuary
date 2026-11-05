// A card's draft and the saves its fields make by themselves (connectorDraft.js has the rules). A control outside a card with a
// draft - a panel reused elsewhere - saves at once, as it always did.
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Typography } from "@mui/material";
import api from "./api";
import { applied, cfgPatch, changes, patched, prune, saveBody, splitNow, stage, stageable, tickWords, whyNot } from "./connectorDraft.js";

const Draft = createContext(null);

// TYPING WAITS FOR THE PAUSE, A PICK SAVES AT ONCE: a box with the focus is being typed in; a switch, a radio or a menu is a choice
const TYPE_MS = 700, PICK_MS = 60;
const typing = () => {
  const e = typeof document === "undefined" ? null : document.activeElement;
  return !!e && (e.tagName === "TEXTAREA" || (e.tagName === "INPUT" && !["checkbox", "radio", "button"].includes(e.type)));
};

// the draft a connection card holds over the connection and its sources, saving itself: `st` is what the last save said
export function useCardDraft(conn, sources, reload) {
  const [want, setWant] = useState(null);
  const [wantSrc, setWantSrc] = useState({});
  const [st, setSt] = useState(null);
  // the switch's own press (splitNow): drawn at once, saved at once, and the card comes back from the server as it now is
  const [flip, setFlip] = useState(null);
  const live = useRef({});
  live.current = { conn, sources, want, wantSrc, reload };
  // what the server now holds drops out of the draft (prune): a staged key never hides a later change to it
  useEffect(() => { setWant((w) => prune(conn, w)); }, [conn]);
  useEffect(() => {
    setWantSrc((m) => Object.fromEntries(sources.map((s) => [s.SourceId, prune(s, m[s.SourceId])]).filter(([, w]) => w)));
  }, [sources]);
  const timer = useRef(null);
  const save = useCallback(async () => {
    clearTimeout(timer.current); timer.current = null;
    const { conn: c, sources: ss, want: w, wantSrc: ws, reload: again } = live.current;
    const posts = [["/api/connectors", saveBody(c, w, "ConnectorId")], ...ss.map((s) => ["/api/sources", saveBody(s, ws[s.SourceId], "SourceId")])]
      .filter(([, b]) => b);
    if (!posts.length) return;
    setSt({ state: "saving" });
    // a refused save keeps its change in the draft, drawn as chosen, and goes again with the next edit
    try { for (const [u, b] of posts) await api.post(u, b); setSt({ state: "saved", at: Date.now() }); await again?.(); }
    catch (e) { setSt({ state: "error", why: whyNot(e) }); }
  }, []);
  const later = (ms) => { clearTimeout(timer.current); timer.current = setTimeout(save, ms); };
  // a box left, or the card left, saves what it was waiting to save
  const flush = () => { if (timer.current) save(); };
  useEffect(() => () => { if (timer.current) save(); }, [save]);
  const setOn = async (on) => {
    setFlip(on); setSt({ state: "saving" });
    try { await api.post("/api/connectors", { ConnectorId: conn?.ConnectorId, Active: !!on }); setSt({ state: "saved", at: Date.now() }); await reload?.(); }
    catch (e) { setSt({ state: "error", why: whyNot(e) }); }
    finally { setFlip(null); }
  };
  const draftConn = conn && flip !== null ? { ...applied(conn, want), Active: flip } : applied(conn, want);
  const draftSources = sources.map((s) => (wantSrc[s.SourceId] ? applied(s, wantSrc[s.SourceId]) : s));
  const pending = [
    ...changes(conn, want).map((c) => ({ ...c, where: "" })),
    ...sources.flatMap((s) => changes(s, wantSrc[s.SourceId]).map((c) => ({ ...c, where: s.Address }))),
  ];
  const ctx = {
    stageConn: (body) => {
      const { now, rest } = splitNow(body);
      if (now) setOn(now.Active);
      if (rest) { setWant((w) => stage(w, rest, live.current.conn)); later(typing() ? TYPE_MS : PICK_MS); }
    },
    stageSource: (body) => {
      const s = live.current.sources.find((x) => x.SourceId === body.SourceId);
      setWantSrc((m) => ({ ...m, [body.SourceId]: stage(m[body.SourceId], body, s) }));
      later(typing() ? TYPE_MS : PICK_MS);
    },
  };
  return { conn: draftConn, sources: draftSources, pending, st, flush, ctx, flipping: flip !== null };
}

export const DraftProvider = ({ value, children }) => <Draft.Provider value={value}>{children}</Draft.Provider>;

// a control's settings post: held by the card it sits in (and saved by it in a moment), straight to the server outside one
export function useSaveConnector(reload) {
  const d = useContext(Draft);
  return async (body) => {
    if (d && stageable(body, "ConnectorId")) { d.stageConn(body); return; }
    await api.post("/api/connectors", body); await reload?.();
  };
}
export function useSaveSource(reload) {
  const d = useContext(Draft);
  return async (body) => {
    if (d && stageable(body, "SourceId")) { d.stageSource(body); return; }
    await api.post("/api/sources", body); await reload?.();
  };
}

// A CARD'S OWN BOXES SAVE THEMSELVES: its credentials and settings, typed into `cfg`, go once the typing pauses - only the keys typed
// (ConfigPatch), so nothing the server wrote meanwhile is written back. A SECRET, and a write-only key (an app's client secret), go
// when the box is left (`flush`, on blur): saved half-typed, a key would be tried and refused on every pause. Each box's tick: `tick(key)`.
// `base` is the config as the boxes last saved it (`rebase` sets it); `extra` rides on every save (a card whose save is its switching on); `onSaved(data,
// keys)` hears each landed save, and a write-only value saved is taken out of the box - the server holds it now, and never sends it back.
export function useBoxesSave({ off = false, cid, cfg, setCfg, base, rebase, secret = "", setSecret = () => {}, writeOnly = [], extra = null, onSaved }) {
  const [marks, setMarks] = useState({});
  const live = useRef({});
  live.current = { off, cfg, base, secret, onSaved, extra, writeOnly, setCfg, rebase, setSecret };
  const timer = useRef(null);
  const mark = (keys, st) => setMarks((m) => ({ ...m, ...Object.fromEntries(keys.map((k) => [k, st])) }));
  const post = useCallback(async (all) => {
    clearTimeout(timer.current); timer.current = null;
    if (live.current.off) return;
    const { cfg: c, base: b, secret: s, onSaved: heard, extra: x, writeOnly: wo, setCfg: putCfg, rebase: putBase, setSecret: putSecret } = live.current;
    const patch = cfgPatch(b, c);
    if (!all) wo.forEach((k) => delete patch[k]);
    const keys = Object.keys(patch), withSecret = all && !!s;
    if (!keys.length && !withSecret) return;
    const names = [...keys, ...(withSecret ? ["Secret"] : [])];
    mark(names, { state: "saving" });
    try {
      const { data } = await api.post("/api/connectors", { ConnectorId: cid, ...(x || {}), ...(keys.length ? { ConfigPatch: patch } : {}), ...(withSecret ? { Secret: s } : {}) });
      const gone = keys.filter((k) => wo.includes(k));
      putBase((v) => { const n = patched(v, patch); gone.forEach((k) => delete n[k]); return n; });
      if (gone.length) putCfg((v) => Object.fromEntries(Object.entries(v).filter(([k]) => !gone.includes(k))));
      if (withSecret) putSecret("");
      mark(names, { state: "saved", at: Date.now() });
      heard?.(data, names);
    } catch (e) { mark(names, { state: "error", why: whyNot(e) }); }
  }, [cid]);
  useEffect(() => {
    const p = cfgPatch(base, cfg);
    writeOnly.forEach((k) => delete p[k]);
    if (!Object.keys(p).length) return;
    clearTimeout(timer.current); timer.current = setTimeout(() => post(false), typing() ? TYPE_MS : PICK_MS);
  }, [cfg]);   // eslint-disable-line react-hooks/exhaustive-deps
  // leaving the card saves what was typed and not yet saved, secret and all
  useEffect(() => () => {
    const { cfg: c, base: b, secret: s } = live.current;
    if (s || Object.keys(cfgPatch(b, c)).length) post(true);
  }, [post]);
  return { flush: () => post(true), tick: (key) => <Tick st={marks[key]} />, marks };
}

// THE QUIET TICK BY A FIELD (the owner, 2026-11-05): "Saved" for a few seconds once a save landed; "Not saved - <why>" until the next try
const SHOWN_MS = 4000;
export function Tick({ st, sx }) {
  const [shown, setShown] = useState(true);
  // ...counted from the save, not from the drawing: a step opened later does not say an old save again
  useEffect(() => {
    const left = st?.state === "saved" ? SHOWN_MS - (Date.now() - (st.at || Date.now())) : 1;
    setShown(left > 0);
    if (st?.state !== "saved" || left <= 0) return undefined;
    const t = setTimeout(() => setShown(false), left); return () => clearTimeout(t);
  }, [st]);
  const w = tickWords(st);
  if (!w || !shown) return null;
  const bad = st.state === "error";
  return (
    <Typography component="span" role="status" data-tq-saved={st.state}
      sx={{ ml: 1, fontSize: 12, fontWeight: 600, whiteSpace: bad ? "normal" : "nowrap", color: bad ? "#8a3646" : "#47654a", ...sx }}>
      {bad ? w : `✓ ${w}`}</Typography>
  );
}
