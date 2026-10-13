import { useState } from "react";
import { Box, Button, Link, Typography } from "@mui/material";
import api from "./api";
import { Confirm } from "./ui.jsx";
import { ACCENT2, ALERT, ALERT_INK, BORDER, DIM, FAINT, INK, label } from "./theme.jsx";
import { actions, circled, fixLine, isOpen, progress, stateWord } from "./batchItems.js";

// The items of a batch, in ranked order, each with what the agent found and the owner's presses for it (batch.py). A line
// waiting on you never holds up the next one; the task closes when the last line is settled.
export default function BatchItems({ taskId, items = [], onChanged, bare = false }) {
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");
  const [ask, setAsk] = useState(null);
  // a repository not yet set up to fix in the cloud (cloudfix.setup_state): the workflow is one press, the secret is the owner's own
  const [setup, setSetup] = useState(null);
  if (!items?.length) return null;
  const press = async (i, a) => {
    setBusy(`${i.Place}:${a.action}`); setErr("");
    try {
      const { data } = await api.post(`/api/tasks/${taskId}/batch/${i.Place}`, { action: a.action });
      if (data?.setup) { setSetup({ ...data.setup, why: data.why, i, a }); return; }
      setSetup(null); onChanged?.();
    }
    catch (e) { setErr(`${circled(i.Place)} ${a.label} did not go through - ${e?.response?.data?.detail || "Taskuary didn't answer"}.`); }
    finally { setBusy(null); }
  };
  // a merge leaves this machine for GitHub: said once, with what it merges, before it goes
  const go = (i, a) => (a.action === "merge" ? setAsk({ i, a }) : press(i, a));
  const install = async () => {
    setBusy("setup"); setErr("");
    try { const { data } = await api.post("/api/cloudfix/setup", { repo: setup.repo }); setSetup({ ...setup, ...data }); }
    catch (e) { setErr(`The workflow was not added - ${e?.response?.data?.detail || "Taskuary didn't answer"}.`); }
    finally { setBusy(null); }
  };
  return (
    <Box sx={{ mt: 1, maxWidth: 900 }}>
      {!bare && <Typography sx={{ ...label, mb: 0.4 }}>{progress(items)}</Typography>}
      {items.map((i) => {
        const you = i.State === "needs_you";
        return (
          <Box key={i.Place} sx={{ display: "grid", gridTemplateColumns: "22px minmax(0,1fr) auto", columnGap: 1, py: 0.9,
            borderTop: `1px solid ${BORDER}`, alignItems: "start" }}>
            <Typography sx={{ color: FAINT, fontSize: 15, lineHeight: 1.4, textAlign: "center" }}>{circled(i.Place)}</Typography>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="body2" sx={{ color: isOpen(i) ? INK : FAINT, fontWeight: 500, overflowWrap: "anywhere" }}>
                {i.Link ? <Link href={i.Link} target="_blank" rel="noreferrer" underline="hover" color="inherit">{i.Title}</Link> : i.Title}
              </Typography>
              {(i.Result || i.EndedWhy) && (
                <Typography variant="body2" sx={{ color: DIM, mt: 0.2, lineHeight: 1.5, overflowWrap: "anywhere" }}>
                  {i.State === "ended" ? i.EndedWhy : i.Result}</Typography>)}
              {i.Overlap && isOpen(i) && (
                <Typography variant="caption" sx={{ color: DIM, display: "block", mt: 0.2 }}>Overlaps: {i.Overlap}</Typography>)}
              {/* stage two (batch.screen): a stranger's change cleared to build and test here, or why it stays read-only */}
              {i.Screen && isOpen(i) && (
                <Typography variant="caption" sx={{ color: /^clear/.test(i.Screen) ? ACCENT2 : DIM, display: "block", mt: 0.2 }}>
                  {/^clear/.test(i.Screen) ? `Cleared to run here${i.Screen.replace(/^clear\s*-?\s*/, " - ")}` : `Read-only here: ${i.Screen.replace(/^held\s*-\s*/, "")}`}
                </Typography>)}
              {fixLine(i) && (
                <Typography variant="caption" sx={{ color: i.Fix === "failed" ? ALERT_INK : DIM, display: "block", mt: 0.2 }}>
                  {fixLine(i)}{i.FixLink && i.Fix === "failed" ? <> <Link href={i.FixLink} target="_blank" rel="noreferrer">Its run on GitHub</Link></> : null}
                </Typography>)}
              {!i.Result && i.State === "waiting" && (
                <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.2 }}>The agent has not reached it yet.</Typography>)}
              <Box sx={{ display: "flex", gap: 0.75, mt: 0.5, flexWrap: "wrap" }}>
                {actions(i).map((a) => (
                  <Button key={a.action} size="small" variant={a.primary ? "contained" : "outlined"} disableElevation
                    disabled={!!busy} {...(a.href ? { href: a.href, target: "_blank", rel: "noreferrer" } : { onClick: () => go(i, a) })}
                    sx={{ textTransform: "none", py: 0, minHeight: 26, fontSize: 12.5,
                      ...(a.primary ? { bgcolor: ALERT, "&:hover": { bgcolor: ALERT_INK } } : { color: INK, borderColor: BORDER }) }}>
                    {busy === `${i.Place}:${a.action}` ? "…" : a.label}
                  </Button>
                ))}
              </Box>
            </Box>
            <Typography variant="caption" sx={{ color: you ? ALERT_INK : i.State === "done" || i.State === "ended" ? ACCENT2 : FAINT,
              fontWeight: you ? 600 : 400, whiteSpace: "nowrap", pt: 0.2 }}>{stateWord(i)}</Typography>
          </Box>
        );
      })}
      {setup && (
        <Box sx={{ mt: 0.75, p: 1.25, border: `1px solid ${BORDER}`, borderRadius: "8px" }}>
          <Typography variant="body2" sx={{ color: INK, fontWeight: 600 }}>Fix outside pull requests on {setup.repo} in GitHub's cloud</Typography>
          <Typography variant="body2" sx={{ color: DIM, mt: 0.3, lineHeight: 1.5 }}>
            {setup.workflow ? "The workflow is in place." : "Taskuary adds a workflow to the repository: the agent and the tests run on a machine GitHub throws away, never yours."}
            {" "}{setup.secret === true ? "The secret is set." : <>It also needs a secret named <b>{setup.secret_name}</b>: run <code>claude setup-token</code> and paste the result <Link href={setup.secret_url} target="_blank" rel="noreferrer">on GitHub</Link>.</>}
          </Typography>
          <Box sx={{ display: "flex", gap: 0.75, mt: 0.75, flexWrap: "wrap" }}>
            {!setup.workflow && <Button size="small" variant="contained" disableElevation disabled={!!busy} onClick={install}
              sx={{ textTransform: "none", py: 0, minHeight: 26, fontSize: 12.5 }}>{busy === "setup" ? "…" : "Add the workflow"}</Button>}
            {setup.workflow && setup.secret !== false && <Button size="small" variant="contained" disableElevation disabled={!!busy}
              onClick={() => press(setup.i, setup.a)} sx={{ textTransform: "none", py: 0, minHeight: 26, fontSize: 12.5 }}>Fix it now</Button>}
            <Button size="small" variant="outlined" onClick={() => setSetup(null)}
              sx={{ textTransform: "none", py: 0, minHeight: 26, fontSize: 12.5, color: INK, borderColor: BORDER }}>Not now</Button>
          </Box>
        </Box>)}
      {/* an outsider's changes are made only in GitHub's cloud, and that is off: said once, quietly, instead of a button that refuses */}
      {items.some((i) => i.canFix === false && i.Propose === "changes" && isOpen(i)) && (
        <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.6 }}>
          An outside contributor's change runs on this machine only once it clears the safety screen; until then it is fixed only in
          GitHub's cloud. To have that done for you, turn on Settings → Agent permissions → Outside pull requests → fix in GitHub's cloud.</Typography>)}
      {err && <Typography variant="caption" sx={{ color: ALERT_INK, display: "block", mt: 0.5 }}>{err}</Typography>}
      <Confirm open={!!ask} title={ask ? `Merge ${ask.i.Title}?` : ""} confirmLabel="Merge on GitHub"
        text="It merges the version the agent reviewed. If anything was pushed to it since, GitHub refuses and nothing is merged."
        onConfirm={() => press(ask.i, ask.a)} onClose={() => setAsk(null)} />
    </Box>
  );
}
