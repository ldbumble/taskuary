// Settings → Updates: which build is running, which is the latest release, and one button that
// fetches it, swaps it in and comes back - with every connection and setting intact, because all
// of that lives in the data folder and never beside the program (update.py explains the roads).
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, Typography } from "@mui/material";
import SystemUpdateAltIcon from "@mui/icons-material/SystemUpdateAlt";
import api from "./api";
import { BORDER, DIM, FAINT, INK, mono } from "./theme.jsx";

const HOW = {
  exe: "the desktop app (Taskuary.exe) — the new build is downloaded beside the old one and swapped in after this window closes; it reopens by itself",
  pip: "a pip install — `pip install -U taskuary` runs, then the same command line is relaunched",
  source: "a source checkout — update it with `git pull` in the repository, then restart; nothing here can do that for you",
};

export default function UpdateCard() {
  const [info, setInfo] = useState(null);
  const [busy, setBusy] = useState("");          // "check" | "apply" | "restarting"
  const [err, setErr] = useState("");
  const [note, setNote] = useState("");
  const startedRef = useRef(null);

  const check = useCallback(async (force) => {
    setBusy("check"); setErr("");
    try { setInfo((await api.get(`/api/update${force ? "?force=1" : ""}`)).data); }
    catch (e) {
      // an older server, or the static demo: still say which build this is, from the route
      // every install has - "Running v..." forever is the one thing this card must never show
      try { const { data } = await api.get("/api/version"); setInfo({ current: data.version, how: "exe", latest: null, newer: false, error: null }); }
      catch { /* nothing answers: the message below says so */ }
      setErr(e?.response?.data?.detail || "update checks are not available here");
    }
    setBusy("");
  }, []);
  useEffect(() => { check(false); }, [check]);

  // After the swap the old process is gone for a few seconds. Poll /api/version until a NEW
  // version answers, then reload so the page runs the new bundle too.
  const waitForNew = useCallback(async (was) => {
    startedRef.current = Date.now();
    for (;;) {
      await new Promise((r) => setTimeout(r, 2000));
      try {
        const { data } = await api.get("/api/version");
        if (data.version && data.version !== was) { window.location.reload(); return; }
      } catch { /* still restarting */ }
      if (Date.now() - startedRef.current > 180000) { setBusy(""); setErr("the new build did not come back within three minutes — start Taskuary by hand; your data is untouched"); return; }
    }
  }, []);

  const apply = async () => {
    setBusy("apply"); setErr(""); setNote("");
    try {
      const { data } = await api.post("/api/update", {});
      if (data.restarting) { setBusy("restarting"); setNote(data.how === "exe" ? "downloaded — swapping the program and reopening…" : "installed — relaunching…"); await waitForNew(info?.current); }
      else { setNote(data.detail || "done"); setBusy(""); }
    } catch (e) { setErr(e?.response?.data?.detail || "the update did not start"); setBusy(""); }
  };

  const how = info?.how || "exe";
  const canApply = !!info && info.newer && !info.error && how !== "source";
  return (
    <Box sx={{ maxWidth: 720 }}>
      <Typography variant="body2" sx={{ color: DIM, mb: 1.5, lineHeight: 1.6 }}>
        Everything you have set up — connections, tokens, the database, your documents and playbooks — lives in
        the data folder, never beside the program. An update only swaps the program, so all of it is exactly
        where you left it when the new build opens.
      </Typography>
      <Box sx={{ p: 1.75, border: `1px solid ${BORDER}`, borderRadius: 2, bgcolor: "#fff" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, flexWrap: "wrap" }}>
          <SystemUpdateAltIcon sx={{ fontSize: 22, color: "#55697a" }} />
          <Box sx={{ flex: 1, minWidth: 220 }}>
            <Typography sx={{ fontWeight: 700, color: INK, fontSize: 13.5 }}>
              Running <Box component="span" sx={{ ...mono }}>v{info?.current || "…"}</Box>
              {info?.latest && (
                <Box component="span" sx={{ color: info.newer ? "#6b2733" : "#47654a", fontWeight: 600, ml: 1, fontSize: 12.5 }}>
                  {info.newer ? `· v${info.latest} is out` : "· this is the latest"}
                </Box>
              )}
            </Typography>
            <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 0.25 }}>
              This is {HOW[how]}.
            </Typography>
          </Box>
          <Button size="small" variant="outlined" disabled={!!busy} onClick={() => check(true)}
            startIcon={busy === "check" ? <CircularProgress size={12} /> : null}>Check now</Button>
          <Button size="small" variant="contained" disableElevation disabled={!canApply || !!busy} onClick={apply}
            startIcon={busy === "apply" || busy === "restarting" ? <CircularProgress size={12} sx={{ color: "#fff" }} /> : null}
            title={how === "source" ? "a source checkout updates with git pull" : info?.newer ? `install v${info.latest} and reopen` : "nothing newer to install"}>
            {busy === "restarting" ? "Reopening…" : busy === "apply" ? "Updating…" : info?.newer ? `Update to v${info.latest}` : "Up to date"}
          </Button>
        </Box>
        {info?.notes && info.newer && (
          <Typography variant="caption" sx={{ display: "block", mt: 1, color: FAINT }}>
            What changed:{" "}
            <Box component="a" href={info.notes} target="_blank" rel="noopener" sx={{ color: "#55697a" }}>release notes</Box>
          </Typography>
        )}
        {note && <Alert severity="info" sx={{ mt: 1.25, fontSize: 12.5 }}>{note}</Alert>}
        {(err || info?.error) && <Alert severity={err ? "error" : "warning"} sx={{ mt: 1.25, fontSize: 12.5 }}>{err || info.error}</Alert>}
      </Box>
      <Typography variant="caption" sx={{ color: FAINT, display: "block", mt: 1.25, lineHeight: 1.6 }}>
        Releases come from the project's GitHub page; the desktop build is the same file you would download there.
        Any agent session that is open when you update is closed with the program — its transcript is kept on its task.
      </Typography>
    </Box>
  );
}
