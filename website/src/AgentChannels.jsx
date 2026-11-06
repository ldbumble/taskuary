// TALK TO THIS AGENT FROM A CHAT, AND ITS PERMISSION REQUESTS AS BUTTONS (the owner, 2026-11-06: "a way to share the coding agent on my machine
// through you sending me slack or teams to that channel that would just keep talking to same agents" ... "protected to only people on your team").
// Developer mode only. The setup is one small fold at the foot of a coding task's chat: a channel, a chat, the teammates (name + their id
// there); Unbind is one press and one confirm. The permission card sits in the stream; only the owner's press - or their own reply on the
// bound chat - answers it (permissions.py).
import React, { useEffect, useState } from "react";
import { Box, Button, CircularProgress, MenuItem, TextField, Typography } from "@mui/material";
import api from "./api.js";
import { ID_HINT, channelLine, membersOf } from "./agentChannels.js";
import { ACCENT, BORDER, DIM, FAINT, INK, mono } from "./theme.jsx";

const btn = { minHeight: 30, py: 0, px: 1.3, fontSize: 12.5, textTransform: "none" };
const card = { my: 1.5, p: 1.5, border: `1px solid ${BORDER}`, borderRadius: 1.5, bgcolor: "#fff" };
const Head = ({ children }) => <Typography sx={{ color: ACCENT, fontSize: 9.5, fontWeight: 600, letterSpacing: "1.5px", mb: 0.4 }}>{children}</Typography>;
const why = (e, d) => e?.response?.data?.detail || e?.message || d;

// ── the agent asks: one card per request waiting on the owner ─────────────────────────────────────────────────────────
export function PermissionCards({ taskId, items = [], onAnswered }) {
  const [busy, setBusy] = useState(""), [err, setErr] = useState("");
  if (!items.length) return null;
  const answer = async (p, kind) => {
    setBusy(`${p.id}:${kind}`); setErr("");
    try { await api.post(`/api/tasks/${taskId}/permission`, { id: p.id, option: kind }); onAnswered?.(); }
    catch (e) { setErr(why(e, "That answer did not reach the agent")); }
    setBusy("");
  };
  return items.map((p) => (
    <Box key={p.id} data-tq-permission={p.id} sx={card} role="group" aria-label="The agent asks permission">
      <Head>THE AGENT ASKS</Head>
      <Typography variant="body2" sx={{ color: INK }}>It {p.line.replace(/\x60([^\x60]+)\x60/g, "“$1”")}.</Typography>
      <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap", mt: 0.8 }}>
        {p.options.map((o) => <Button key={o.kind} size="small" disableElevation disabled={!!busy} data-tq-permission-answer={o.kind}
          variant={o.kind === "allow_once" ? "contained" : "outlined"}
          sx={{ ...btn, ...(o.kind === "allow_once" ? {} : o.kind.startsWith("reject") ? { color: "#7a2f3c", borderColor: BORDER } : { color: INK, borderColor: BORDER }) }}
          startIcon={busy === `${p.id}:${o.kind}` ? <CircularProgress size={12} color="inherit" /> : null}
          onClick={() => answer(p, o.kind)}>{o.label}</Button>)}
      </Box>
      <Typography variant="caption" sx={{ display: "block", color: FAINT, mt: 0.5 }}>
        {p.risky ? "It sends or pushes, so there is no Always for it. " : ""}No answer by {String(p.until || "").slice(11, 16)} refuses it.</Typography>
      {err && <Typography variant="body2" sx={{ mt: 0.5, color: "#7a2f3c" }}>{err}</Typography>}
    </Box>));
}

// ── the setup: the bindings, Unbind, and Add a channel ─────────────────────────────────────────────────────────────────
// `taskId`: this task's agent (the fold at the foot of a coding task's chat). None: every binding, and a new one is "the coding agents" -
// conductor mode, the owner alone, any of their agents by TQ ref (Settings > Phone & chats). Teammates belong to one task's agent: the
// server refuses them on a conductor chat, so the form does not offer them there.
export function ChannelSetup({ taskId = null, onLoaded, rowOf = null }) {
  const [v, setV] = useState(null), [kind, setKind] = useState(""), [chat, setChat] = useState(""), [repo, setRepo] = useState(""),
    [ownerId, setOwnerId] = useState(""), [mates, setMates] = useState([]), [busy, setBusy] = useState(false), [err, setErr] = useState(""),
    [sure, setSure] = useState(null);
  const one = taskId != null, list = `tq-ac-chats-${one ? taskId : "all"}`;
  const load = () => api.get("/api/agent-channels", { params: one ? { task: taskId } : {} })
    .then(({ data }) => { setV(data?.data || null); onLoaded?.(data?.data || null); }).catch(() => { setV(null); onLoaded?.(null); });
  useEffect(() => { setV(null); setKind(""); setChat(""); setMates([]); setErr(""); setSure(null); load(); }, [taskId]);   // eslint-disable-line react-hooks/exhaustive-deps
  const k = v?.kinds.find((x) => x.kind === kind);
  // the owner's own id where the channel cannot tell their lines apart (Telegram, Slack), filled from what Taskuary already knows
  useEffect(() => { setOwnerId(k?.ownerId || ""); }, [k?.kind]);   // eslint-disable-line react-hooks/exhaustive-deps
  if (!v) return null;                                                 // Developer mode off: nothing here at all
  const bind = async () => {
    setBusy(true); setErr("");
    try {
      await api.post("/api/agent-channels", { kind, chat, task: one ? taskId : null, repo: repo || v.repo || "",
        members: membersOf({ owner: v.owner, ownerId, teammates: one ? mates : [] }) });
      setKind(""); setChat(""); setRepo(""); setMates([]); load();
    } catch (e) { setErr(why(e, "It was not bound")); }
    setBusy(false);
  };
  const unbind = async (c) => {
    if (sure !== c.id) { setSure(c.id); return; }
    setSure(null);
    try { await api.delete(`/api/agent-channels/${c.id}`); load(); } catch (e) { setErr(why(e, "It is still bound")); }
  };
  const mate = (i, f) => (e) => setMates((m) => m.map((x, j) => (j === i ? { ...x, [f]: e.target.value } : x)));
  return (
    <Box data-tq-channel-setup={one ? taskId : "all"}>
      {v.channels.map((c) => (
        <Box key={c.id} data-tq-agent-channel={c.id} sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.75 }}>
          <Box sx={{ flex: 1, minWidth: 0 }}>{rowOf ? rowOf(c) : (
            <Typography variant="body2" sx={{ color: INK }} noWrap title={channelLine(c)}>{channelLine(c)}
              {c.repoName && <Box component="span" sx={{ color: DIM }}> · {c.repoName}</Box>}</Typography>)}</Box>
          <Button size="small" sx={{ ...btn, color: "#7a2f3c" }} data-tq-agent-channel-unbind={c.id} onClick={() => unbind(c)}>{sure === c.id ? "Yes, unbind" : "Unbind"}</Button>
          {sure === c.id && <Button size="small" sx={{ ...btn, color: DIM }} onClick={() => setSure(null)}>Keep it</Button>}
        </Box>))}
      {!v.kinds.length && <Typography variant="body2" sx={{ color: DIM }}>Connect WhatsApp, Telegram, Slack or Teams first (Connections).</Typography>}
      {!!v.kinds.length && <>
        {!one && <Typography sx={{ color: INK, fontWeight: 600, fontSize: 12.5, mt: v.channels.length ? 1.5 : 0, mb: 0.75 }}>Add a channel</Typography>}
        <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
          <TextField select size="small" label="Channel" value={kind} onChange={(e) => { setKind(e.target.value); setChat(""); }} sx={{ minWidth: 130 }}
            inputProps={{ "data-tq-agent-channel-kind": "" }}>
            {v.kinds.map((x) => <MenuItem key={x.kind} value={x.kind}>{x.label}</MenuItem>)}</TextField>
          {k && <TextField size="small" label={kind === "slack" ? "Channel id" : "Chat"} value={chat} onChange={(e) => setChat(e.target.value)} sx={{ flex: 1, minWidth: 180 }}
            inputProps={{ list, "data-tq-agent-channel-chat": "" }} />}
          {k && <datalist id={list}>{k.chats.map((x) => <option key={x.chat} value={x.chat}>{x.name}</option>)}</datalist>}
        </Box>
        {k && <>
          {!v.repo && <TextField size="small" fullWidth label={one ? "Repo folder" : "Repo folder (optional) - keeps it to the agents in one repository"}
            value={repo} onChange={(e) => setRepo(e.target.value)} sx={{ mt: 1 }} />}
          {k.needsOwnerId && <TextField size="small" fullWidth label={`Your own id there - ${ID_HINT[kind].replace(/^their /, "your ")}`} value={ownerId} onChange={(e) => setOwnerId(e.target.value)} sx={{ mt: 1 }} />}
          {one && mates.map((m, i) => (
            <Box key={i} sx={{ display: "flex", gap: 1, mt: 1 }}>
              <TextField size="small" label="Teammate" value={m.name} onChange={mate(i, "name")} sx={{ flex: 1 }} />
              <TextField size="small" label={ID_HINT[kind]} value={m.id} onChange={mate(i, "id")} sx={{ flex: 1.3, "& input": mono }} />
              <Button size="small" sx={{ ...btn, color: DIM }} onClick={() => setMates((x) => x.filter((_, j) => j !== i))}>Remove</Button>
            </Box>))}
          <Box sx={{ display: "flex", gap: 0.75, mt: 1, alignItems: "center" }}>
            {one ? <Button size="small" sx={{ ...btn, color: INK }} onClick={() => setMates((x) => [...x, { name: "", id: "" }])}>Add a teammate</Button>
              : <Typography variant="caption" sx={{ color: FAINT }}>It talks to every coding agent you run, by its TQ number - yours alone. To code with
                teammates, bind a chat from the coding task itself (Talk to this agent from…).</Typography>}
            <Box sx={{ flex: 1 }} />
            <Button size="small" variant="contained" disableElevation disabled={busy || !chat.trim()} sx={btn} data-tq-agent-channel-bind="" onClick={bind}>Bind</Button>
          </Box>
          {one && <Typography variant="caption" sx={{ display: "block", color: FAINT, mt: 0.75 }}>
            Only the people named here are heard; everyone else in the chat is ignored. A teammate's words reach the agent as theirs - they
            cannot approve, land, push or send anything. The agent's answers are posted back to the chat.</Typography>}
        </>}
      </>}
      {err && <Typography variant="body2" role="alert" sx={{ mt: 0.75, color: "#7a2f3c" }}>{err}</Typography>}
    </Box>);
}

// ── Talk to this agent from… ──────────────────────────────────────────────────────────────────────────────────────────
// `pop`: drawn in the task header's popover (TaskPage HeadPop) - the setup alone, no fold of its own
export default function AgentChannels({ taskId, pop = false }) {
  const [v, setV] = useState(undefined);
  if (pop) return <Box data-tq-agent-channels="pop"><Box sx={{ ...card, mt: 0 }}><ChannelSetup taskId={taskId} onLoaded={setV} /></Box></Box>;
  // the fold is drawn once the read says Developer mode is on; open by itself while this agent already talks somewhere
  return (
    <details className="tq-aui-working-fold" data-tq-agent-channels="" open={!!v?.channels.length || undefined} hidden={!v || undefined}>
      <summary>Talk to this agent from…</summary>
      <Box sx={{ ...card, mt: 1 }}><ChannelSetup taskId={taskId} onLoaded={setV} /></Box>
    </details>);
}
