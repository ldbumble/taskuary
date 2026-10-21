// The Reason Network card (taskuary/reasonnet.py): who is on the network and what their agents are doing, the people the
// owner trusts, the gate that keeps everyone else out, what waits on the owner, and which folders stay off the network.
// Reason Network is the owner's own install - this card finds it and talks to it, and never installs or updates it.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, Chip, CircularProgress, Switch, TextField, Typography } from "@mui/material";
import api from "./api";
import { BORDER, DIM, FAINT, INK, PANEL } from "./theme.jsx";
import { cleanOne, gateWords, sessionLine, trustOf, withTrust, withoutTrust } from "./reasonNetwork.js";

const said = (e, d) => e?.response?.data?.detail || d;
const Section = ({ title, children }) => (
  <Box sx={{ mt: 2.5 }}>
    <Typography variant="overline" sx={{ color: FAINT, letterSpacing: ".08em" }}>{title}</Typography>
    <Box sx={{ mt: .5 }}>{children}</Box>
  </Box>
);
const Row = ({ children }) => (
  <Box sx={{ display: "flex", alignItems: "center", gap: 1, flexWrap: "wrap", py: .75, borderBottom: `1px solid ${BORDER}` }}>{children}</Box>
);

export default function ReasonPanel({ conn, reload }) {
  const [st, setSt] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [add, setAdd] = useState("");
  const load = useCallback(async () => {
    try { setSt((await api.get("/api/reason/status")).data); setErr(""); }
    catch (e) { setErr(said(e, "Reason Network could not be read")); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const act = async (key, f) => {
    setBusy(key); setErr("");
    try { await f(); } catch (e) { setErr(said(e, "That did not work")); }
    setBusy(""); load();
  };
  if (!st) return err ? <Alert severity="warning">{err}</Alert> : <CircularProgress size={20} sx={{ m: 2 }} />;

  const install = (
    <Typography variant="body2" sx={{ color: DIM }}>
      Reason Network is a separate program you install and keep up to date yourself. Taskuary only finds it on this computer and talks
      to it - it never installs or updates it. <a href={st.docs} target="_blank" rel="noreferrer">How to install it (its own instructions)</a>
    </Typography>
  );
  if (st.demo || !st.installed) return (
    <Box sx={{ maxWidth: 720 }}>
      <Alert severity="info" sx={{ mb: 1.5 }}>{st.demo ? "The demo has no Reason Network." : "Reason Network isn't installed on this computer."}</Alert>
      {install}
    </Box>
  );

  const trusted = st.trusted || [], me = st.who?.person || "";
  const saveTrust = (list, key) => act(key, () => api.post("/api/reason/trusted", { trusted: list }));
  const people = st.who?.people || [], sessions = st.who?.sessions || [];
  return (
    <Box sx={{ maxWidth: 820 }}>
      <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>
        Found at <code>{st.path}</code>. Teammates' coding agents can message yours, and yours theirs - peer to peer, end to end encrypted.
        {" "}<a href={st.docs} target="_blank" rel="noreferrer">Reason Network's own instructions</a>
      </Typography>
      {err && <Alert severity="error" sx={{ mb: 1 }}>{err}</Alert>}
      {st.detail && <Alert severity="warning" sx={{ mb: 1 }}>{st.detail}</Alert>}

      <Row>
        <Switch checked={!!conn.Active} disabled={busy === "active"}
          onChange={(e) => act("active", async () => { await api.post("/api/connectors", { ConnectorId: conn.ConnectorId, Active: e.target.checked }); reload(); })} />
        <Typography variant="body2" sx={{ color: INK }}>
          {conn.Active ? "Taskuary watches Reason Network: messages to your agents go on their tasks, and what waits on you comes to your work rail."
            : "Off: Taskuary does not watch Reason Network, and asks no teammate's agent anything."}
        </Typography>
      </Row>
      <Row>
        <Switch checked={!!st.gate?.on} disabled={busy === "gate" || !conn.Active}
          onChange={(e) => act("gate", () => api.post("/api/reason/gate", { on: e.target.checked }))} />
        <Box>
          <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }}>Only people you trust reach your agents</Typography>
          <Typography variant="caption" sx={{ color: DIM }}>{gateWords(st.gate)} Turning it on also keeps the Assistant's own folder off the network.</Typography>
        </Box>
      </Row>

      <Section title="People you trust">
        <Box sx={{ display: "flex", gap: .75, flexWrap: "wrap", mb: 1 }}>
          {trusted.length === 0 && <Typography variant="body2" sx={{ color: DIM }}>Nobody yet - only you. Add a name, or one of their sessions.</Typography>}
          {trusted.map((t) => <Chip key={t} label={t} size="small" disabled={busy === `rm${t}`} onDelete={() => saveTrust(withoutTrust(trusted, t), `rm${t}`)} />)}
        </Box>
        <Box sx={{ display: "flex", gap: 1 }}>
          <TextField size="small" label="name, or name/session" value={add} onChange={(e) => setAdd(e.target.value)} sx={{ bgcolor: "#fff", minWidth: 240 }}
            onKeyDown={(e) => { if (e.key === "Enter" && cleanOne(add)) { saveTrust(withTrust(trusted, add), "add"); setAdd(""); } }} />
          <Button size="small" variant="outlined" disabled={!cleanOne(add) || busy === "add"}
            onClick={() => { saveTrust(withTrust(trusted, add), "add"); setAdd(""); }}>Trust</Button>
        </Box>
      </Section>

      <Section title={`Who's on the network${st.who?.team ? ` - ${st.who.team}` : ""}`}>
        {people.length === 0 && <Typography variant="body2" sx={{ color: DIM }}>Nobody can be seen right now.</Typography>}
        {people.map((p) => {
          const theirs = sessions.filter((s) => s.person === p.person), how = trustOf(trusted, p.person, me);
          return (
            <Box key={p.person} sx={{ py: .75, borderBottom: `1px solid ${BORDER}` }}>
              <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
                <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }}>{p.person}{p.me ? " (you)" : ""}</Typography>
                <Typography variant="caption" sx={{ color: FAINT }}>{p.online ? "online" : "offline"}{p.verified ? " · verified" : ""}</Typography>
                {!p.me && (how === "person"
                  ? <Button size="small" onClick={() => saveTrust(withoutTrust(trusted, p.person), `p${p.person}`)}>Stop trusting</Button>
                  : <Button size="small" onClick={() => saveTrust(withTrust(trusted, p.person), `p${p.person}`)}>Trust</Button>)}
              </Box>
              {theirs.map((s) => {
                const one = trustOf(trusted, s.address, me);
                return (
                  <Box key={s.address} sx={{ display: "flex", alignItems: "center", gap: 1, pl: 2 }}>
                    <Typography variant="caption" sx={{ color: INK, fontFamily: "monospace" }}>{s.address}</Typography>
                    <Typography variant="caption" sx={{ color: DIM }}>{sessionLine(s)}</Typography>
                    {!p.me && how !== "person" && (one === "session"
                      ? <Button size="small" onClick={() => saveTrust(withoutTrust(trusted, s.address), `s${s.address}`)}>Stop trusting this session</Button>
                      : <Button size="small" onClick={() => saveTrust(withTrust(trusted, s.address), `s${s.address}`)}>Trust only this session</Button>)}
                  </Box>
                );
              })}
            </Box>
          );
        })}
      </Section>

      {(st.held || []).length > 0 && (
        <Section title="Waiting for you - held, not delivered">
          {st.held.map((m) => (
            <Box key={m.id} sx={{ p: 1, mb: 1, bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 1 }}>
              <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }}>{m.from}{m.ambiguous ? " - its text imitates another sender" : ""}</Typography>
              <Typography variant="body2" sx={{ color: DIM, whiteSpace: "pre-wrap" }}>{m.text}</Typography>
              {m.files?.length > 0 && <Typography variant="caption" sx={{ color: FAINT }}>Files: {m.files.join("; ")}</Typography>}
              <Box sx={{ display: "flex", gap: 1, mt: .5 }}>
                <Button size="small" variant="outlined" disabled={!!busy} onClick={() => act(`d${m.id}`, () => api.post(`/api/reason/held/${m.id}`, { deliver: true }))}>Deliver</Button>
                <Button size="small" disabled={!!busy} onClick={() => act(`x${m.id}`, () => api.post(`/api/reason/held/${m.id}`, { deliver: false }))}>Drop</Button>
              </Box>
            </Box>
          ))}
        </Section>
      )}

      <Section title="Off the network">
        <Row>
          <Typography variant="body2" sx={{ color: INK, flex: 1 }}>The Assistant's own folder</Typography>
          <Typography variant="caption" sx={{ color: DIM }}>{st.assistant_off ? "off the network" : "not yet off - turn on the trust gate above"}</Typography>
        </Row>
        {(st.folders || []).length === 0 && <Typography variant="body2" sx={{ color: DIM, mt: 1 }}>No repository checkouts are set up for your agents yet.</Typography>}
        {(st.folders || []).map((f) => (
          <Row key={f.path}>
            <Switch size="small" checked={!!f.off} disabled={busy === f.path}
              onChange={(e) => act(f.path, () => api.post("/api/reason/folder", { path: f.path, off: e.target.checked }))} />
            <Typography variant="body2" sx={{ color: INK }}>{f.repo}</Typography>
            <Typography variant="caption" sx={{ color: FAINT, fontFamily: "monospace" }}>{f.path}</Typography>
            <Typography variant="caption" sx={{ color: DIM }}>{f.off ? "off - its sessions are not seen and cannot be messaged" : "on the network"}</Typography>
          </Row>
        ))}
      </Section>
    </Box>
  );
}
