// SET UP WITH AI IS THE ASSISTANT BUILDING IT, ON THIS PAGE (the owner, 2026-11-13: "the agents are in tasks but assistant is ai about
// taskuary itself"; "the assistant should be built into setup with ai without opening the bottom bar"). One strip for every builder - a
// report, a dashboard, a routine, a playbook, a connection: the owner says what it should do, the server builds it (taskuary/build.py -
// drafts, checks, saves, tries again), and the strip shows its steps, its one question with a box to answer, and where it ended. The chat
// is never opened; New and the chat bring the page up with the words and the strip starts there (goStraight).
import React, { useEffect, useRef, useState } from "react";
import { Box, Button, CircularProgress, TextField, Typography } from "@mui/material";
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome";
import api from "./api";
import { openAppLink } from "./appLinks.js";
import { firstPressOf, goesStraight } from "./newTask.js";
import { INK, DIM, FAINT } from "./theme.jsx";
import ConnectAi from "./ConnectAi.jsx";
import { label as btnLabel } from "./buttons.js";

export const NEW_HASH = { report: "report=new", dashboard: "report=new-dashboard", workflow: "report=new-agent" };
const NOUN = { report: "report", dashboard: "dashboard", workflow: "routine", playbook: "playbook", connection: "connection" };
const POLL_MS = 1200;

// WORDS HANDED TO THE PAGE THAT OPENS NEXT: New's box or the chat said "a routine that ...", the builder comes up, and its strip takes them
let pending = null;
export const handTo = (kind, words) => { pending = { kind, words: String(words || ""), at: Date.now() }; };
export const takeFor = (kind) => {
  const p = pending && pending.kind === kind && Date.now() - pending.at < 30000 ? pending : null;
  if (p) pending = null;
  return p;
};
// the builder brought up with the words (`onOpen`: what the door shuts first, New's card) - this press made once per line. True when it went
export const goStraight = (made, onOpen) => {
  if (!goesStraight(made?.kind, made?.line)) return false;
  if (firstPressOf(made.line)) { handTo(made.kind, made.text || ""); onOpen?.(); openAppLink(NEW_HASH[made.kind]); }
  return true;
};

// BUILT: the page that lists what was just saved reads it in, then opens it (ReportsView); with nobody listening the link opens as it is
const BUILT = "tq-built";
export const onBuilt = (fn) => { const h = (e) => { e.preventDefault(); fn(e.detail); }; window.addEventListener(BUILT, h); return () => window.removeEventListener(BUILT, h); };
const built = (link) => { if (link && window.dispatchEvent(new CustomEvent(BUILT, { detail: link, cancelable: true }))) openAppLink(link); };

const MARK = { done: "✓", failed: "✗", you: "You:", said: "" };
const STEP_COLOR = { failed: "var(--tq-danger, #6b2733)", you: DIM, said: INK, done: INK };

// `kind`; `words`: what the box starts with; `refId`: a connection's card; `ctx`: what a card's form knows (guide, fields, secret label);
// `messageId`: a past email a playbook is made from; `onOpen`: a DOOR on a list - the press brings the builder up and the strip there starts;
// `auto`: start at once with `words`; `onDone(view)`: the thing is saved - the page goes to it
export default function SetupWithAi({ kind = "report", words = "", refId = null, ctx = null, messageId = null, onOpen, auto = false, onDone, sx = {} }) {
  // ...words handed over are taken in the first draw, so the strip opens already working - never a beat of an empty box first
  const handed = useRef(undefined);
  if (handed.current === undefined) handed.current = onOpen ? null : takeFor(kind);
  const first = handed.current?.words.trim() ? handed.current.words : auto && (kind === "connection" || words.trim()) ? words : null;
  const [said, setSaid] = useState(first ?? words), [reply, setReply] = useState("");
  const [open, setOpen] = useState(first != null || !!handed.current), [v, setV] = useState(null), [err, setErr] = useState("");
  const live = useRef(true), doneOnce = useRef(false);
  useEffect(() => () => { live.current = false; }, []);
  const noWords = kind === "connection";

  const poll = (id) => api.get(`/api/build/${id}`).then(({ data }) => {
    if (!live.current) return;
    setV(data);
    if (data.busy) setTimeout(() => poll(id), POLL_MS);
    else if (data.done && !doneOnce.current) { doneOnce.current = true; onDone ? onDone(data) : built(data.link); }
  }).catch((e) => live.current && setErr(e?.response?.data?.detail || "The setup could not be read - press Set up with AI again."));
  const go = async (text = said) => {
    setErr(""); setOpen(true);
    try {
      const { data } = await api.post("/api/build", { kind, words: String(text || "").trim(), ref: refId, ctx, message_id: messageId });
      setV(data); poll(data.id);
    } catch (e) { setErr(e?.response?.data?.detail || "It could not start."); }
  };
  const answer = async () => {
    const text = reply.trim(); if (!text || !v) return;
    setReply(""); setErr("");
    try { const { data } = await api.post(`/api/build/${v.id}/answer`, { text }); setV(data); poll(v.id); }
    catch (e) { setErr(e?.response?.data?.detail || "The answer did not reach it."); }
  };
  // ...words handed over from New or the chat start it the moment the page is up; a list's door hands none and opens the box
  useEffect(() => { if (first != null) go(first); }, []);   // eslint-disable-line react-hooks/exhaustive-deps

  const button = (
    <Button size="small" variant="outlined" disableElevation data-tq-setup-ai={kind} data-tq-view-skip="" startIcon={<AutoAwesomeIcon sx={{ fontSize: 15 }} />}
      title={`The Assistant sets up this ${NOUN[kind]} here - it drafts, checks and saves it, and asks you only what it cannot know`}
      onClick={() => (onOpen ? (handTo(kind, words), onOpen()) : noWords ? go("") : setOpen(true))} sx={{ alignSelf: "flex-start" }}>
      Set up with AI
    </Button>);
  if (onOpen || (!open && !v)) return <Box sx={{ display: "flex", ...sx }}>{button}</Box>;

  const busy = v ? !!v.busy : first != null && !err, steps = v?.steps || [];
  return (
    <Box data-tq-build={v?.id || ""} sx={{ border: "1px solid var(--tq-line, #e2ddd3)", borderRadius: 2, p: 1.5, display: "flex", flexDirection: "column",
      gap: 1, maxWidth: 820, bgcolor: "var(--tq-panel, #fff)", ...sx }}>
      <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: INK, display: "flex", alignItems: "center", gap: 0.75 }}>
        <AutoAwesomeIcon sx={{ fontSize: 15, color: DIM }} /> The Assistant sets up this {NOUN[kind]}
      </Typography>
      {!v && first == null && !noWords && <>
        <TextField size="small" multiline minRows={2} autoFocus fullWidth value={said} onChange={(e) => setSaid(e.target.value)}
          placeholder={`Say what the ${NOUN[kind]} should do`} inputProps={{ "aria-label": `What the ${NOUN[kind]} should do` }}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && said.trim()) { e.preventDefault(); go(); } }} />
        <Button size="small" variant="contained" disableElevation disabled={!said.trim()} onClick={() => go()} sx={{ alignSelf: "flex-start" }}>Set it up</Button>
      </>}
      {steps.map((s, i) => (
        <Typography key={i} data-tq-build-step={s.kind} sx={{ fontSize: 12.5, color: STEP_COLOR[s.kind] || INK, whiteSpace: "pre-wrap", lineHeight: 1.5 }}>
          {MARK[s.kind] ? `${MARK[s.kind]} ` : ""}{s.text}
        </Typography>))}
      {busy && <Typography sx={{ fontSize: 12.5, color: DIM, display: "flex", alignItems: "center", gap: 1 }}><CircularProgress size={12} /> Working on it…</Typography>}
      {v?.done && <Typography data-tq-build-done="" sx={{ fontSize: 12.5, fontWeight: 600, color: "var(--tq-success, #47654a)" }}>Set up and saved.</Typography>}
      {/* ...and with no AI to build it, the way to connect one, under its line (concierge.no_brain) */}
      {!busy && v?.no_ai && <ConnectAi variant="outlined" sx={{ alignSelf: "flex-start" }} />}
      {!busy && v && !v.done && !v.no_ai && (v.ask || v.error) && <>
        {v.ask && <Typography data-tq-build-ask="" sx={{ fontSize: 13, color: INK, fontWeight: 600, whiteSpace: "pre-wrap" }}>{v.ask}</Typography>}
        <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start" }}>
          <TextField size="small" fullWidth multiline autoFocus value={reply} onChange={(e) => setReply(e.target.value)}
            placeholder={v.ask ? "Your answer" : "Say what to change, and it tries again"} inputProps={{ "aria-label": v.ask ? "Your answer" : "What to change" }}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); answer(); } }} />
          <Button size="small" variant="contained" disableElevation disabled={!reply.trim()} onClick={answer}>{v.ask ? "Answer" : btnLabel("try_again")}</Button>
        </Box>
      </>}
      {err && <Typography sx={{ fontSize: 12.5, color: "var(--tq-danger, #6b2733)" }}>✗ {err}</Typography>}
      {!v && <Typography sx={{ fontSize: 11.5, color: FAINT }}>It drafts it, checks it and saves it. Anything that sends something out still waits for your press.</Typography>}
    </Box>
  );
}
