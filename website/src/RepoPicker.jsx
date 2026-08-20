// Which checkout does this task belong in? Taskuary decides it (the `repo:` tag, else the ask
// matched against the SOUL.md repo map) - but it can be wrong, and a wrong answer means an agent
// editing the wrong tree in good faith. So the decision is visible on the task, with its reason,
// and one click overrides it: the tag is what always wins, and the new session's prompt says so.
import React, { useEffect, useState } from "react";
import { Box, Button, Chip, CircularProgress, TextField, Typography } from "@mui/material";
import AccountTreeIcon from "@mui/icons-material/AccountTree";
import CheckIcon from "@mui/icons-material/Check";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import api from "./api";
import { PANEL, PANEL2, BORDER, DIM, FAINT, INK, mono } from "./theme.jsx";

export const RepoPicker = ({ taskId, agent = "coder", hasSession, onDone }) => {
  const [rows, setRows] = useState(null);
  const [picked, setPicked] = useState(null);
  const [why, setWhy] = useState("");
  const [open, setOpen] = useState(null);          // the repo whose path we are being asked for
  const [path, setPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const load = () => api.get(`/api/tasks/${taskId}/repos`, { params: { agent } })
    .then(({ data }) => { setRows(data.data || []); setPicked(data.picked); setWhy(data.why || ""); })
    .catch(() => setRows([]));
  useEffect(() => { setRows(null); setOpen(null); setPath(""); setErr(""); load(); }, [taskId, agent]);

  const choose = async (r, withPath) => {
    // a repo Taskuary knows about but has no path for cannot be opened at all - ask once, here
    if (!r.has_path && !withPath) { setOpen(r.repo); setPath(""); setErr(""); return; }
    setBusy(true); setErr("");
    try {
      const { data } = await api.put(`/api/tasks/${taskId}/repo`,
        { repo: r.repo, path: withPath || null, agent, restart: !!hasSession });
      setOpen(null); load(); onDone?.(data);
    } catch (e) { setErr(e?.response?.data?.detail || "Could not set the repo"); }
    setBusy(false);
  };

  if (rows === null) return <CircularProgress size={14} />;
  if (!rows.length) return (
    <Typography variant="caption" sx={{ color: FAINT }}>
      No repository map yet — add one to SOUL.md (Docs) and Taskuary can route tasks to a checkout.
    </Typography>
  );
  return (
    <Box>
      <Typography variant="caption" sx={{ color: DIM, display: "block", mb: 0.75 }}>
        {picked ? <>Working in <b style={mono}>{picked}</b>{why ? ` — ${why}` : ""}.</>
          : "No checkout chosen — the session opens in the agent's own folder."}
        {" "}Pick another and the session restarts there with the prompt rewritten.
      </Typography>
      {rows.map((r) => {
        const on = r.repo === picked;
        return (
          <Box key={r.repo} sx={{ border: `1px solid ${on ? "#c7d2fe" : BORDER}`, borderRadius: 1.5,
            bgcolor: on ? "#eef0ff" : PANEL, px: 1.1, py: 0.7, mb: 0.6 }}>
            <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
              <AccountTreeIcon sx={{ fontSize: 14, color: on ? "#4f46e5" : FAINT }} />
              <Typography variant="caption" sx={{ ...mono, fontWeight: 700, color: on ? "#4f46e5" : INK,
                flex: 1, minWidth: 0 }} noWrap>{r.repo}</Typography>
              {r.tagged && <Chip size="small" label="pinned" sx={{ height: 16, fontSize: 9, bgcolor: "#eef0ff", color: "#4f46e5" }} />}
              {!r.has_path && (
                <Chip size="small" icon={<WarningAmberIcon sx={{ fontSize: 11 }} />} label="no local path"
                  sx={{ height: 16, fontSize: 9, bgcolor: "#fff8e6", color: "#b45309" }} />
              )}
              {on ? <CheckIcon sx={{ fontSize: 15, color: "#15803d" }} />
                : <Button size="small" sx={{ fontSize: 10.5, minWidth: 0, px: 0.75 }} disabled={busy}
                    onClick={() => choose(r)}>use this</Button>}
            </Box>
            {r.what && (
              <Typography variant="caption" sx={{ color: FAINT, display: "block", pl: 2.6, lineHeight: 1.35 }} noWrap>
                {r.what}
              </Typography>
            )}
            {r.has_path && (
              <Typography variant="caption" sx={{ ...mono, color: FAINT, display: "block", pl: 2.6, fontSize: 9.5 }} noWrap>
                {r.path}
              </Typography>
            )}
            {/* Taskuary knows what this repo IS (SOUL.md) but not where it is. Without a path a
                session cannot open here at all - it would silently land in the default folder. */}
            {open === r.repo && (
              <Box sx={{ mt: 0.75, pl: 2.6 }}>
                <Typography variant="caption" sx={{ color: "#b45309", display: "block", mb: 0.5 }}>
                  Where is {r.repo} checked out on this machine? Saved on the {agent} agent, so every
                  future task routed here uses it.
                </Typography>
                <Box sx={{ display: "flex", gap: 0.75, alignItems: "center" }}>
                  <TextField size="small" fullWidth autoFocus value={path} placeholder="C:\\Users\\you\\Documents\\TopE"
                    onChange={(e) => setPath(e.target.value)}
                    inputProps={{ style: { fontSize: 11.5, fontFamily: "ui-monospace, monospace" } }} />
                  <Button size="small" variant="contained" disableElevation disabled={busy || !path.trim()}
                    onClick={() => choose(r, path.trim())}>Save</Button>
                  <Button size="small" sx={{ color: DIM }} onClick={() => setOpen(null)}>cancel</Button>
                </Box>
              </Box>
            )}
          </Box>
        );
      })}
      {err && <Typography variant="caption" sx={{ color: "#b91c1c", display: "block" }}>{err}</Typography>}
      {picked && (
        <Button size="small" sx={{ fontSize: 10.5, color: DIM }} disabled={busy}
          onClick={async () => { setBusy(true); await api.put(`/api/tasks/${taskId}/repo`, { repo: null, agent }); setBusy(false); load(); onDone?.({}); }}>
          unpin — let Taskuary choose again
        </Button>
      )}
    </Box>
  );
};
