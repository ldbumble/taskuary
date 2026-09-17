// Getting started, pointed at the places that do it.
//
// A fresh install opens on an empty Timeline that looks exactly like a working install on a quiet
// morning, and the few things standing between those two states live on different tabs.
//
// The first version of this pointed at those tabs, and the second decided that pointing was not
// setting up - so every step grew a form. That held while a step was one field. It stopped holding
// when the AI row grew a CLI picker, an installer, a sign-in pane and an API-key form: a worse copy
// of the page that owns those things, kept in step with it by hand. A second source of truth loses.
//
// So the rows point again, at real positions rather than at tabs - the AI CLI agents page, the
// group inside Settings where the models are chosen, the name field inside Docs. One form survives,
// because two text boxes have nowhere better to be. And the whole thing is gone once it is done:
// the counter is finished, not hidden. The walk on the Assistant header is the way back.
import React, { useCallback, useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, Dialog, DialogContent, TextField, Tooltip, Typography } from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import CloseIcon from "@mui/icons-material/Close";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import api from "./api";
import { BORDER, DIM, FAINT, INK, PANEL2 } from "./theme.jsx";

const COUNT = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];
const spell = (n) => COUNT[n] || String(n);

export const useSetup = (tick) => {
  const [state, setState] = useState(null);
  const load = useCallback(() => {
    api.get("/api/setup").then(({ data }) => setState(data)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load, tick]);
  return [state, load];
};

/* Gone for good once the five are done - there is no "show it again", because the walk on the
   Assistant header is always there and covers more than this ever did. */
export const SetupChip = ({ state, onOpen }) => {
  if (!state || state.complete) return null;
  const left = state.total - state.done;
  const pct = state.total ? (state.done / state.total) * 100 : 0;
  return (
    <Tooltip title={state.dismissed ? "Setting up — put away, click to reopen" : "Finish setting Taskuary up"}>
      <Box onClick={onOpen}
        sx={{ display: "flex", alignItems: "center", gap: 0.75, cursor: "pointer", ml: 1,
          px: 1, py: 0.35, borderRadius: 99, border: `1px solid ${state.dismissed ? BORDER : "#d8cfbe"}`,
          bgcolor: state.dismissed ? "transparent" : "#eae4d8",
          opacity: state.dismissed ? 0.75 : 1, "&:hover": { opacity: 1 } }}>
        <Box sx={{ position: "relative", display: "flex", width: 16, height: 16 }}>
          <CircularProgress variant="determinate" value={100} size={16} thickness={6}
            sx={{ color: "#e6e9ef", position: "absolute" }} />
          <CircularProgress variant="determinate" value={pct} size={16} thickness={6} sx={{ color: "#55697a" }} />
        </Box>
        <Typography variant="caption" sx={{ fontWeight: 700, color: state.dismissed ? DIM : "#55697a" }}>
          {left} left
        </Typography>
      </Box>
    </Tooltip>
  );
};

const Field = (p) => <TextField size="small" fullWidth sx={{ bgcolor: "#fff" }} {...p} />;

/* The one step still done here. Everything else has a page with more on it than this dialog can
   hold; this one is two text boxes, and sending somebody to Docs to type their own name is exactly
   the pointing that is worth complaining about. */
const OwnerForm = ({ onDone }) => {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => {
    api.get("/api/owner").then(({ data }) => {
      if (data.owner && data.owner !== "the owner") setName(data.owner);
      if (data.owner_email) setEmail(data.owner_email);
    }).catch(() => {});
  }, []);
  const save = async () => {
    setBusy(true); setErr("");
    try { await api.put("/api/owner", { name: name.trim(), email: email.trim() || null }); await onDone(); }
    catch (e) { setErr(e?.response?.data?.detail || "could not save that"); }
    setBusy(false);
  };
  return (
    <Box sx={{ display: "flex", gap: 1, mt: 1, flexWrap: "wrap" }}>
      <Field label="Your name" value={name} onChange={(e) => setName(e.target.value)} sx={{ bgcolor: "#fff", flex: 1, minWidth: 160 }} />
      <Field label="Email" value={email} onChange={(e) => setEmail(e.target.value)} sx={{ bgcolor: "#fff", flex: 1, minWidth: 160 }} />
      <Button variant="contained" disableElevation size="small" disabled={busy || !name.trim()} onClick={save}>
        {busy ? "…" : "Save"}
      </Button>
      {err && <Alert severity="error" sx={{ width: "100%", fontSize: 12.5 }}>{err}</Alert>}
    </Box>
  );
};

const FORMS = { owner: OwnerForm };

/* A done step collapses to ONE line. Its reason mattered while you were deciding whether to do it;
   afterwards it is six lines of history pushing the thing you are actually working on below the
   fold. Only the open step carries its full text, and only one is ever open. */
const Step = ({ s, n, open, onOpen, onGo, onDone }) => {
  const Form = FORMS[s.key];
  const active = open && !s.done;
  return (
    <Box sx={{ borderTop: n ? `1px solid ${BORDER}` : "none",
      bgcolor: active ? "#fff" : "transparent",
      boxShadow: active ? "inset 3px 0 0 #55697a" : "none",
      px: active ? 1.5 : 0, py: s.done ? 1 : 1.5, transition: "background-color .15s" }}>
      {/* the button WRAPS below the text rather than squeezing it: naming the destination makes it
          a phrase, and a nowrap phrase beside a shrinkable column left the reason reading one word
          per line at 390px (photographed) */}
      <Box sx={{ display: "flex", gap: 1.5, flexWrap: "wrap", alignItems: s.done ? "center" : "flex-start" }}>
        <Box sx={{ pt: s.done ? 0 : 0.25, display: "flex" }}>
          {s.done ? <CheckCircleIcon sx={{ fontSize: 18, color: "#47654a" }} />
            : <RadioButtonUncheckedIcon sx={{ fontSize: 20, color: "#55697a" }} />}
        </Box>
        <Box sx={{ flex: "1 1 150px", minWidth: 0 }}>
          <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, flexWrap: "wrap" }}>
            <Typography sx={{ fontWeight: s.done ? 600 : 700, fontSize: s.done ? 12.5 : 13.5,
              color: s.done ? DIM : INK }}>{s.title}</Typography>
            {s.done && s.detail && (
              <Typography variant="caption" sx={{ color: "#47654a", fontWeight: 600 }}>{s.detail}</Typography>
            )}
          </Box>
          {/* WHY before HOW, while it is still a decision */}
          {!s.done && (
            <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.25, lineHeight: 1.55 }}>
              {s.why}
            </Typography>
          )}
          {active && Form && <Form onDone={onDone} />}
        </Box>
        {!s.done && !open && Form && (
          <Button size="small" variant="outlined" onClick={onOpen}
            sx={{ alignSelf: "center", whiteSpace: "nowrap", fontSize: 12 }}>Set up</Button>
        )}
        {!s.done && !Form && (
          /* what it OPENS, not which tab it lives on: two rows both read "Connections" and went to
             the AI CLI agents page and the connector list (setup.state owns the words) */
          <Button size="small" endIcon={<OpenInNewIcon sx={{ fontSize: 13 }} />} onClick={() => onGo(s.goto)}
            sx={{ alignSelf: "center", whiteSpace: "nowrap", fontSize: 12 }}>{s.goto?.label || s.goto?.tab}</Button>
        )}
        {s.done && (Form
          ? <Typography variant="caption" onClick={onOpen}
              sx={{ color: FAINT, cursor: "pointer", whiteSpace: "nowrap", "&:hover": { color: "#55697a" } }}>change</Typography>
          : <Typography variant="caption" onClick={() => onGo(s.goto)}
              sx={{ color: FAINT, cursor: "pointer", whiteSpace: "nowrap", "&:hover": { color: "#55697a" } }}>change</Typography>)}
      </Box>
      {/* A reopened DONE step puts its form UNDER the row, indented to the text column - inside the
          header row it overflowed its track and sat on the step's own title (owner, 2026-09-02). */}
      {s.done && open && Form && (
        <Box sx={{ pl: 4.5, pt: 1 }}><Form onDone={onDone} /></Box>
      )}
    </Box>
  );
};

export const SetupPanel = ({ open, state, onClose, onGo, onDismiss, onRefresh }) => {
  const [openKey, setOpenKey] = useState(null);
  const steps = state?.steps || [];
  // the first thing left to do is already open: a list whose every step needs a click first is a
  // list of buttons
  useEffect(() => {
    if (!open || !steps.length) return;
    if (state.complete) { setOpenKey(null); return; }
    setOpenKey((k) => k || (steps.find((s) => !s.done && FORMS[s.key]) || {}).key || null);
  }, [open, steps, state?.complete]);
  if (!state) return null;
  const left = state.total - state.done;
  // one road for every row: the tab, then the position inside it
  const go = (goto) => {
    if (goto?.hash) window.location.hash = goto.hash;
    onGo(goto?.tab);
    onClose();
  };
  const done = async () => { setOpenKey(null); await onRefresh(); };
  return (
    <Dialog open={!!open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogContent sx={{ p: 3 }}>
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
          <Box sx={{ flex: 1 }}>
            <Typography sx={{ fontWeight: 800, fontSize: 17, color: INK }}>
              {state.complete ? "Taskuary is yours" : `${spell(left)} ${left === 1 ? "thing" : "things"} left`}
            </Typography>
            <Typography variant="body2" sx={{ color: DIM, mt: 0.5 }}>
              {state.complete
                ? "This list is finished and will not come back. “Set up Taskuary” on the Assistant walks the rest of the app whenever you want it."
                : "Each one opens the page that actually does it. They tick themselves from what is really connected, "
                  + "so anything you set up anywhere shows up here."}
            </Typography>
          </Box>
          <CloseIcon onClick={onClose} sx={{ fontSize: 18, color: FAINT, cursor: "pointer", mt: 0.5 }} />
        </Box>

        <Box sx={{ mt: 2, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 2 }}>
          {steps.map((s, i) => (
            <Step key={s.key} s={s} n={i} open={openKey === s.key} onOpen={() => setOpenKey(s.key)}
              onGo={go} onDone={done} />
          ))}
        </Box>

        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 2 }}>
          <Typography variant="caption" sx={{ color: FAINT, flex: 1 }}>
            {state.dismissed ? "Put away — the quiet counter in the top bar brings it back."
              : state.complete ? "Revisit any of these later from Connections, Docs or Settings."
                : "Not now? Put it away; the counter in the top bar brings it back."}
          </Typography>
          {!state.complete && (
            <Button size="small" sx={{ color: DIM, fontSize: 12 }} onClick={() => onDismiss(!state.dismissed)}>
              {state.dismissed ? "Show it again" : "Put it away"}
            </Button>
          )}
          <Button size="small" variant="contained" disableElevation onClick={onClose} sx={{ fontSize: 12 }}>
            {state.complete ? "Done" : "Close"}
          </Button>
        </Box>
      </DialogContent>
    </Dialog>
  );
};
