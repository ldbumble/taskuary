// NEW → MEETING (the owner, 2026-10-28: "probably new meeting screen is better"): who, what, how long and roughly when; Find times reads the
// owner's calendar and the attendees' where the provider answers for them (calwrite.suggest), and a pick DRAFTS the invite on a task of its
// own whose Close out holds it with Send (calwrite.draft_new) - the same road a thread's Find a time takes. Nothing reaches a calendar here.
// No calendar, or one that may not be written to: the server's one line with its sign-in as the way out, as Find a time does.
import React, { useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, TextField, Typography } from "@mui/material";
import api from "./api";
import { ACCENT, ACCENT2, BORDER, DIM, FAINT, GRADIENT, INK, mono } from "./theme.jsx";
import { label as btn } from "./buttons.js";
import { openAppLink } from "./appLinks.js";
import { FOCUS_RING, pressable } from "./pressable.js";
import { LENGTHS, WITHIN, canFind, formFrom, seenLine, slotsUrl, typedSlot } from "./meetingForm.js";

const Label = ({ children }) => (
  <Typography sx={{ ...mono, fontSize: 9.5, fontWeight: 600, letterSpacing: ".11em", textTransform: "uppercase", color: ACCENT2, mb: 0.75 }}>{children}</Typography>
);
const FIELD = { "& .MuiInputBase-root": { fontSize: 13, bgcolor: "#fcfaf7" } };
const Pick = ({ on, children, onPress, ...rest }) => (
  <Box {...pressable(onPress)} aria-pressed={on} {...rest}
    sx={{ ...FOCUS_RING, px: 1.25, py: 0.6, borderRadius: 2, cursor: "pointer", fontSize: 12.5, fontWeight: 600, whiteSpace: "nowrap",
      border: `1px solid ${on ? ACCENT : BORDER}`, boxShadow: on ? `inset 0 0 0 1px ${ACCENT}` : "none", color: on ? INK : DIM, bgcolor: on ? "#fff" : "#fcfaf7" }}>
    {children}</Box>
);
const dateBox = { font: "inherit", fontSize: 13, padding: "5px 8px", borderRadius: 6, border: `1px solid ${BORDER}`, background: "#fcfaf7", minWidth: 0 };

export default function NewMeeting({ renderTo, options = [], initial, onPicked }) {
  const [f, setF] = useState(() => formFrom(initial || {}));
  const set = (k) => (v) => setF((x) => ({ ...x, [k]: v }));
  const [got, setGot] = useState(null);        // the free times the server offered
  const [busy, setBusy] = useState("");        // "find" | the slot being drafted
  const [no, setNo] = useState(null);          // {say, fix}: nothing could be read or drafted
  const [err, setErr] = useState("");
  const [day, setDay] = useState(""), [time, setTime] = useState("");
  // ...the times were for these people, this length and these days - any change and they are not what is on the screen any more
  useEffect(() => { setGot(null); }, [f.to.join(","), f.minutes, f.within, f.from, f.until]);   // eslint-disable-line react-hooks/exhaustive-deps

  const find = async () => {
    setBusy("find"); setNo(null); setErr(""); setGot(null);
    try { const { data } = await api.get(slotsUrl(f)); if (data?.ok === false) setNo(data); else setGot(data); }
    catch (e) { setErr(e?.response?.data?.detail || e?.message || "Your calendar could not be read"); }
    setBusy("");
  };
  const pick = async (s) => {
    if (!s) return;
    setBusy(s.start); setNo(null); setErr("");
    try {
      const { data } = await api.post("/api/meetings", { to: f.to, subject: f.subject.trim(), start: s.start, end: s.end, note: f.note });
      if (data?.ok === false) setNo(data); else { onPicked?.(data); setGot(null); }
    } catch (e) { setErr(e?.response?.data?.detail || e?.message || "The invite could not be drafted"); }
    setBusy("");
  };
  const typed = typedSlot(day, time, f.minutes);
  const seen = seenLine(got);

  return (
    <Box data-tq-meeting="" sx={{ display: "grid", gap: 2, minWidth: 0 }}>
      <Box>
        <Label>With</Label>
        {renderTo({ value: f.to, onChange: set("to"), options, placeholder: "Search people or type an email address" })}
        {!!f.unplaced.length && <Typography sx={{ fontSize: 11.5, color: FAINT, mt: 0.5 }}>
          Could not place {f.unplaced.join(", ")} - search for them above or type their address.</Typography>}
      </Box>
      <Box>
        <Label>About</Label>
        <TextField fullWidth size="small" value={f.subject} onChange={(e) => set("subject")(e.target.value)} placeholder="the Q3 budget" inputProps={{ "data-tq-meeting-subject": "" }} sx={FIELD} />
      </Box>
      <Box sx={{ display: "flex", gap: 2.5, flexWrap: "wrap" }}>
        <Box>
          <Label>How long</Label>
          <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
            {LENGTHS.map((m) => <Pick key={m} on={f.minutes === m} onPress={() => set("minutes")(m)} data-tq-length={m}>{m} min</Pick>)}
          </Box>
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <Label>When</Label>
          <Box sx={{ display: "flex", gap: 0.75, flexWrap: "wrap" }}>
            {WITHIN.map((w) => <Pick key={w.key} on={f.within === w.key} onPress={() => set("within")(w.key)} data-tq-within={w.key || "soon"}>{w.label}</Pick>)}
          </Box>
          {f.within === "range" && <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap", mt: 1, fontSize: 12, color: DIM }}>
            <input type="date" aria-label="From" value={f.from} onChange={(e) => setF((x) => ({ ...x, from: e.target.value, until: x.until && x.until >= e.target.value ? x.until : e.target.value }))} style={dateBox} />
            to
            <input type="date" aria-label="Until" min={f.from || undefined} value={f.until} onChange={(e) => set("until")(e.target.value)} style={dateBox} />
          </Box>}
        </Box>
      </Box>
      <Box>
        <Label>Note or agenda</Label>
        <TextField fullWidth multiline minRows={2} size="small" value={f.note} onChange={(e) => set("note")(e.target.value)}
          placeholder="Optional - it goes in the invite" sx={FIELD} />
      </Box>
      <Box sx={{ display: "flex", gap: 1.25, alignItems: "center", flexWrap: "wrap" }}>
        <Button size="small" variant="contained" disableElevation data-tq-find-times="" disabled={!canFind(f) || !!busy} onClick={find}
          startIcon={busy === "find" ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : null} sx={{ background: GRADIENT }}>
          {busy === "find" ? "Reading calendars…" : "Find times"}</Button>
        <Typography sx={{ fontSize: 11.5, color: FAINT, flex: "1 1 200px" }}>Your calendar, and theirs where it is shared with you. Nothing is sent.</Typography>
      </Box>

      {got && <Box data-tq-meeting-slots="" sx={{ border: `1px solid ${BORDER}`, borderRadius: 2, p: 1.5, display: "grid", gap: 1, bgcolor: "#fff", minWidth: 0 }}>
        <Typography sx={{ fontSize: 12.5, fontWeight: 600, color: INK }}>
          {got.slots?.length ? `${got.minutes} minutes - pick a time` : "No free time in those days - type one below."}</Typography>
        {got.later && !!got.slots?.length && <Typography sx={{ fontSize: 11.5, color: FAINT }}>Those days are full - these are the next free times after them.</Typography>}
        {!!seen && <Typography data-tq-meeting-seen="" sx={{ fontSize: 11.5, color: FAINT }}>{seen}</Typography>}
        <Box sx={{ display: "grid", gap: 0.75, gridTemplateColumns: { xs: "1fr", sm: "repeat(auto-fill, minmax(220px, 1fr))" } }}>
          {(got.slots || []).map((s) => (
            <Button key={s.start} size="small" variant="outlined" data-tq-slot={s.start} disabled={!!busy} onClick={() => pick(s)}
              startIcon={busy === s.start ? <CircularProgress size={12} /> : null}
              sx={{ justifyContent: "flex-start", fontSize: 12.5, minHeight: 34, textTransform: "none" }}>{s.label}</Button>
          ))}
        </Box>
        <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap", fontSize: 12, color: DIM }}>
          Or type one
          <input type="date" aria-label="Day" value={day} onChange={(e) => setDay(e.target.value)} style={dateBox} />
          <input type="time" aria-label="Time" value={time} onChange={(e) => setTime(e.target.value)} style={dateBox} />
          <Button size="small" disabled={!typed || !!busy} onClick={() => pick(typed)} data-tq-slot-typed="">Use this time</Button>
        </Box>
        <Typography sx={{ fontSize: 11, color: FAINT }}>A pick drafts the invite on a task of its own - it waits in Close out for your {btn("approve")}.</Typography>
      </Box>}

      {no && <Alert severity="warning" sx={{ py: 0.25, fontSize: 12.5, alignItems: "center" }}
        action={no.fix ? <Button size="small" onClick={() => openAppLink(no.fix.href)} data-tq-meeting-fix="">{no.fix.label}</Button> : null}>{no.say}</Alert>}
      {err && <Alert severity="error" sx={{ py: 0.25, fontSize: 12.5 }}>{err}</Alert>}
    </Box>
  );
}
