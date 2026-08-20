// Triage drew the boundary in the wrong place: one task holding two jobs, or two tasks
// holding one. Same drawer for both, because it is the same question - "is this one job?" -
// and the answer is either "no, break it out" or "no, fold it in". Its own module because
// two places offer it: the Tasks header bar and the Timeline panel, like Handoff.
import React, { useEffect, useState } from "react";
import { Autocomplete, Box, Button, Checkbox, Chip, CircularProgress, TextField, Typography } from "@mui/material";
import CallSplitIcon from "@mui/icons-material/CallSplit";
import MergeIcon from "@mui/icons-material/MergeType";
import api from "./api";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, mono } from "./theme.jsx";

const msgOf = (e, fallback) => (e?.response?.status === 404
  ? "This needs the new server — restart Taskuary and try again."
  : e?.response?.data?.detail || fallback);

const Head = ({ icon, title, sub }) => (
  <Box sx={{ display: "flex", gap: 1, alignItems: "flex-start", mb: 1 }}>
    {icon}
    <Box sx={{ minWidth: 0 }}>
      <Typography sx={{ color: INK, fontWeight: 700, fontSize: 13 }}>{title}</Typography>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", lineHeight: 1.3 }}>{sub}</Typography>
    </Box>
  </Box>
);

const Section = ({ children }) => (
  <Box sx={{ bgcolor: PANEL, border: `1px solid ${BORDER}`, borderRadius: 2, p: 1.5, mb: 1.5 }}>{children}</Box>
);

export const Reshape = ({ taskId, taskRef, onDone }) => (
  <Box>
    <SplitInTwo taskId={taskId} taskRef={taskRef} onDone={onDone} />
    <FoldIntoAnother taskId={taskId} taskRef={taskRef} onDone={onDone} />
  </Box>
);

// The first half KEEPS this task - ref, session, report, history - so the fields are laid out
// in that order: what stays here, then what leaves.
const SplitInTwo = ({ taskId, taskRef, onDone }) => {
  const [sug, setSug] = useState(null);
  const [first, setFirst] = useState({ title: "", summary: "" });
  const [second, setSecond] = useState({ title: "", summary: "" });
  const [move, setMove] = useState([]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setSug(null); setDone(null); setErr(""); setMove([]);
    api.get(`/api/tasks/${taskId}/split/suggest`).then(({ data }) => {
      setSug(data); setFirst(data.first || { title: "", summary: "" }); setSecond(data.second || { title: "", summary: "" });
    }).catch((e) => { setSug({ messages: [] }); setErr(msgOf(e, "Could not read the task")); });
  }, [taskId]);
  const go = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/api/tasks/${taskId}/split`, { first, second, move_message_ids: move });
      setDone(data.ref); onDone?.({ split: data.taskId, ref: data.ref });
    } catch (e) { setErr(msgOf(e, "Could not break it in two")); }
    setBusy(false);
  };
  if (done) return (
    <Section>
      <Typography variant="body2" sx={{ color: "#15803d", fontWeight: 600 }}>
        ✓ broken in two — the second job is {done}. Send it to an agent from its own task.
      </Typography>
    </Section>
  );
  return (
    <Section>
      <Head icon={<CallSplitIcon sx={{ fontSize: 17, color: "#0e7490" }} />} title="Break it into two tasks"
        sub={`Two jobs filed as one. ${taskRef || "This task"} keeps its session, report and history — the second job starts clean.`} />
      {!sug ? <CircularProgress size={16} /> : (
        <>
          <Typography variant="caption" sx={{ color: sug.two ? "#0e7490" : FAINT, display: "block", mb: 1 }}>
            {sug.ai
              ? sug.two ? `The AI reads two jobs in here — ${sug.why}. Edit either side; nothing happens until you say so.`
                        : `The AI reads this as one job${sug.why ? ` — ${sug.why}` : ""}. Split it anyway if you disagree.`
              : sug.why}
          </Typography>
          <Typography variant="caption" sx={{ ...mono, color: FAINT, fontSize: 10 }}>① STAYS HERE</Typography>
          <TextField fullWidth size="small" sx={{ mt: 0.25, mb: 1 }} value={first.title}
            onChange={(e) => setFirst({ ...first, title: e.target.value })} placeholder="what this task is really about" />
          <Typography variant="caption" sx={{ ...mono, color: FAINT, fontSize: 10 }}>② BECOMES A NEW TASK</Typography>
          <TextField fullWidth size="small" sx={{ mt: 0.25, mb: 0.75 }} value={second.title} autoFocus={!!sug.two}
            onChange={(e) => setSecond({ ...second, title: e.target.value })} placeholder="the other job, in one line" />
          <TextField fullWidth multiline minRows={2} size="small" value={second.summary}
            onChange={(e) => setSecond({ ...second, summary: e.target.value })}
            placeholder="the part of the ask that belongs to it — the agent reads this" />
          {(sug.messages || []).length > 0 && (
            <Box sx={{ mt: 1, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 1, py: 0.5 }}>
              <Typography variant="caption" sx={{ color: DIM, fontWeight: 700 }}>Messages that move with it</Typography>
              {sug.messages.map((m) => (
                <Box key={m.message_id} sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
                  <Checkbox size="small" sx={{ p: 0.4 }} checked={move.includes(m.message_id)}
                    onChange={(e) => setMove((v) => e.target.checked ? [...v, m.message_id] : v.filter((x) => x !== m.message_id))} />
                  <Typography variant="caption" sx={{ color: INK, flex: 1, minWidth: 0 }} noWrap>
                    {m.from} · {m.subject || m.preview}
                  </Typography>
                </Box>
              ))}
              <Typography variant="caption" sx={{ color: FAINT, display: "block", pb: 0.5 }}>
                Tick nothing and the mail stays here — the new task carries the ask you wrote above.
              </Typography>
            </Box>
          )}
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", mt: 1.25 }}>
            <Button size="small" variant="contained" disableElevation disabled={busy || !second.title.trim()}
              startIcon={busy ? <CircularProgress size={11} sx={{ color: "#fff" }} /> : <CallSplitIcon sx={{ fontSize: 15 }} />}
              onClick={go}>Break it in two</Button>
            {err && <Typography variant="caption" sx={{ color: "#b91c1c" }}>{err}</Typography>}
          </Box>
        </>
      )}
    </Section>
  );
};

// The router's own signals, run backwards: whatever it nearly attached this to is the task it
// probably IS. Which one survives is the owner's call - the loser keeps its notes and a pointer.
const FoldIntoAnother = ({ taskId, taskRef, onDone }) => {
  const [cands, setCands] = useState(null);
  const [pick, setPick] = useState(null);
  const [keep, setKeep] = useState("other");     // which task survives the fold
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setCands(null); setPick(null); setDone(null); setErr("");
    api.get(`/api/tasks/${taskId}/merge-candidates`).then(({ data }) => setCands(data.data || [])).catch(() => setCands([]));
  }, [taskId]);
  const go = async () => {
    setBusy(true); setErr("");
    const [src, dst] = keep === "other" ? [taskId, pick.task_id] : [pick.task_id, taskId];
    try {
      const { data } = await api.post(`/api/tasks/${src}/merge`, { into: dst });
      setDone(data); onDone?.({ merged: dst, dropped: src, ref: data.ref });
    } catch (e) { setErr(msgOf(e, "Could not fold them together")); }
    setBusy(false);
  };
  if (done) return (
    <Section>
      <Typography variant="body2" sx={{ color: "#15803d", fontWeight: 600 }}>
        ✓ folded together — {done.ref} carries the work now
        {done.moved ? `, with ${done.moved} message${done.moved === 1 ? "" : "s"} moved over` : ""}.
      </Typography>
    </Section>
  );
  return (
    <Section>
      <Head icon={<MergeIcon sx={{ fontSize: 17, color: "#7e22ce" }} />} title="Fold it into another task"
        sub="One job filed twice. The messages move to the survivor; the other is dropped with a pointer at it — never deleted." />
      {!cands ? <CircularProgress size={16} /> : !cands.length ? (
        <Typography variant="caption" sx={{ color: FAINT }}>No other open task to fold into.</Typography>
      ) : (
        <>
          <Autocomplete size="small" options={cands} value={pick} onChange={(_e, v) => setPick(v)}
            getOptionLabel={(o) => `${o.ref} ${o.title}`}
            isOptionEqualToValue={(a, b) => a.task_id === b.task_id}
            renderOption={(props, o) => (
              <li {...props} style={{ display: "block", fontSize: 12.5 }}>
                <span style={{ ...mono, color: "#4f46e5", fontWeight: 700 }}>{o.ref}</span> {o.title}
                <div style={{ color: "#8a94a6", fontSize: 10.5 }}>{o.why} · match {o.score.toFixed(2)}</div>
              </li>
            )}
            renderInput={(params) => <TextField {...params} placeholder="the task this is really the same as" />} />
          {pick && (
            <Box sx={{ display: "flex", gap: 0.75, alignItems: "center", mt: 1, flexWrap: "wrap" }}>
              <Typography variant="caption" sx={{ color: DIM }}>Which one survives?</Typography>
              {[["other", `${pick.ref} — this one closes`], ["this", `${taskRef || "this task"} — ${pick.ref} closes`]].map(([k, label]) => (
                <Chip key={k} size="small" label={label} onClick={() => setKeep(k)}
                  sx={{ height: 20, fontSize: 10.5, cursor: "pointer",
                    bgcolor: keep === k ? "#eef0ff" : PANEL2, color: keep === k ? "#4f46e5" : DIM,
                    border: `1px solid ${keep === k ? "#c7d2fe" : BORDER}`, fontWeight: keep === k ? 700 : 400 }} />
              ))}
            </Box>
          )}
          <Box sx={{ display: "flex", gap: 1, alignItems: "center", mt: 1.25 }}>
            <Button size="small" variant="contained" disableElevation disabled={busy || !pick}
              startIcon={busy ? <CircularProgress size={11} sx={{ color: "#fff" }} /> : <MergeIcon sx={{ fontSize: 15 }} />}
              onClick={go}>Fold them together</Button>
            {err && <Typography variant="caption" sx={{ color: "#b91c1c" }}>{err}</Typography>}
          </Box>
          {pick && (
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.75 }}>
              A task an agent is working cannot be folded away underneath it — pause that session first.
            </Typography>
          )}
        </>
      )}
    </Section>
  );
};
