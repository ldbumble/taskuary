// ABOUT YOUR WORK, the first run's fourth question (the owner, 2026-10-15: "a few short question on setup screen to fill out soul.md
// and job.md (though you can generate as much as possible from history). They should be short to fill out basic map of their
// job/soul ... we only have repo's in the soul.md not what other corporate system connectors they have for non technical people ...
// forgot to ask for their name"). Five answers, suggested from the mail where the form is still blank, saved into SOUL.md (the systems)
// and JOB.md (role, what they own, who they work with) by firstrun.save_about - and STYLE.md is learned from the sent mail behind it.
import React, { useEffect, useState } from "react";
import { Box, Button, Chip, CircularProgress, TextField, Typography } from "@mui/material";
import api from "./api";
import { DIM } from "./theme.jsx";

const errText = (e) => e?.response?.data?.detail || e?.message || "That didn't work.";
const blank = (a) => !a.role && !a.owns && !a.people && !(a.systems || []).length;

export default function FirstRunAbout({ onSaved, again = false }) {
  const [a, setA] = useState(null), [offered, setOffered] = useState([]);
  const [reading, setReading] = useState(false), [busy, setBusy] = useState(""), [err, setErr] = useState(""), [note, setNote] = useState("");
  const [other, setOther] = useState("");
  useEffect(() => {
    let on = true;
    api.get("/api/setup/first-run/about").then(async ({ data }) => {
      if (!on) return;
      setOffered(data.offered || []);
      setA({ name: data.name, role: data.role, owns: data.owns, people: data.people, systems: data.systems || [] });
      if (!blank(data)) return;
      // what the mail says, for the boxes still blank - never over what was typed
      setReading(true);
      try {
        const { data: s } = await api.post("/api/setup/first-run/about/suggest", {}, { timeout: 180_000 });
        if (!on) return;
        if (s.error) setNote(`I couldn't fill these in from your email (${s.error}) - type them, or skip.`);
        else setA((x) => ({ ...x, role: x.role || s.role || "", owns: x.owns || s.owns || "", people: x.people || s.people || "",
          systems: x.systems?.length ? x.systems : s.systems || [] }));
      } catch (e) { if (on) setNote(`I couldn't fill these in from your email (${errText(e)}) - type them, or skip.`); }
      if (on) setReading(false);
    }).catch((e) => on && setErr(errText(e)));
    return () => { on = false; };
  }, []);
  if (!a) return err ? <Typography sx={{ color: "#9b2c2c", fontSize: 13 }}>{err}</Typography> : <CircularProgress size={16} />;
  const set = (k) => (e) => setA((x) => ({ ...x, [k]: e.target.value }));
  const has = (s) => a.systems.includes(s);
  const toggle = (s) => setA((x) => ({ ...x, systems: has(s) ? x.systems.filter((y) => y !== s) : [...x.systems, s] }));
  const addOther = () => { const v = other.trim(); if (v && !has(v)) setA((x) => ({ ...x, systems: [...x.systems, v] })); setOther(""); };
  const save = async () => {
    setBusy("save"); setErr("");
    try { await api.post("/api/setup/first-run/about", a); onSaved?.(); } catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  const skip = async () => {
    setBusy("skip"); setErr("");
    try { await api.post("/api/setup/first-run/about/skip"); onSaved?.(); } catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  const field = { "& .MuiInputBase-root": { fontSize: 14, bgcolor: "#fff" } };
  const label = { fontSize: 12.5, fontWeight: 600, mb: 0.4 };
  const extra = a.systems.filter((s) => !offered.includes(s));
  return (
    <Box data-tq-firstrun-about="" sx={{ display: "flex", flexDirection: "column", gap: 1.6, maxWidth: 760 }}>
      {reading && <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}><CircularProgress size={14} />
        <Typography sx={{ color: DIM, fontSize: 13.5 }}>Reading your email to fill these in - about a minute. You can start typing.</Typography></Box>}
      {note && <Typography sx={{ color: DIM, fontSize: 13 }}>{note}</Typography>}
      <Box><Typography sx={label}>Your name</Typography>
        <TextField size="small" fullWidth value={a.name} onChange={set("name")} placeholder="Alex Doyle" sx={field} /></Box>
      <Box><Typography sx={label}>Your role</Typography>
        <TextField size="small" fullWidth value={a.role} onChange={set("role")} placeholder="Finance systems lead at Northwind" sx={field} /></Box>
      <Box><Typography sx={label}>What you're responsible for</Typography>
        <TextField size="small" fullWidth multiline minRows={2} value={a.owns} onChange={set("owns")}
          placeholder="Month-end close, vendor payments, the payroll systems" sx={field} /></Box>
      <Box><Typography sx={label}>Systems you work in</Typography>
        <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.6 }}>
          {[...offered, ...extra].map((s) => <Chip key={s} label={s} size="small" clickable onClick={() => toggle(s)}
            color={has(s) ? "primary" : "default"} variant={has(s) ? "filled" : "outlined"} />)}
        </Box>
        <Box sx={{ display: "flex", gap: 1, mt: 0.8, maxWidth: 420 }}>
          <TextField size="small" fullWidth value={other} onChange={(e) => setOther(e.target.value)} placeholder="Another one - type it and press Add"
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addOther(); } }} sx={field} />
          <Button size="small" onClick={addOther} disabled={!other.trim()}>Add</Button>
        </Box></Box>
      <Box><Typography sx={label}>Who you work with most</Typography>
        <TextField size="small" fullWidth value={a.people} onChange={set("people")} placeholder="Erin Blake, Gail Moreno" sx={field} /></Box>
      {err && <Typography sx={{ color: "#9b2c2c", fontSize: 13 }}>{err}</Typography>}
      <Box sx={{ display: "flex", gap: 1, alignItems: "center", flexWrap: "wrap" }}>
        <Button variant="contained" disableElevation disabled={!!busy} onClick={save}>{busy === "save" ? "Saving…" : again ? "Save" : "Save and continue"}</Button>
        {!again && <Button disabled={!!busy} onClick={skip} sx={{ color: DIM }}>Skip</Button>}
        <Typography sx={{ color: DIM, fontSize: 12 }}>Saved into SOUL.md and JOB.md - edit them any time under Settings → Docs.</Typography>
      </Box>
    </Box>
  );
}
