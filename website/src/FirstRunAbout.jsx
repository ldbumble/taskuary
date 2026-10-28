// ABOUT YOUR WORK, ONE QUESTION A SCREEN (the owner, 2026-10-16: "about your work is too much on one screen. ask one then hit next
// button ... let them fill out name/org/name of role/ then what they are responsible or job description should be prefilled using ai
// from their email and ask them if it's good description"). Name, organisation, title and systems, each filled from the mail where it
// can (firstrun.suggest_about) and never over what was typed; the title answered, JOB.md is written from the mail with them in hand
// (firstrun.learn) and the last screen asks whether it is right. No placeholder text: a box is either filled from the mail or empty.
// The row's Back and Next are this component's while it is on the canvas; the question is the Advisor's line (onLine).
// EVERY SOURCE BEFORE THE JOB (the owner, 2026-10-20; any source, 2026-10-21): the job is read out of what comes in, so a step lists the
// sources connected so far - mailboxes, chats, task systems (firstrun.sources) - and adds the rest with the main source step's own
// cards (FirstRun hands its shelf in as `mailShelf`). It is never skipped - Skip on a question before it lands on it - and
// "That's all my sources" moves on once one is connected.
// ...AND THREE DRAFTS, each written from the mail, edited, then accepted: the job (JOB.md), how you write (STYLE.md - it was written
// silently after the job and its failure only logged) and who you are (SOUL.md). Each says its state, and a failure is said with
// Write it again.
import React, { useEffect, useRef, useState } from "react";
import { Box, Button, Chip, CircularProgress, TextField, Typography } from "@mui/material";
import api from "./api";
import { DIM } from "./theme.jsx";
import { useVerbs } from "./actionRow.js";
import { Md } from "./md.jsx";

const errText = (e) => e?.response?.data?.detail || e?.message || "That didn't work.";
export const STEPS = ["name", "org", "role", "signature", "systems", "mailboxes", "job", "style", "soul"];
export const MAIL_AT = STEPS.indexOf("mailboxes");
// Skip before the mailbox step lands on it; on it there is no Skip; past it, Skip leaves the rest (null)
export const skipTo = (at) => (at < MAIL_AT ? MAIL_AT : null);
export const canSkip = (step) => step !== "mailboxes";
export const DRAFTS = ["job", "style", "soul"];
const KIND = { outlook: "Microsoft 365 / Outlook", gmail: "Gmail", imap: "Email (IMAP)" };
const LABEL = { name: "Your name", org: "Your organisation", role: "Your job title", signature: "Your email signature",
  systems: "Systems you work in", mailboxes: "Connect your sources", job: "Your job", style: "How you write", soul: "Who you are" };
const ASK = {
  name: "What's your name?", org: "What organisation do you work for?",
  role: "What's your job title? Next, I write your job description from your email.",
  // the block under every email Taskuary writes - read off the sent mail, checked here (the owner, 2026-10-16: "pull the signature
  // from the email and use that in emails ... have a setting so they can check it that it looks good")
  signature: "Is this your email signature? It goes under every email Taskuary writes for you, exactly like this - fix anything that's off.",
  systems: "Which systems do you work in? The ones ticked came up in your email - add any that are missing.",
  // short enough that the line still names the button at 1440 px - it ran out past "Th…" (the setup sweep, 2026-10-27)
  mailboxes: "Add any other place your work comes in with its card - your job is read from all of them.",
};
// each draft's line, by its state - the job's as it was, the other two in the same words
const SAYS = {
  job: { running: "Reading three months of your email to write your job description - about a minute.",
    failed: (why) => `I couldn't write it from your email (${why}). Press Write it again, or say it in your own words.`,
    ready: "This is your job as your email describes it. Is it right? Edit anything that's wrong, then press Looks right.",
    none: "Press Write it - I read your email and describe your job.", busy: "Writing your job description from your email…" },
  style: { running: "Reading your sent mail to describe how you write - about a minute.",
    failed: (why) => `I couldn't write it from your sent mail (${why}). Press Write it again, or describe it in your own words.`,
    ready: "This is how you write, as your sent mail shows it. Edit anything that's off, then press Looks right.",
    none: "Press Write it - I read your sent mail and describe how you write.", busy: "Describing how you write from your sent mail…" },
  soul: { running: "Reading your mail and your answers to describe how you like to work - about a minute.",
    failed: (why) => `I couldn't write it from your mail (${why}). Press Write it again, or say it in your own words.`,
    ready: "This is how you like to work, from your mail and your answers. Edit anything that's off, then press Looks right.",
    none: "Press Write it - I describe how you like to work from your mail and your answers.", busy: "Describing how you like to work…" },
};
const NONE = { state: "none", why: "", text: "" };
// what the job was written from: the answers and every mailbox it read - one added since is a reason to write it again
const who = (a, boxes = []) => JSON.stringify([...[a.name, a.org, a.role].map((x) => (x || "").trim()), ...boxes.map((b) => b.address.toLowerCase()).sort()]);

export default function FirstRunAbout({ onSaved, onBack, onLine, onStep, again = false, mailboxes = [], mailShelf = null, hidden = false }) {
  const [a, setA] = useState(null), [offered, setOffered] = useState([]), [seen, setSeen] = useState([]), [all, setAll] = useState(false);
  const [at, setAt] = useState(0), [reading, setReading] = useState(false), [note, setNote] = useState("");
  const [busy, setBusy] = useState(""), [err, setErr] = useState(""), [other, setOther] = useState("");
  // the three drafts: {state, why, text} as the server has them, the text as the owner left it, which they changed, which is open
  const [drafts, setDrafts] = useState({ job: NONE, style: NONE, soul: NONE }), [texts, setTexts] = useState({ job: "", style: "", soul: "" });
  const [edited, setEdited] = useState({}), [editing, setEditing] = useState("");      // read as a document; Edit opens its text
  const touched = useRef(new Set()), learnedFor = useRef(""), editedRef = useRef({});
  editedRef.current = edited;
  // what came back: each draft's state, and its text wherever the owner has not typed over it
  const took = (ds) => {
    setDrafts((x) => ({ ...x, ...ds }));
    setTexts((x) => ({ ...x, ...Object.fromEntries(Object.entries(ds).filter(([k, d]) => d.state === "ready" && !editedRef.current[k]).map(([k, d]) => [k, d.text])) }));
  };
  useEffect(() => {
    let on = true;
    api.get("/api/setup/first-run/about").then(async ({ data }) => {
      if (!on) return;
      const got = { name: data.name || "", org: data.org || "", role: data.role || "", signature: data.signature || "", systems: data.systems || [] };
      setOffered(data.offered || []); setA(got); setSeen(got.systems);
      // answered before and drafts already written for those answers: no need to write them again unless one of them changes
      if (data.done && data.job) learnedFor.current = who(got, mailboxes);
      if (data.done) took(Object.fromEntries(DRAFTS.filter((k) => data[k]).map((k) => [k, { state: "ready", why: "", text: data[k] }])));
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
  // a draft being written: read again every few seconds until each is ready or says why not
  const writing = DRAFTS.some((k) => drafts[k].state === "running");
  useEffect(() => {
    if (!writing) return undefined;
    const id = setTimeout(() => api.get("/api/setup/first-run/about/drafts").then(({ data }) => took(data)).catch(() => setDrafts((d) => ({ ...d }))), 3000);
    return () => clearTimeout(id);
  }, [drafts, writing]);
  const step = STEPS[at], draft = DRAFTS.includes(step) ? drafts[step] : null;
  useEffect(() => { onStep?.(step); }, [step, onStep]);
  useEffect(() => () => onStep?.(""), [onStep]);
  const boxes = mailboxes.length;
  // write these drafts from the mail (the job also from the answers, which are saved on the way)
  const learn = async (docs = DRAFTS, x = a) => {
    if (!docs.length) return;
    if (docs.includes("job")) learnedFor.current = who(x, mailboxes);
    setEdited((e) => ({ ...e, ...Object.fromEntries(docs.map((k) => [k, false])) }));
    setDrafts((d) => ({ ...d, ...Object.fromEntries(docs.map((k) => [k, { state: "running", why: "", text: "" }])) }));
    try { took((await api.post("/api/setup/first-run/about/learn", { ...x, docs })).data.drafts || {}); }
    catch (e) { setDrafts((d) => ({ ...d, ...Object.fromEntries(docs.map((k) => [k, { state: "failed", why: errText(e), text: "" }])) })); }
  };
  // a draft as the owner left it, kept: only when it was written or they wrote it themselves
  const accept = (k) => (drafts[k].state === "ready" || edited[k]) && texts[k].trim()
    ? api.post("/api/setup/first-run/about/accept", { doc: k, text: texts[k] }) : Promise.resolve();
  const save = async () => {
    setBusy("save"); setErr("");
    try { await accept("soul"); await api.post("/api/setup/first-run/about", { ...a, job: drafts.job.state === "ready" || edited.job ? texts.job : "" }); onSaved?.(); }
    catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  const skip = async () => {
    setErr("");
    const to = skipTo(at);
    if (to !== null) return setAt(to);              // never past the mailboxes: Skip lands on them
    setBusy("skip");
    try { await api.post("/api/setup/first-run/about/skip"); onSaved?.(); } catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  const next = async () => {
    setErr(""); setEditing("");
    if (step === "role" && who(a, mailboxes) !== learnedFor.current) learn(["job"]);     // written while the systems are picked
    // ...and all three once every mailbox is in - the job again only when a mailbox (or an answer) changed since it was written
    if (step === "mailboxes") learn(who(a, mailboxes) !== learnedFor.current ? DRAFTS : DRAFTS.filter((k) => k !== "job" && drafts[k].state === "none"));
    if (step === "soul") return save();
    if (draft) {
      setBusy("save");
      try { await accept(step); } catch (e) { setBusy(""); return setErr(errText(e)); }
      setBusy("");
    }
    setAt((i) => Math.min(i + 1, STEPS.length - 1));
  };
  const back = () => { setEditing(""); return at ? setAt(at - 1) : onBack?.(); };
  const ready = !!a && (!draft || draft.state !== "running") && (step !== "mailboxes" || boxes > 0);
  const last = step === "soul";
  // THE ONE LIT MOVE (FirstRun.jsx, the owner 2026-10-19): Write it while there is no draft to look at, else the row's Next - and the
  // line names it by its label
  const writeLit = !!draft && ["none", "failed"].includes(draft.state);
  const nextLabel = busy === "save" ? "Saving…" : draft ? (draft.state === "ready" ? "Looks right" : last ? "Save" : "Next")
    : step === "mailboxes" ? "That's all my sources" : "Next";
  useVerbs("setup-about", a ? [
    { id: "about:back", group: "next", tone: "s", label: "Back", title: at ? "The question before" : "Your main source", run: back },
    { id: "about:next", group: "decide", tone: writeLit ? "s" : "p", disabled: !ready || !!busy,
      why: draft ? `${LABEL[step].toLowerCase()} is still being written` : step === "mailboxes" ? "connect a source first" : "",
      label: nextLabel,
      title: last ? "Saved to what Taskuary knows about you - change it any time in Settings" : step === "mailboxes" ? "Every place your work comes in is connected"
        : draft ? "Kept as it is here - change it any time in Settings" : "The next question", run: next },
  ] : [], !!a && !hidden);
  // the question is the Advisor's line over the row
  const says = draft && SAYS[step];
  const line = !a ? "" : draft ? (draft.state === "failed" ? says.failed(draft.why) : says[draft.state])
    : step === "mailboxes" ? (boxes ? `${boxes === 1 ? "One source is" : `${boxes} sources are`} connected. ${ASK.mailboxes} Then press ${nextLabel}.`
      : "Connect your email, chat or task system with its card - your job is read from everything you connect.")
    // ...and "the ones ticked" only when the mail ticked some: with none it pointed at nothing
    : step === "systems" && !reading && !seen.length ? `Which systems do you work in? Type each one and press Add a system. Then press ${nextLabel}.`
    : `${ASK[step]}${reading && step !== "systems" ? " I'm reading your email to fill this in." : ""} Then press ${nextLabel}.`;
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
  const text = draft ? texts[step] : "";
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
      {step === "mailboxes" && <>
        <Box data-tq-mailboxes="" sx={{ display: "flex", flexDirection: "column", gap: 0.4 }}>
          {boxes ? mailboxes.map((m) => <Typography key={m.address} sx={{ fontSize: 14 }}>{m.address}
            <span style={{ color: DIM, fontSize: 12.5 }}> · {KIND[m.type] || m.title || "Email"}</span></Typography>)
            : <Typography sx={{ color: DIM, fontSize: 13.5 }}>Nothing is connected yet.</Typography>}
        </Box>
        {mailShelf}
      </>}
      {draft && <Box data-tq-draft={draft.state} sx={{ display: "flex", flexDirection: "column", gap: 1.25 }}>{draft.state === "running" ? (
        <Box sx={{ display: "flex", gap: 1, alignItems: "center" }}><CircularProgress size={14} />
          <Typography sx={{ color: DIM, fontSize: 13.5 }}>{says.busy}</Typography></Box>
      ) : <>
        {draft.state === "failed" && <Typography data-tq-draft-failed="" sx={{ color: "#9b2c2c", fontSize: 13.5 }}>
          I couldn't write it: {draft.why}</Typography>}
        {/* READ AS A DOCUMENT, not its markdown (the owner, 2026-10-16: the box showed "### What my job is"): Edit opens the text */}
        {editing === step || !text.trim()
          ? <TextField key={step} multiline fullWidth minRows={10} maxRows={22} value={text} sx={{ ...field, "& textarea": { fontSize: 14, lineHeight: 1.5 } }}
            onChange={(e) => { const v = e.target.value; setEdited((x) => ({ ...x, [step]: true })); setTexts((x) => ({ ...x, [step]: v })); }}
            inputProps={{ "aria-label": LABEL[step] }} autoFocus={editing === step} />
          : <Box data-tq-job-read="" sx={{ border: "1px solid #ddd5c6", borderRadius: 1.5, bgcolor: "#fff", px: 2, py: 1, maxHeight: "52vh", overflowY: "auto",
              "& h2": { fontSize: 15.5, fontWeight: 700, mt: 2, mb: 0.5, borderBottom: "1px solid #ece6db" }, "& h2:first-of-type": { mt: 0.5 },
              "& h3": { fontSize: 14.5, fontWeight: 700, mt: 1.5, mb: 0.5 }, "& h3:first-of-type": { mt: 0.5 }, "& ul": { pl: 2.5, my: 0.5 },
              "& li": { fontSize: 14, lineHeight: 1.55, mb: 0.4 } }}><Md text={text} /></Box>}
        <Box sx={{ display: "flex", gap: 1 }}>
          {text.trim() && <Button size="small" onClick={() => setEditing((v) => (v === step ? "" : step))}>{editing === step ? "Done editing" : "Edit"}</Button>}
          <Button size="small" onClick={() => { setEditing(""); learn([step]); }} disabled={!!busy}
            data-tq-setup-lit={writeLit ? "about" : undefined}>{draft.state === "none" ? "Write it" : "Write it again"}</Button>
        </Box>
      </>}</Box>}
      {note && !draft && <Typography sx={{ color: DIM, fontSize: 13 }}>{note}</Typography>}
      {err && <Typography sx={{ color: "#9b2c2c", fontSize: 13 }}>{err}</Typography>}
      {!again && canSkip(step) && <Box><Button size="small" disabled={!!busy} onClick={skip} sx={{ color: DIM, fontSize: 12.5 }}>Skip these questions</Button></Box>}
    </Box>
  );
}
