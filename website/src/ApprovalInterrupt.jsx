import React from "react";
import { Box, Button, Dialog, DialogActions, DialogContent, DialogTitle, Typography } from "@mui/material";
import { DIM, FAINT, INK } from "./theme.jsx";

// PW-239: the click did not send. The new message and the triage change are shown; the owner's own
// edit stays theirs; "Review the update" opens the refreshed draft beside it for a fresh yes.
export default function ApprovalInterrupt({ it, onResolve }) {
  if (!it) return null;
  return (
    <Dialog open onClose={() => onResolve("cancel")} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ fontSize: 15, fontWeight: 700 }}>{it.title}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ color: DIM, mb: 1 }}>
          Nothing was sent. The draft you approved was written before this arrived.
        </Typography>
        {it.latest && (
          <Box sx={{ border: "1px solid #d2d6cf", borderRadius: 1.5, p: 1, mb: 1 }}>
            <Typography variant="caption" sx={{ color: FAINT, display: "block" }}>
              {it.latest.FromName || it.latest.FromEmail || "New message"}{it.latest.SentAt ? ` · ${it.latest.SentAt}` : ""}
            </Typography>
            <Typography variant="body2" sx={{ color: INK, whiteSpace: "pre-wrap" }}>{it.latest.preview}</Typography>
          </Box>
        )}
        {it.triage && <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 1 }}>Triage: {it.triage}</Typography>}
        {it.yours && (
          <Typography variant="caption" sx={{ color: FAINT, display: "block" }}>
            Your edit is kept in the reply box for comparison; the refreshed draft is shown beside it when you review the update.
          </Typography>
        )}
      </DialogContent>
      <DialogActions>
        <Button size="small" sx={{ color: DIM }} onClick={() => onResolve("cancel")}>Cancel</Button>
        <Button size="small" variant="contained" disableElevation onClick={() => onResolve("review")}>Review the update</Button>
      </DialogActions>
    </Dialog>
  );
}
