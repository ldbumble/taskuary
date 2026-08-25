// Getting started, said out loud. A fresh install opens on an empty Timeline that looks exactly
// like a working install on a quiet morning - and the three things standing between those two
// states live on three different tabs with nothing pointing at them.
//
// Two pieces: a counter in the top bar that is a progress ring rather than a badge (it shows how
// far along you are without being read), and a panel that says what each step is FOR before it
// says where to click. Dismissible, because a checklist that cannot be put away is nagging - and
// reopenable from the same spot, because one that cannot be got back is worse.
import React, { useCallback, useEffect, useState } from "react";
import { Box, Button, CircularProgress, Dialog, DialogContent, Tooltip, Typography } from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import CloseIcon from "@mui/icons-material/Close";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import api from "./api";
import { BORDER, DIM, FAINT, INK, PANEL2 } from "./theme.jsx";

export const useSetup = (tick) => {
  const [state, setState] = useState(null);
  const load = useCallback(() => {
    api.get("/api/setup").then(({ data }) => setState(data)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load, tick]);
  return [state, load];
};

/* The counter: a ring that fills as steps complete. Hidden once everything required is done -
   a permanent "3/3 ✓" is decoration, and the top bar is not for decoration. */
export const SetupChip = ({ state, onOpen }) => {
  if (!state || state.ready) return null;
  const pct = state.total ? (state.done / state.total) * 100 : 0;
  return (
    <Tooltip title={state.dismissed ? "Setup — put away, click to reopen" : "Finish setting Taskuary up"}>
      <Box onClick={onOpen}
        sx={{ display: "flex", alignItems: "center", gap: 0.75, cursor: "pointer", ml: 1,
          px: 1, py: 0.35, borderRadius: 99, border: `1px solid ${state.dismissed ? BORDER : "#f3ddb8"}`,
          bgcolor: state.dismissed ? "transparent" : "#fef4e6",
          opacity: state.dismissed ? 0.75 : 1, "&:hover": { opacity: 1 } }}>
        <Box sx={{ position: "relative", display: "flex", width: 16, height: 16 }}>
          <CircularProgress variant="determinate" value={100} size={16} thickness={6}
            sx={{ color: "#e6e9ef", position: "absolute" }} />
          <CircularProgress variant="determinate" value={pct} size={16} thickness={6}
            sx={{ color: "#b45309" }} />
        </Box>
        <Typography variant="caption" sx={{ fontWeight: 700, color: state.dismissed ? DIM : "#b45309" }}>
          {state.done}/{state.total}
        </Typography>
      </Box>
    </Tooltip>
  );
};

const Step = ({ s, n, onGo }) => (
  <Box sx={{ display: "flex", gap: 1.5, py: 1.5, borderTop: n ? `1px solid ${BORDER}` : "none" }}>
    <Box sx={{ pt: 0.25 }}>
      {s.done
        ? <CheckCircleIcon sx={{ fontSize: 20, color: "#15803d" }} />
        : <RadioButtonUncheckedIcon sx={{ fontSize: 20, color: s.optional ? "#c2c9d6" : "#b45309" }} />}
    </Box>
    <Box sx={{ flex: 1, minWidth: 0 }}>
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1, flexWrap: "wrap" }}>
        <Typography sx={{ fontWeight: 700, fontSize: 13.5, color: s.done ? DIM : INK }}>{s.title}</Typography>
        {s.optional && <Typography variant="caption" sx={{ color: FAINT }}>optional</Typography>}
        {s.done && s.detail && (
          <Typography variant="caption" sx={{ color: "#15803d", fontWeight: 600 }}>{s.detail}</Typography>
        )}
      </Box>
      {/* WHY before WHERE: "go to Connectors" is navigation, not an explanation, and the reason
          this step exists is the thing that makes it worth doing */}
      <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.25, lineHeight: 1.55 }}>
        {s.why}
      </Typography>
    </Box>
    {!s.done && (
      <Button size="small" endIcon={<ArrowForwardIcon sx={{ fontSize: 14 }} />}
        onClick={() => onGo(s.where)} sx={{ alignSelf: "center", whiteSpace: "nowrap", fontSize: 12 }}>
        {s.where}
      </Button>
    )}
  </Box>
);

export const SetupPanel = ({ open, state, onClose, onGo, onDismiss }) => {
  if (!state) return null;
  const left = state.total - state.done;
  return (
    <Dialog open={!!open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogContent sx={{ p: 3 }}>
        <Box sx={{ display: "flex", alignItems: "flex-start", gap: 1 }}>
          <Box sx={{ flex: 1 }}>
            <Typography sx={{ fontWeight: 800, fontSize: 17, color: INK }}>
              {state.ready ? "Taskuary is set up" : "Three things and Taskuary works"}
            </Typography>
            <Typography variant="body2" sx={{ color: DIM, mt: 0.5 }}>
              {state.ready
                ? "Everything needed is connected. The rest below is optional."
                : `${state.done} of ${state.total} done${left ? ` — ${left} to go` : ""}. Nothing here is busywork: `
                  + "without these the Timeline stays empty and looks like a quiet day."}
            </Typography>
          </Box>
          <CloseIcon onClick={onClose} sx={{ fontSize: 18, color: FAINT, cursor: "pointer", mt: 0.5 }} />
        </Box>

        <Box sx={{ mt: 2, bgcolor: PANEL2, border: `1px solid ${BORDER}`, borderRadius: 1.5, px: 2 }}>
          {(state.steps || []).map((s, i) => <Step key={s.key} s={s} n={i} onGo={onGo} />)}
        </Box>

        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mt: 2 }}>
          {/* dismissing is not the same as finishing, and the wording has to say which one you
              are doing - the counter stays in the bar, greyed, and clicking it brings this back */}
          <Typography variant="caption" sx={{ color: FAINT, flex: 1 }}>
            {state.dismissed
              ? "Put away — the counter stays in the top bar until setup is done."
              : "Not now? Put it away; the counter in the top bar brings it back."}
          </Typography>
          {!state.ready && (
            <Button size="small" sx={{ color: DIM, fontSize: 12 }}
              onClick={() => onDismiss(!state.dismissed)}>
              {state.dismissed ? "Show it again" : "Put it away"}
            </Button>
          )}
          <Button size="small" variant="contained" disableElevation onClick={onClose} sx={{ fontSize: 12 }}>
            {state.ready ? "Done" : "Close"}
          </Button>
        </Box>
      </DialogContent>
    </Dialog>
  );
};
