// HAND THE TASK TO ANOTHER AI, FROM ITS HEAD (the owner, 2026-11-18: "i need way to hand this to new AI agent instead of the one that blocked
// me.. we need button on top of every task to change the backend of this both model, and provider of whatever is available in app"): one pill
// naming the AI at work, its menu every AI ready here and each of its models (brainOptions.switchChoices), the current one ticked. A pick is
// handed to `onPick({pick, model, label})` - Continue's own road on the server (_take_ai): what works it stops, the new AI takes the conversation.
import React, { useState } from "react";
import { Box, Button, CircularProgress, Menu, MenuItem, Tooltip } from "@mui/material";
import CheckIcon from "@mui/icons-material/Check";
import SwapHorizIcon from "@mui/icons-material/SwapHoriz";
import { BORDER, FAINT, INK } from "./theme.jsx";
import { switchChoices } from "./brainOptions.js";

const PILL = { fontSize: 11.5, fontWeight: 600, height: 26, minHeight: 26, py: 0, px: 1.25, borderRadius: 13, textTransform: "none", letterSpacing: 0,
  bgcolor: "var(--tq-panel, #f4f1ec)", color: INK, borderColor: BORDER, whiteSpace: "nowrap", maxWidth: 220, flexShrink: 1, minWidth: 0,
  "& .MuiButton-startIcon": { mr: 0.5 }, "&:hover": { borderColor: "var(--tq-border, #d8cfbe)", bgcolor: "var(--tq-panel, #f4f1ec)" } };

export default function SwitchAi({ choices, busy = false, onPick }) {
  const [at, setAt] = useState(null);
  const { rows, said, why } = choices || switchChoices();
  const title = why || (said ? `Working on ${said} - hand this task to another AI` : "Hand this task to an AI");
  return <>
    <Tooltip title={title}><span style={{ display: "inline-flex", minWidth: 0 }}>
      <Button size="small" variant="outlined" sx={PILL} data-tq-switch-ai="" disabled={!!why || busy} aria-haspopup="menu" aria-label={title}
        startIcon={busy ? <CircularProgress size={11} /> : <SwapHorizIcon sx={{ fontSize: 14, color: "var(--tq-link, #55697a)" }} />}
        onClick={(e) => setAt(e.currentTarget)}>
        <Box component="span" sx={{ overflow: "hidden", textOverflow: "ellipsis" }}>{busy ? "Handing over…" : said || "AI"}</Box>
      </Button></span></Tooltip>
    <Menu anchorEl={at} open={!!at} onClose={() => setAt(null)} slotProps={{ paper: { sx: { maxHeight: "60vh" } } }}>
      {rows.map((r) => <MenuItem key={`${r.pick}/${r.model}`} data-tq-switch-option={`${r.pick}/${r.model}`} selected={r.now} disabled={r.now}
        onClick={() => { setAt(null); onPick?.({ pick: r.pick, model: r.model, label: r.model ? `${r.ai} (${r.model})` : r.label }); }}
        sx={{ fontSize: 12.5, pl: r.model ? 4 : 1.5, fontWeight: r.model ? 400 : 600, color: r.model ? FAINT : INK, gap: 1 }}>
        <Box component="span" sx={{ flex: 1 }}>{r.label}{!r.model && <Box component="span" sx={{ fontWeight: 400, color: FAINT }}> · default model</Box>}</Box>
        {r.now && <CheckIcon sx={{ fontSize: 14 }} aria-label="at work now" />}
      </MenuItem>)}
    </Menu>
  </>;
}
