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
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, Dialog, DialogContent, Tooltip, Typography } from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import CloseIcon from "@mui/icons-material/Close";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import api from "./api";
import OwnerForm from "./OwnerForm.jsx";
import { BORDER, DIM, FAINT, INK, PANEL2, ROLES } from "./theme.jsx";
import { firstSyncProgress, startFirstSync } from "./setupSync.js";

const COUNT = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];
const spell = (n) => COUNT[n] || String(n);

export const useSetup = (tick) => {
  const [state, setState] = useState(null);
  const load = useCallback(() => {
    return api.get("/api/setup").then(({ data }) => setState(data)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load, tick]);
  return [state, load];
};

/* Gone once the four are done; the optional walk remains available afterwards.
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
        {/* The track has to be WARM. It was #e6e9ef - a cool grey-blue on this warm tan pill, 1.04:1,
            the same lightness - so the ring was invisible. And on a fresh install nothing is done, so
            the arc has zero length and that track is the ONLY thing drawn: the counter showed "5 left"
            beside a blank gap at exactly the moment it matters most. Both colours come from the roles
            table now rather than being typed here: muted is the part not done, done is the part that is,
            which is the same green the panel ticks a finished row with. */}
        <Box sx={{ position: "relative", display: "flex", width: 16, height: 16 }}>
          <CircularProgress variant="determinate" value={100} size={16} thickness={6}
            sx={{ color: ROLES.muted.solid, position: "absolute" }} />
          <CircularProgress variant="determinate" value={pct} size={16} thickness={6} sx={{ color: ROLES.done.solid }} />
        </Box>
        <Typography variant="caption" sx={{ fontWeight: 700, color: state.dismissed ? DIM : "#55697a" }}>
          {left} left
        </Typography>
      </Box>
    </Tooltip>
  );
};

const FORMS = { owner: OwnerForm };

export const FirstSync = ({ enabled, ready, firstItems = [], onSaved, onNavigate }) => {
  const [starting, setStarting] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const saved = useRef(onSaved); saved.current = onSaved;
  useEffect(() => {
    if (!busy) return undefined;
    let cancelled = false, timer;
    const read = async () => {
      try {
        const progress = await firstSyncProgress(api);
        if (cancelled) return;
        setResult(progress);
        if (progress.phase === "reading") timer = setTimeout(read, 1500);
        else { setBusy(false); await saved.current?.(); }
      } catch (e) {
        if (!cancelled) { setError(e?.response?.data?.detail || e.message || "Could not read progress. Try again."); setBusy(false); }
      }
    };
    timer = setTimeout(read, 1500);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [busy]);
  const start = async () => {
    setError(""); setResult(null); setStarting(true);
    try { await startFirstSync(api); setBusy(true); }
    catch (e) { setError(e?.response?.data?.detail || e.message || "Could not start the source read."); }
    finally { setStarting(false); }
  };
  const items = (result?.state?.first_items || firstItems).slice(0, 5);
  const openItem = (item) => {
    window.location.hash = item.TaskId ? `task=${item.TaskId}` : `msg=${item.MessageId}`;
    onNavigate?.("Assistant");
  };
  return <Box sx={{ mt: 1 }}>
    {!ready && !enabled && <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 1 }}>
      Add your name, one AI and one work source first.
    </Typography>}
    <Button size="small" variant="contained" disableElevation disabled={starting || busy || !enabled} onClick={start}
      startIcon={starting || busy ? <CircularProgress size={12} color="inherit" /> : null}>
      {starting || busy ? "Reading…" : ready || result?.phase === "ready" ? "Read again" : "Read first items"}
    </Button>
    <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.75 }} aria-live="polite">
      {result?.message || (ready ? "Open one of your first items to review its verdict or draft." : "We will show up to five recent results here; sources keep their normal import scope.")}
    </Typography>
    {(error || result?.phase === "failed") && <Alert severity="error" sx={{ mt: 1 }}>{error || result.message}</Alert>}
    {items.length > 0 && <Box sx={{ display: "flex", flexDirection: "column", alignItems: "flex-start", mt: 1 }}>
      {items.map((item) => <Button key={item.MessageId} size="small" onClick={() => openItem(item)} sx={{ textAlign: "left", justifyContent: "flex-start" }}>
        {item.Subject || "Open this item"}
      </Button>)}
    </Box>}
  </Box>;
};

/* A done step collapses to ONE line. Its reason mattered while you were deciding whether to do it;
   afterwards it is six lines of history pushing the thing you are actually working on below the
   fold. Only the open step carries its full text, and only one is ever open. */
const Step = ({ s, n, open, onOpen, onGo, onDone, firstItems }) => {
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
          {s.action === "sync" && <FirstSync enabled={s.enabled} ready={s.done} firstItems={firstItems}
            onSaved={onDone} onNavigate={() => onGo(s.goto)} />}
        </Box>
        {!s.done && !open && Form && (
          <Button size="small" variant="outlined" onClick={onOpen}
            sx={{ alignSelf: "center", whiteSpace: "nowrap", fontSize: 12 }}>Set up</Button>
        )}
        {!s.done && !Form && s.action !== "sync" && (
          /* what it OPENS, not which tab it lives on: two rows both read "Connections" and went to
             the AI CLI agents page and the connector list (setup.state owns the words) */
          <Button size="small" endIcon={<OpenInNewIcon sx={{ fontSize: 13 }} />} onClick={() => onGo(s.goto)}
            sx={{ alignSelf: "center", whiteSpace: "nowrap", fontSize: 12 }}>{s.goto?.label || s.goto?.tab}</Button>
        )}
        {s.done && s.action !== "sync" && (Form
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
                ? "Your first result is ready. Open an item below to review it; add more sources, agents or reports when you need them."
                : "Start with your name, one AI and one work source. Review the first result before adding anything else; model settings can wait."}
            </Typography>
          </Box>
          <CloseIcon onClick={onClose} sx={{ fontSize: 18, color: FAINT, cursor: "pointer", mt: 0.5 }} />
        </Box>

        <Box sx={{ mt: 2, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 2 }}>
          {steps.map((s, i) => (
            <Step key={s.key} s={s} n={i} open={openKey === s.key} onOpen={() => setOpenKey(s.key)}
              onGo={go} onDone={done} firstItems={state.first_items || []} />
          ))}
        </Box>

        <Button size="small" sx={{ mt: 1, color: DIM }} onClick={() => go({ tab: "Settings", hash: "settings=config&group=Triage%20%26%20agents" })}>
          Optional: review models and agents
        </Button>

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
