// THE ONE BOX AN AGENT STARTS FROM (the owner, 2026-10-23: "start a agent on fyi email or any email you need to write prompt what
// about the email or attachment is the issue?? regular box should show up with voice note and attachment button ... Same for sending
// to agent ... a report"). Every door that starts an agent on an item - a task's Send to agent, Run another agent, a goal's step,
// an email's or a report's Send to agent on the row, a line of the fyi batch - opens THIS before anything runs: what to do, in your
// words or a voice note, pictures by paste, drop or the paperclip, and which agent. The item itself rides along by itself - the
// email and its files, the report's rows - and your words lead what the agent is told. An empty box is allowed: the item alone is
// the job. Start is the only press that starts.
import React, { useEffect, useRef, useState } from "react";
import { Box, Button, CircularProgress, TextField, Typography } from "@mui/material";
import { AgentPicker, MicButton, TaskuaryMark, useAgents } from "./ui.jsx";
import { AttachImage, ImageTray, usePromptImages, withImages } from "./promptImages.jsx";
import { cannotStart, useCapabilities } from "./capabilities.js";
import { choice, label as btn } from "./buttons.js";
import { BORDER, FAINT, INK } from "./theme.jsx";

// the box's own placeholder: what the owner is asked, the same words on every door
export const ASK_WHAT = "What should it do? What about it is the issue? - optional; paste or drop a picture too";
export const ASK_REPORT = "What should it do? Which part of the report should change? - optional; paste or drop a picture too";

// The box itself, drawn the same wherever it opens. `onValue` takes a value or an updater: the mic's words land after the press,
// so they are appended to what is in the box THEN, not to what was there when recording started.
export function RunForm({ title, picker, note, value, onValue, pics, placeholder = ASK_WHAT, children, actions, autoFocus = false, sx }) {
  const add = (x) => onValue((cur) => (cur ? `${cur} ${x}` : x));
  return (
    <Box data-tq-agent-box="" sx={{ mt: 1, pt: 1, borderTop: `1px solid ${BORDER}`, ...sx }}>
      {title && <Typography sx={{ color: INK, fontSize: 12.5, fontWeight: 600, mb: 0.75 }}>{title}</Typography>}
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
        {picker}
        {note && <Typography variant="caption" sx={{ color: FAINT }}>{note}</Typography>}
      </Box>
      <TextField fullWidth multiline minRows={2} maxRows={5} size="small" value={value} autoFocus={autoFocus}
        onChange={(e) => onValue(e.target.value)} placeholder={placeholder} {...pics.drop}
        InputProps={{ endAdornment: (
          <Box sx={{ display: "flex", alignSelf: "flex-start", gap: 0.25 }}>
            <AttachImage pics={pics} sx={{ width: 30, height: 30 }} />
            <MicButton size={18} sx={{ width: 30, height: 30, p: 0, color: "#6e685f" }} onText={add} />
          </Box>) }}
        sx={{ mt: 0.85, bgcolor: "#fff", "& .MuiInputBase-root": { alignItems: "flex-start" } }} />
      <ImageTray pics={pics} sx={{ mt: 0.75 }} />
      {children}
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 0.75, flexWrap: "wrap" }}>{actions}</Box>
    </Box>
  );
}

// THE BOX ON AN ITEM WITH NO TASK PAGE - an email, an fyi, a report run on the walk. It holds its own answers and hands them to
// `onStart({ verb, kind, text, agent, brain, pick, model })`; the caller runs the start through its own road and the box closes
// when that resolves. `coding`: the kind the door asked for - the coding agent only where a coding tool is connected.
export function AgentAsk({ coding: wantCoding = false, title, what, placeholder = ASK_WHAT, onStart, onClose, inline = false }) {
  const caps = useCapabilities(), canCode = !!caps.coding;
  const { agents, models, kinds, brainList, brainModels, generalBrains, agentsRead, codingReady } = useAgents();
  const [general, setGeneral] = useState(!(wantCoding && canCode));
  const coding = canCode && !general;
  const [run, setRun] = useState({ agent: "", brain: "", pick: "", model: "" });
  const [text, setText] = useState("");
  const pics = usePromptImages();
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const why = cannotStart(caps, { coding, read: agentsRead, brains: generalBrains, codingReady });
  const box = useRef(null);
  useEffect(() => { box.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" }); }, []);
  const swap = (g) => { setGeneral(g); setRun({ agent: "", brain: "", pick: "", model: "" }); };
  const start = async () => {
    setBusy(true); setErr("");
    try {
      await onStart?.({ verb: coding ? "coding_agent" : "regular_agent", kind: coding ? "coding" : "general",
        text: withImages(text.trim(), pics.paths) || "", agent: coding ? null : run.agent || null,
        brain: coding ? run.brain || null : null, pick: coding ? null : run.pick || null, model: run.model || null });
    } catch (e) { setErr(e?.response?.data?.detail || e?.message || "It did not start - press it again."); }
    finally { setBusy(false); }
  };
  const verb = coding ? "coding_agent" : "regular_agent";
  return (
    <Box ref={box} data-tq-agent-ask="" sx={inline ? { p: 1.5, border: "1px solid #d5d0c7", borderRadius: "12px", bgcolor: "#fffdfb" } : {}}>
      <RunForm title={title || btn(verb)} value={text} onValue={setText} pics={pics} autoFocus placeholder={placeholder}
        sx={inline ? { mt: 0, pt: 0, borderTop: 0 } : {}}
        note={what}
        picker={<AgentPicker agents={agents} models={models} kinds={kinds} coding={coding} agent={run.agent} model={run.model}
          brains={brainList} brainModels={brainModels} brain={run.brain}
          generalBrains={generalBrains} brainsRead={agentsRead} codingReady={codingReady} pick={run.pick}
          onPick={coding ? undefined : (p) => setRun((r) => ({ ...r, pick: p }))}
          onBrain={(b) => setRun((r) => ({ ...r, brain: b, model: "" }))}
          onAgent={(a) => setRun((r) => ({ ...r, agent: a }))}
          onModel={(m) => setRun((r) => ({ ...r, model: m }))} size={28} />}
        actions={<>
          <span title={why || undefined}><Button size="small" variant="contained" disableElevation data-tq-agent-start={coding ? "coding" : "general"}
            disabled={busy || pics.busy || !!why} onClick={start}
            startIcon={busy ? <CircularProgress size={11} /> : <TaskuaryMark size={13} />}>
            {busy ? "Starting…" : btn(verb)}</Button></span>
          {/* the other kind is one press away, as on the task's own box - never chosen for the owner */}
          {canCode && <Button size="small" variant="outlined" disabled={busy} onClick={() => swap(coding)}>
            {choice("agent", coding ? "regular_agent" : "coding_agent")}</Button>}
          <Button size="small" variant="text" disabled={busy} onClick={onClose}>Cancel</Button>
        </>}>
        {err && <Typography role="alert" variant="caption" sx={{ color: "#7a2f3c", display: "block", mt: 0.5 }}>{err}</Typography>}
      </RunForm>
    </Box>
  );
}
