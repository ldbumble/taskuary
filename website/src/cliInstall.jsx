// The Install button for a coding CLI, shared by the setup wizard and the AI CLI agents page.
// Both had the same dead end: "not installed on this machine", and nothing to press.
//
// The install runs in a thread on the server (a whole CLI over npm is a minute on a slow line),
// so this posts once and then polls the phase. What comes back that matters is `path` - the
// ABSOLUTE path of the binary. A GUI app keeps the PATH it was launched with, so a profile saved
// as bare "claude" works tomorrow; one saved as the path the installer just reported works now.
//
// What gets posted is the row's `install` - the RECIPE it is an install of - never its name: a
// profile is named for its job, and every install ships one called "coder".
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Button, Typography } from "@mui/material";
import DownloadIcon from "@mui/icons-material/Download";
import api from "./api";
import { FAINT } from "./theme.jsx";

const POLL_MS = 1500, GIVE_UP_MS = 12 * 60 * 1000;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
// the recipe to install, however the caller holds the row
export const recipeOf = (cli) => (typeof cli === "string" ? cli : cli?.install || "");

export const useCliInstall = () => {
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState(null);              // { bad, text }
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const install = useCallback(async (cli) => {
    const name = recipeOf(cli);
    if (!name) { setNote({ bad: true, text: "Taskuary has no installer for that one" }); return null; }
    const put = (fn, v) => { if (alive.current) fn(v); };
    put(setBusy, name); put(setNote, { text: `installing ${name}…` });
    try {
      await api.post("/api/cli/install", { name });
      const end = Date.now() + GIVE_UP_MS;
      for (;;) {
        await wait(POLL_MS);
        if (!alive.current) return null;
        const { data } = await api.get("/api/cli/install/state");
        // the phase is global: only trust it while it is still about the CLI we asked for
        if (data.name && data.name !== name) { put(setBusy, ""); put(setNote, { bad: true, text: `${data.name} is installing right now — try again after it` }); return null; }
        if (data.phase === "done") { put(setBusy, ""); put(setNote, { text: `${name} is installed` }); return data; }
        if (data.phase === "failed") { put(setBusy, ""); put(setNote, { bad: true, text: data.detail || `could not install ${name}` }); return null; }
        if (data.detail) put(setNote, { text: data.detail });
        // the server only ever runs one at a time, and a phase that never lands must not poll forever
        if (Date.now() > end) { put(setBusy, ""); put(setNote, { bad: true, text: `${name} is still installing — check back in a minute` }); return null; }
      }
    } catch (e) {
      put(setNote, { bad: true, text: e?.response?.data?.detail || e?.message || "that did not work" });
      put(setBusy, ""); return null;
    }
  }, []);

  return { install, busy, note, setNote };
};

// "not on this machine — Install". Drawn only where there is a way in: `installable` is the
// server saying it has a recipe that can run on THIS operating system (cursor's installer is
// bash-only, so on Windows the row says so instead of offering a button that cannot work).
export const InstallLine = ({ cli, busy, onInstall, sx = {} }) => {
  if (cli.installed) return null;
  if (!cli.installable) {
    return <Typography variant="caption" sx={{ color: FAINT, ...sx }}>
      not on this machine — Taskuary cannot install this one for you
    </Typography>;
  }
  return (
    <Button size="small" variant="outlined" disabled={!!busy} onClick={() => onInstall(cli)}
      startIcon={<DownloadIcon sx={{ fontSize: 14 }} />}
      title={`Download and install ${cli.label} on this machine, and put it on your PATH`}
      sx={{ fontSize: 11.5, whiteSpace: "nowrap", ...sx }}>
      {busy === recipeOf(cli) ? "installing…" : "Install"}
    </Button>
  );
};
