// ABOUT YOUR WORK, ONE QUESTION A SCREEN (the owner, 2026-10-16: "about your work is too much on one screen. ask one then hit next
// button ... let them fill out name/org/name of role/ then what they are responsible or job description should be prefilled using ai
// from their email and ask them if it's good description"). Name, organisation, title and systems, each filled from the mail where it
// can (firstrun.suggest_about) and never over what was typed; the title answered, JOB.md is written from the mail with them in hand
// (firstrun.learn) and the last screen asks whether it is right. No placeholder text: a box is either filled from the mail or empty.
// The row's Back and Next are this component's while it is on the canvas; the question is the Advisor's line (onLine).
import React, { useEffect, useRef, useState } from "react";
import { Box, Button, Chip, CircularProgress, TextField, Typography } from "@mui/material";
import api from "./api";
import { DIM } from "./theme.jsx";
import { useVerbs } from "./actionRow.js";
import { Md } from "./md.jsx";

const errText = (e) => e?.response?.data?.detail || e?.message || "That didn't work.";
export const STEPS = ["name", "org", "role", "signature", "systems", "job"];
const LABEL = { name: "Your name", org: "Your organisation", role: "Your job title", signature: "Your email signature",
  systems: "Systems you work in", job: "Your job" };
const ASK = {
  name: "What's your name?", org: "What organisation do you work for?",
  role: "What's your job title? Next, I write your job description from your email.",
  // the block under every email Taskuary writes - read off the sent mail, checked here (the owner, 2026-10-16: "pull the signature
  // from the email and use that in emails ... have a setting so they can check it that it looks good")
  signature: "Is this your email signature? It goes under every email Taskuary writes for you, exactly like this - fix anything that's off.",
  systems: "Which systems do you work in? The ones ticked came up in your email - add any that are missing.",
};
const who = (a) => JSON.stringify([a.name, a.org, a.role].map((x) => (x || "").trim()));

export default function FirstRunAbout({ onSaved, onBack, onLine, again = false }) {
  const [a, setA] = useState(null), [offered, setOffered] = useState([]), [seen, setSeen] = useState([]), [all, setAll] = useState(false);
  const [at, setAt] = useState(0), [reading, setReading] = useState(false), [note, setNote] = useState("");
  const [busy, setBusy] = useState(""), [err, setErr] = useState(""), [other, setOther] = useState("");
  const [job, setJob] = useState({ state: "none", why: "", text: "" }), [jobText, setJobText] = useState(""), [edited, setEdited] = useState(false);
  const [editing, setEditing] = useState(false);       // the job is read as a document; Edit opens its text
  const touched = useRef(new Set()), learnedFor = useRef("");
  useEffect(() => {
    let on = true;
    api.get("/api/setup/first-run/about").then(async ({ data }) => {
      if (!on) return;
      const got = { name: data.name || "", org: data.org || "", role: data.role || "", signature: data.signature || "", systems: data.systems || [] };
      setOffered(data.offered || []); setA(got); setSeen(got.systems);
      // answered before and a job already written for those answers: no need to write it again unless one of them changes
      if (data.done && data.job) { learnedFor.current = who(got); setJob({ state: "ready", why: "", text: data.job }); setJobText(data.job); }
      if (data.done && data.org && data.role) return;
      // what the mail says, for every box not typed in - the name guessed from the address included
      setReading(true);
      try {
        const { data: s } = await api.post("/api/setup/first-run/about/suggest", {}, { timeout: 180_000 });
        if (!on) return;
        if (s.error) setNote(`I couldn't fill these in from your email (${s.error}) - type them in.`);
        else {
          // a box the owner answered - now or before - is theirs; only an empty one, or the name guessed from the address, takes the mail's
          setA((x) => ({ ...x, ...Object.fromEntries(["name", "org", "role", "signature"].filter((k) => !touched.current.has(k) && s[k]
            && (!x[k] || (data.guessed || []).includes(k))).map((k) => [k, s[k]])),
            systems: touched.current.has("systems") || x.systems.length ? x.systems : s.systems || [] }));
          setSeen((x) => [...new Set([...x, ...(s.systems || [])])]);
        }
      } catch (e) { if (on) setNote(`I couldn't fill these in from your email (${errText(e)}) - type them in.`); }
      if (on) setReading(false);
    }).catch((e) => on && setErr(errText(e)));
    return () => { on = false; };
  }, []);
  // the job being written: read again every few seconds until it is ready or says why not
  useEffect(() => {
    if (job.state !== "running") return undefined;
    const id = setTimeout(() => api.get("/api/setup/first-run/about/job").then(({ data }) => {
      setJob(data);
      if (data.state === "ready" && !edited) setJobText(data.text);
    }).catch(() => setJob((j) => ({ ...j })) ), 3000);
    return () => clearTimeout(id);
  }, [job, edited]);
  const step = STEPS[at];
  const learn = async (x = a) => {
    learnedFor.current = who(x); setEdited(false); setJob({ state: "running", why: "", text: "" });
    try { setJob((await api.post("/api/setup/first-run/about/learn", x)).data); }
    catch (e) { setJob({ state: "failed", why: errText(e), text: "" }); }
  };
  const save = async () => {
    setBusy("save"); setErr("");
    try { await api.post("/api/setup/first-run/about", { ...a, job: job.state === "ready" || edited ? jobText : "" }); onSaved?.(); }
    catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  const skip = async () => {
    setBusy("skip"); setErr("");
    try { await api.post("/api/setup/first-run/about/skip"); onSaved?.(); } catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  const next = () => {
    setErr("");
    if (step === "role" && who(a) !== learnedFor.current) learn();     // written while the systems are picked
    if (step === "job") return save();
    setAt((i) => Math.min(i + 1, STEPS.length - 1));
  };
  const back = () => (at ? setAt(at - 1) : onBack?.());
  const ready = !!a && (step !== "job" || job.state !== "running");
  const last = step === "job";
  useVerbs("setup-about", a ? [
    { id: "about:back", group: "next", tone: "s", label: "Back", title: at ? "The question before" : "Your email", run: back },
    { id: "about:next", group: "decide", tone: "p", disabled: !ready || !!busy, why: step === "job" ? "your job description is still being written" : "",
      label: last ? (busy === "save" ? "Saving…" : job.state === "ready" ? "Looks right" : "Save") : "Next",
      title: last ? "Saved to what Taskuary knows about you - change it any time in Settings" : "The next question", run: next },
  ] : [], !!a);
  // the question is the Advisor's line over the row
  const line = !a ? "" : step === "job"
    ? job.state === "running" ? "Reading three months of your email to write your job description - about a minute."
      : job.state === "failed" ? `I couldn't write it from your email (${job.why}). Press Write it again, or say it in your own words.`
        : job.state === "ready" ? "This is your job as your email describes it. Is it right? Edit anything that's wrong, then press Looks right."
          : "Press Write it - I read your email and describe your job."
    : `${ASK[step]}${reading && step !== "systems" ? " I'm reading your email to fill this in." : ""}`;
  useEffect(() => { onLine?.(line); }, [line, onLine]);
  useEffect(() => () => onLine?.(""), [onLine]);
  if (!a) return err ? <Typography sx={{ color: "#9b2c2c", fontSize: 13 }}>{err}</Typography> : <CircularProgress size={16} />;

  const set = (k) => (e) => { touched.current.add(k); setA((x) => ({ ...x, [k]: e.target.value })); };
  const has = (s) => a.systems.includes(s);
  const toggle = (s) => { touched.current.add("systems"); setA((x) => ({ ...x, systems: has(s) ? x.systems.filter((y) => y !== s) : [...x.systems, s] })); };
  const addOther = () => {
    const v = other.trim();
    if (v && !has(v)) { touched.current.add("systems"); setA((x) => ({ ...x, systems: [...x.systems, v] })); setSeen((x) => [...new Set([...x, v])]); }
    setOther("");
  };
  const field = { "& .MuiInputBase-root": { fontSize: 15, bgcolor: "#fff" } };
  const enter = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); next(); } };
  const shown = all ? [...new Set([...seen, ...offered])] : seen;
  return (
    <Box data-tq-firstrun-about={step} sx={{ display: "flex", flexDirection: "column", gap: 1.25, maxWidth: 760 }}>
      <Typography sx={{ color: DIM, fontSize: 12 }}>About your work · {at + 1} of {STEPS.length}</Typography>
      <Typography sx={{ fontSize: 15, fontWeight: 600 }}>{LABEL[step]}</Typography>
      {["name", "org", "role"].includes(step) && <>
        <TextField key={step} size="small" fullWidth autoFocus value={a[step]} onChange={set(step)} onKeyDown={enter} sx={field}
          inputProps={{ "aria-label": LABEL[step] }} />
        {reading && !a[step] && <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}><CircularProgress size={13} />
          <Typography sx={{ color: DIM, fontSize: 13 }}>Reading your email to fill this in - you can type it yourself.</Typography></Box>}
      </>}
      {step === "signature" && <>
        <TextField multiline fullWidth minRows={4} value={a.signature || ""} onChange={set("signature")} sx={{ ...field, "& textarea": { fontSize: 14 } }}
          inputProps={{ "aria-label": LABEL.signature }} />
        {reading && !a.signature && <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}><CircularProgress size={13} />
          <Typography sx={{ color: DIM, fontSize: 13 }}>Reading your sent mail for it…</Typography></Box>}
        <Typography sx={{ color: DIM, fontSize: 12 }}>How it sits under an email:</Typography>
        <Box data-tq-signature-preview="" sx={{ border: "1px solid #ddd5c6", borderRadius: 1.5, bgcolor: "#fff", px: 2, py: 1.25, fontSize: 13.5,
          whiteSpace: "pre-line", color: "#2b2b2b", maxWidth: 520 }}>
          {"Hi Erin,\n\nThanks - that's done.\n\n"}{(a.signature || "").trim() || <span style={{ color: DIM }}>(no signature - leave it blank and drafts sign the way your writing style does)</span>}
        </Box>
      </>}
      {step === "systems" && <>
        {reading && <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}><CircularProgress size={13} />
          <Typography sx={{ color: DIM, fontSize: 13 }}>Reading your email for the systems you use…</Typography></Box>}
        {shown.length > 0 && <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.6 }}>
          {shown.map((s) => <Chip key={s} label={s} size="small" clickable onClick={() => toggle(s)}
            color={has(s) ? "primary" : "default"} variant={has(s) ? "filled" : "outlined"} />)}
        </Box>}
        <Box sx={{ display: "flex", gap: 1, maxWidth: 460, alignItems: "center" }}>
          <TextField size="small" fullWidth value={other} onChange={(e) => setOther(e.target.value)} sx={field}
            inputProps={{ "aria-label": "Another system" }} onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addOther(); } }} />
          <Button size="small" onClick={addOther} disabled={!other.trim()} sx={{ whiteSpace: "nowrap" }}>Add a system</Button>
        </Box>
        <Box><Button size="small" sx={{ color: DIM, fontSize: 12.5 }} onClick={() => setAll((v) => !v)}>
          {all ? "Show only mine" : "Show the full list"}</Button></Box>
      </>}
      {step === "job" && (job.state === "running" ? (
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}><CircularProgress size={14} />
          <Typography sx={{ color: DIM, fontSize: 13.5 }}>Writing your job description from your email…</Typography></Box>
      ) : <>
        {/* READ AS A DOCUMENT, not its markdown (the owner, 2026-10-16: the box showed "### What my job is"): Edit opens the text */}
        {editing || !jobText.trim()
          ? <TextField multiline fullWidth minRows={10} maxRows={22} value={jobText} sx={{ ...field, "& textarea": { fontSize: 14, lineHeight: 1.5 } }}
            onChange={(e) => { setEdited(true); setJobText(e.target.value); }} inputProps={{ "aria-label": "Your job" }} autoFocus={editing} />
          : <Box data-tq-job-read="" sx={{ border: "1px solid #ddd5c6", borderRadius: 1.5, bgcolor: "#fff", px: 2, py: 1, maxHeight: "52vh", overflowY: "auto",
              "& h3": { fontSize: 14.5, fontWeight: 700, mt: 1.5, mb: 0.5 }, "& h3:first-of-type": { mt: 0.5 }, "& ul": { pl: 2.5, my: 0.5 },
              "& li": { fontSize: 14, lineHeight: 1.55, mb: 0.4 } }}><Md text={jobText} /></Box>}
        <Box sx={{ display: "flex", gap: 1 }}>
          {jobText.trim() && <Button size="small" onClick={() => setEditing((v) => !v)}>{editing ? "Done editing" : "Edit"}</Button>}
          <Button size="small" onClick={() => { setEditing(false); learn(); }} disabled={!!busy}>{job.state === "none" ? "Write it" : "Write it again"}</Button>
        </Box>
      </>)}
      {note && step !== "job" && <Typography sx={{ color: DIM, fontSize: 13 }}>{note}</Typography>}
      {err && <Typography sx={{ color: "#9b2c2c", fontSize: 13 }}>{err}</Typography>}
      {!again && <Box><Button size="small" disabled={!!busy} onClick={skip} sx={{ color: DIM, fontSize: 12.5 }}>Skip these questions</Button></Box>}
    </Box>
  );
}
