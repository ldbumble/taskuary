// THE ONE BOX AN AGENT STARTS FROM (the owner, 2026-10-23: "start a agent on fyi email or any email you need to write prompt what
// about the email or attachment is the issue?? regular box should show up with voice note and attachment button ... Same for sending
// to agent ... a report"). Every door that starts an agent on an item - a task's Send to agent, Run another agent, a goal's step,
// an email's or a report's Send to agent on the row, a line of the fyi batch - opens THIS before anything runs: what to do, in your
// words or a voice note, pictures by paste, drop or the paperclip, and which agent. The item itself rides along by itself - the
// email and its files, the report's rows - and your words lead what the agent is told. An empty box is allowed: the item alone is
// the job. Start is the only press that starts.
import React, { useEffect, useRef, useState } from "react";
import { Box, Button, CircularProgress, Typography } from "@mui/material";
import { AgentPicker, TaskuaryMark, useAgents } from "./ui.jsx";
import { usePromptImages, withImages } from "./promptImages.jsx";
import { PromptBox } from "./AgentSummary.jsx";
import { cannotStart, useCapabilities } from "./capabilities.js";
import { choice, label as btn } from "./buttons.js";
import { useViewExtras } from "./pageView.js";
import { BORDER, FAINT, INK } from "./theme.jsx";
import { MESSAGE } from "./kinds.js";

// the box's own placeholder: the one prompt wording, the same words on every door (kinds.MESSAGE) - a report or a meeting included
export const ASK_WHAT = MESSAGE;

// The box itself, drawn the same wherever it opens. `onValue` takes a value or an updater: the mic's words land after the press,
// so they are appended to what is in the box THEN, not to what was there when recording started.
// ...ITS WORDS ARE THE ONE BOX (AgentSummary.PromptBox, the owner 2026-11-06: "stop building each unique prompt box. it should be shared"): the
// paperclip, the files, the words, the mic. Its press stays the form's own (`actions`: Start), so the box draws no Send of its own
export function RunForm({ title, picker, note, value, onValue, pics, placeholder = ASK_WHAT, children, actions, autoFocus = false, sx }) {
  const setText = onValue;     // the words, typed or dictated: `onValue` takes a value or an updater
  return (
    <Box data-tq-agent-box="" sx={{ mt: 1, pt: 1, borderTop: `1px solid ${BORDER}`, ...sx }}>
      {title && <Typography sx={{ color: INK, fontSize: 12.5, fontWeight: 600, mb: 0.75 }}>{title}</Typography>}
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, flexWrap: "wrap" }}>
        {picker}
        {note && <Typography variant="caption" sx={{ color: FAINT }}>{note}</Typography>}
      </Box>
      <Box sx={{ mt: 0.85 }}><PromptBox text={value} setText={setText} pics={pics} placeholder={placeholder} label={title || "What to do"} autoFocus={autoFocus} /></Box>
      {children}
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75, mt: 0.75, flexWrap: "wrap" }}>{actions}</Box>
    </Box>
  );
}

// THE BOX ON AN ITEM WITH NO TASK PAGE - an email, an fyi, a report run on the walk. It holds its own answers and hands them to
// `onStart({ verb, kind, text, agent, brain, pick, model })`; the caller runs the start through its own road and the box closes
// when that resolves. `coding`: the kind the door asked for - the coding agent only where a coding tool is connected.
// `view`: { item, title } - the box is the page the pop-up Assistant reads while it is open (pageView.js): its words box and its Send to agent,
// so "prep me for this meeting: pull the open issues with these people" fills it and starts it as the owner would (the owner, 2026-11-02)
export function AgentAsk({ coding: wantCoding = false, title, what, placeholder = ASK_WHAT, onStart, onClose, inline = false, view = null }) {
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
  useViewExtras(box, view ? { item: view.item, title: view.title } : {});
  useEffect(() => { box.current?.scrollIntoView?.({ block: "nearest", behavior: "smooth" }); }, []);
  const swap = (g) => { setGeneral(g); setRun({ agent: "", brain: "", pick: "", model: "" }); };
  const start = async () => {
    setBusy(true); setErr("");
    try {
      await onStart?.({ verb: coding ? "coding_agent" : "regular_agent", kind: coding ? "coding" : "general",
        text: withImages(text.trim(), pics.paths) || "", agent: coding ? null : run.agent || null,
        brain: coding ? run.brain || null : null, pick: coding && run.brain ? null : run.pick || null, model: run.model || null });
    } catch (e) { setErr(e?.response?.data?.detail || e?.message || "It did not start - press it again."); }
    finally { setBusy(false); }
  };
  const verb = coding ? "coding_agent" : "regular_agent";
  return (
    <Box ref={box} data-tq-agent-ask="" data-tq-view={view ? "agent" : undefined} data-tq-view-label={view?.title} sx={inline ? { p: 1.5, border: "1px solid var(--tq-border, #d5d0c7)", borderRadius: "12px", bgcolor: "var(--tq-panel, #fffdfb)" } : {}}>
      <RunForm title={title || btn(verb)} value={text} onValue={setText} pics={pics} autoFocus placeholder={placeholder}
        sx={inline ? { mt: 0, pt: 0, borderTop: 0 } : {}}
        note={what}
        picker={<AgentPicker agents={agents} models={models} kinds={kinds} coding={coding} agent={run.agent} model={run.model}
          brains={brainList} brainModels={brainModels} brain={run.brain}
          generalBrains={generalBrains} brainsRead={agentsRead} codingReady={codingReady} pick={run.pick}
          onPick={(p) => setRun((r) => ({ ...r, pick: p }))}
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
        {err && <Typography role="alert" variant="caption" sx={{ color: "var(--tq-danger, #7a2f3c)", display: "block", mt: 0.5 }}>{err}</Typography>}
      </RunForm>
    </Box>
  );
}
