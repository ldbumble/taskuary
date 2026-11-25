// HAND THE TASK TO ANOTHER AI, FROM ITS HEAD (the owner, 2026-11-18: "i need way to hand this to new AI agent instead of the one that blocked
// me.. we need button on top of every task to change the backend of this both model, and provider of whatever is available in app"): one pill
// naming the AI at work, its menu every AI ready here and each of its models (brainOptions.switchChoices), the current one ticked. A pick is
// handed to `onPick({pick, model, label})` - Continue's own road on the server (_take_ai): what works it stops, the new AI takes the conversation.
import React, { useState } from "react";
import { Box, Button, CircularProgress, Menu, MenuItem, Tooltip } from "@mui/material";
import CheckIcon from "@mui/icons-material/Check";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";
import { BORDER, FAINT, INK } from "./theme.jsx";
import { cardsOf, switchChoices } from "./brainOptions.js";
import { useCardModels } from "./ModelPick.jsx";

const PILL = { fontSize: 11.5, fontWeight: 600, height: 26, minHeight: 26, py: 0, px: 1.25, borderRadius: 13, textTransform: "none", letterSpacing: 0,
  bgcolor: "var(--tq-panel, #f4f1ec)", color: INK, borderColor: BORDER, whiteSpace: "nowrap", maxWidth: 220, flexShrink: 1, minWidth: 0,
  "& .MuiButton-startIcon": { mr: 0.5 }, "&:hover": { borderColor: "var(--tq-border, #d8cfbe)", bgcolor: "var(--tq-panel, #f4f1ec)" } };

// `ask`: what switchChoices reads - the AIs, the one at work - with each AI card's own models read here (ModelPick.useCardModels)
// `off`: the AI at work stands in for one that is off (brainroute.stands_in) - "Running on Claude Code - HIPAA AI is off", said first
// `title`: what the pill is for where it is not a task's hand-over (New's box: the AI the job starts on)
export default function SwitchAi({ ask = {}, off = "", busy = false, onPick, title: what = "" }) {
  const [at, setAt] = useState(null), [open, setOpen] = useState({});
  const live = useCardModels(cardsOf(ask));
  const { rows, said, why } = switchChoices({ ...ask, live });
  const title = why || what || (off ? `${off} - hand this task to another AI` : said ? `Working on ${said} - hand this task to another AI` : "Hand this task to an AI");
  return <>
    <Tooltip title={title}><span style={{ display: "inline-flex", minWidth: 0 }}>
      <Button size="small" variant="outlined" sx={PILL} data-tq-switch-ai="" disabled={!!why || busy} aria-haspopup="menu" aria-label={title}
        startIcon={busy ? <CircularProgress size={11} /> : <SwapHorizIcon sx={{ fontSize: 14, color: "var(--tq-link, #55697a)" }} />}
        onClick={(e) => setAt(e.currentTarget)}>
        <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>{busy ? "Handing over…" : said || "AI"}</Box>
      </Button></span></Tooltip>
    <Menu anchorEl={at} open={!!at} onClose={() => { setAt(null); setOpen({}); }} slotProps={{ paper: { sx: { maxHeight: "60vh" } } }}>
      {rows.filter((r) => !r.more || open[r.pick]).map((r) => [<MenuItem key={`${r.pick}/${r.model}`} data-tq-switch-option={`${r.pick}/${r.model}`} selected={r.now} disabled={r.now}
        onClick={() => { setAt(null); onPick?.({ pick: r.pick, model: r.model, label: r.model ? `${r.ai} (${r.model})` : r.label }); }}
        sx={{ fontSize: 12.5, pl: r.model ? 4 : 1.5, fontWeight: r.model ? 400 : 600, color: r.model ? FAINT : INK, gap: 1 }}>
        <Box component="span" sx={{ flex: 1 }}>{r.label}{!r.model && <Box component="span" sx={{ fontWeight: 400, color: FAINT }}> · {r.note || "default model"}</Box>}</Box>
        {r.now && <CheckIcon sx={{ fontSize: 14 }} aria-label="at work now" />}
      </MenuItem>,
      // ...under an AI's last shown model, the rest of its list one press away
      ...(!r.more && rows.some((x) => x.more && x.pick === r.pick) && !open[r.pick] && r === rows.filter((x) => x.pick === r.pick && !x.more).at(-1)
        ? [<MenuItem key={`${r.pick}/more`} data-tq-switch-more={r.pick} onClick={() => setOpen((o) => ({ ...o, [r.pick]: true }))}
            sx={{ fontSize: 12, pl: 4, color: FAINT, fontStyle: "italic" }}>More {r.ai || r.label} models ({rows.filter((x) => x.more && x.pick === r.pick).length})</MenuItem>] : [])])}
    </Menu>
  </>;
}
