// FIRST RUN, on the assistant canvas: two steps - pick your AI, connect your email - and then the mail is read and sorted.
//
// The owner, 2026-10-14: "Think about a idiot user who knows nothing about nothing and he should setup this app in 2 steps
// ... Remove the popup things just use the assistant canvas. use the advisor as well to say next steps ... it should never
// drop the user." Every card does its whole step on one click (taskuary/firstrun.py), every wait has a limit, and every
// answer ends in the one thing to press next. The NEXT line on top is the server's (firstrun.state), never guessed here.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Box, Button, CircularProgress, TextField, Typography } from "@mui/material";
import api from "./api";
import { ACCENT, ASSISTANT, BORDER, DIM, FAINT, INK, PANEL } from "./theme.jsx";
import { ChannelDetail, MsSignIn } from "./ConnectorsView.jsx";
import { CliPane, useCliSetup } from "./cliSetup.jsx";

const CHECK_MS = 90_000;            // a card test is a minute at most server-side; past this we say so instead of spinning
const INSTALL_MS = 6 * 60_000;
const errText = (e) => e?.response?.data?.detail || (e?.code === "ECONNABORTED" ? "That took too long." : e?.message) || "That didn't work.";
const ok = "#47654a", bad = "#6b2733";

function Card({ title, sub, on, busy, disabled, onClick, children }) {
  return (
    <Box component={onClick ? "button" : "div"} type={onClick ? "button" : undefined} onClick={disabled || busy ? undefined : onClick}
      data-tq-firstrun-card={title}
      sx={{ textAlign: "left", fontFamily: "inherit", display: "flex", flexDirection: "column", gap: 0.4, p: 1.5, minHeight: 74,
        borderRadius: "12px", border: `1.5px solid ${on ? ACCENT : BORDER}`, bgcolor: PANEL, cursor: onClick && !disabled ? "pointer" : "default",
        opacity: disabled ? 0.6 : 1, transition: "border-color .15s, box-shadow .15s",
        "&:hover": onClick && !disabled ? { borderColor: ACCENT, boxShadow: "0 2px 10px rgba(30,50,40,.08)" } : {} }}>
      <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Typography sx={{ fontWeight: 650, fontSize: 15, color: INK, flex: 1 }}>{title}</Typography>
        {busy && <CircularProgress size={14} />}
      </Box>
      {sub && <Typography sx={{ fontSize: 12.5, color: FAINT, lineHeight: 1.4 }}>{sub}</Typography>}
      {children}
    </Box>
  );
}

const Grid = ({ children }) => (
  <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(auto-fill, minmax(210px, 1fr))" }, gap: 1.25 }}>{children}</Box>
);

const Said = ({ said }) => (said ? (
  <Typography role="status" sx={{ fontSize: 13, fontWeight: 600, color: said.ok ? ok : bad, mt: 0.5 }}>{said.ok ? "✓" : "✗"} {said.text}</Typography>
) : null);

// THE NEXT STEP, in the Advisor's voice and place: one line, what to do now
const Next = ({ text }) => (
  <Box data-tq-firstrun-next="" sx={{ display: "flex", gap: 1, alignItems: "flex-start", p: 1.25, borderRadius: "10px",
    bgcolor: ASSISTANT.tint || "#e8eee4", border: `1px solid ${ASSISTANT.bd || "#d3dccd"}` }}>
    <Typography component="span" sx={{ fontSize: 10.5, fontWeight: 700, letterSpacing: ".08em", color: ASSISTANT.ink, pt: "2px" }}>NEXT</Typography>
    <Typography sx={{ fontSize: 14, color: INK, lineHeight: 1.45 }}>{text}</Typography>
  </Box>
);

function AiStep({ st, reload }) {
  const [busy, setBusy] = useState(""), [said, setSaid] = useState(null), [fix, setFix] = useState(null);
  const [keyOpen, setKeyOpen] = useState(false), [keyType, setKeyType] = useState(st.keys[0]?.type || ""), [key, setKey] = useState("");
  const { openSetup, pane, note } = useCliSetup();
  const [more, setMore] = useState(false);
  const main = st.ais.filter((a) => !a.more), others = st.ais.filter((a) => a.more);
  const pick = async (ai) => {
    // not on this computer: installing IS choosing it - one click, never a second "now press Install" (the owner, 2026-10-14)
    if (!ai.installed && ai.install && !ai.done) { install(ai); return; }
    setBusy(ai.name); setFix(null);
    setSaid({ ok: true, text: `Checking that ${ai.title} works - this can take up to a minute…` });
    try {
      const { data } = await api.post("/api/setup/first-run/ai", { name: ai.name }, { timeout: CHECK_MS });
      setSaid({ ok: data.ok, text: data.why });
      if (data.ok) reload(); else if (data.fix) setFix({ ...ai, fix: data.fix });
    } catch (e) { setSaid({ ok: false, text: `${errText(e)} Click the card to try again.` }); }
    setBusy("");
  };
  const install = async (ai) => {
    setBusy(ai.name); setSaid({ ok: true, text: `Installing ${ai.title}… this takes about a minute.` });
    try {
      await api.post("/api/cli/install", { name: ai.install });
      const until = Date.now() + INSTALL_MS;
      for (;;) {
        await new Promise((r) => setTimeout(r, 2500));
        const { data } = await api.get("/api/cli/install/state");
        if (data.phase === "installing" && data.detail) setSaid({ ok: true, text: `${data.detail} (this can take a few minutes)` });
        if (data.phase === "done") break;
        if (data.phase === "failed") throw new Error(data.detail || "the installer stopped");
        if (Date.now() > until) throw new Error("the install is taking too long");
      }
      setBusy(""); await pick({ ...ai, installed: true, done: true });   // installed: test it right away - one click, the whole step
    } catch (e) { setBusy(""); setFix({ ...ai, fix: "install" });
      setSaid({ ok: false, text: `${ai.title} didn't install: ${errText(e)} Press Install to try again, or pick another AI.` }); }
  };
  const saveKey = async () => {
    setBusy("key"); setSaid(null);
    try {
      const { data } = await api.post("/api/setup/first-run/key", { type: keyType, key }, { timeout: CHECK_MS });
      setSaid({ ok: data.ok, text: data.why }); if (data.ok) { setKey(""); reload(); }
    } catch (e) { setSaid({ ok: false, text: `${errText(e)} Press Use this key to try again.` }); }
    setBusy("");
  };
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.25 }}>
      <Grid>
        {[...main, ...(more ? others : [])].map((ai) => (
          <Card key={ai.name} title={ai.title} sub={ai.installed ? ai.sub : `${ai.sub} · not installed yet`} busy={busy === ai.name}
            disabled={!!busy && busy !== ai.name} on={fix?.name === ai.name} onClick={() => pick(ai)} />
        ))}
        <Card title="Use an API key" sub="Paste a Claude or OpenAI key instead" on={keyOpen} onClick={() => setKeyOpen((v) => !v)} />
      </Grid>
      {!!others.length && <Box><Button size="small" onClick={() => setMore((v) => !v)} sx={{ color: DIM, fontSize: 12.5 }}>
        {more ? "Show fewer" : `Other AI already on this computer (${others.length})`}</Button></Box>}
      <Said said={said} />
      {fix?.fix === "install" && <Box><Button variant="contained" disableElevation disabled={!!busy} onClick={() => install(fix)}>Install {fix.title}</Button></Box>}
      {fix?.fix === "signin" && (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
            <Button variant="contained" disableElevation onClick={() => openSetup(fix.setup)}>Sign in to {fix.title}</Button>
            <Button onClick={() => pick(fix)} disabled={!!busy}>I've signed in - check again</Button>
          </Box>
          {note && <Typography sx={{ fontSize: 12.5, color: note.bad ? bad : DIM }}>{note.text}</Typography>}
          {pane?.sid && <CliPane pane={pane} height="38vh" />}
        </Box>
      )}
      {keyOpen && (
        <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
          {st.keys.map((k) => (
            <Button key={k.type} size="small" variant={keyType === k.type ? "contained" : "outlined"} disableElevation onClick={() => setKeyType(k.type)}>{k.title}</Button>
          ))}
          <TextField size="small" type="password" placeholder="Paste the key here" value={key} onChange={(e) => setKey(e.target.value)}
            sx={{ flex: 1, minWidth: 220 }} helperText={st.keys.find((k) => k.type === keyType)?.sub || ""} />
          <Button variant="contained" disableElevation disabled={!key.trim() || busy === "key"} onClick={saveKey}>
            {busy === "key" ? <CircularProgress size={14} sx={{ color: "#fff" }} /> : "Use this key"}</Button>
        </Box>
      )}
    </Box>
  );
}

function MailStep({ st, reload }) {
  const [open, setOpen] = useState(""), [said, setSaid] = useState(null);
  const [card, setCard] = useState(null);                   // the chosen email card itself, as Connections draws it
  const load = useCallback(async (type) => {
    const want = st.mail.find((m) => m.type === type);
    if (!want) return;
    try {
      const { data } = await api.get("/api/connectors");
      const c = (data.data || data || []).find((x) => x.ConnectorId === want.cid);
      if (c) { let cfg = {}; try { cfg = JSON.parse(c.ConfigJson || "{}"); } catch { /* blank is fine */ } setCard({ conn: c, cfg }); }
    } catch (e) { setSaid({ ok: false, text: `${errText(e)} Click the card to try again.` }); }
  }, [st.mail]);
  const choose = (t) => { setOpen((o) => (o === t ? "" : t)); setSaid(null); setCard(null); load(t); };
  return (
    <Box sx={{ display: "flex", flexDirection: "column", gap: 1.25 }}>
      <Grid>{st.mail.map((m) => <Card key={m.type} title={m.title} sub={m.sub} on={open === m.type} onClick={() => choose(m.type)} />)}</Grid>
      {open === "outlook" && card && <MsSignIn conn={card.conn} cfg={card.cfg} reload={() => load("outlook")} onSignedIn={reload} plain />}
      {(open === "gmail" || open === "imap") && card && (
        <ChannelDetail simple conn={card.conn} sources={[]} reload={() => {}} onBack={() => setOpen("")} onConnected={reload} />
      )}
      <Said said={said} />
    </Box>
  );
}

export default function FirstRun({ onWalk, onChanged }) {
  const [st, setSt] = useState(null), [err, setErr] = useState("");
  const was = useRef("");
  const reload = useCallback(async () => {
    try { const { data } = await api.get("/api/setup/first-run", { timeout: 30_000 }); setSt(data); setErr(""); }
    catch (e) { setErr(`${errText(e)} Retrying…`); }
  }, []);
  useEffect(() => { reload(); }, [reload]);
  // while mail is being read - or a Microsoft sign-in may finish in another tab - read again until it is done
  useEffect(() => {
    if (!st || st.step === "done" || st.step === "ai") return undefined;
    const id = setTimeout(reload, st.step === "reading" ? 3000 : 5000);
    return () => clearTimeout(id);
  }, [st, reload]);
  // a step moved: the rail reloads, and the top bar's chip counts again (TaskHubPage listens) - it said "2 steps" after one
  useEffect(() => {
    if (!st || st.step === was.current) return;
    if (was.current) { onChanged?.(); window.dispatchEvent(new Event("tq-setup-changed")); }
    was.current = st.step;
  }, [st, onChanged]);
  if (!st) return <Box sx={{ p: 2, display: "flex", gap: 1, alignItems: "center" }}><CircularProgress size={16} />
    <Typography sx={{ color: DIM }}>{err || "Getting set up…"}</Typography></Box>;
  const dot = (n, on, done) => (
    <Box sx={{ width: 22, height: 22, borderRadius: 99, display: "grid", placeItems: "center", fontSize: 12, fontWeight: 700,
      color: done || on ? "#fff" : FAINT, bgcolor: done ? ok : on ? ACCENT : "#ece8e1" }}>{done ? "✓" : n}</Box>
  );
  const s1 = st.step === "ai", s2 = st.step === "email", reading = st.step === "reading" || st.step === "done";
  return (
    <Box data-tq-firstrun={st.step} sx={{ display: "flex", flexDirection: "column", gap: 1.75, maxWidth: 860 }}>
      <Typography sx={{ fontWeight: 700, fontSize: 20, color: INK }}>Let's set up Taskuary</Typography>
      <Next text={st.next} />
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>{dot(1, s1, !s1)}
          <Typography sx={{ fontWeight: 650, color: INK }}>Pick your AI</Typography>
          {!s1 && <Typography sx={{ color: ok, fontSize: 13 }}>{st.brain.name} is ready</Typography>}</Box>
        {s1 && <AiStep st={st} reload={reload} />}
      </Box>
      <Box sx={{ display: "flex", flexDirection: "column", gap: 1, opacity: s1 ? 0.55 : 1 }}>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}>{dot(2, s2, reading)}
          <Typography sx={{ fontWeight: 650, color: INK }}>Connect your email</Typography>
          {reading && <Typography sx={{ color: ok, fontSize: 13 }}>{st.connected.join(", ")}</Typography>}</Box>
        {s2 && <MailStep st={st} reload={reload} />}
      </Box>
      {reading && (
        <Box sx={{ display: "flex", gap: 1.25, alignItems: "center", flexWrap: "wrap" }}>
          {st.step === "reading" ? <><CircularProgress size={16} /><Typography sx={{ color: DIM }}>
            {st.sorting ? `Sorting ${st.sorting} email${st.sorting === 1 ? "" : "s"}…` : "Reading your mail…"}</Typography></>
            : <Button variant="contained" disableElevation onClick={onWalk}>Walk me through my tasks</Button>}
        </Box>
      )}
    </Box>
  );
}
