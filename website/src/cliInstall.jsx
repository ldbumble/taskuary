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
import UpgradeIcon from "@mui/icons-material/Upgrade";
import api from "./api";
import { FAINT } from "./theme.jsx";

const POLL_MS = 1500, GIVE_UP_MS = 12 * 60 * 1000;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
// the recipe to install, however the caller holds the row
export const recipeOf = (cli) => (typeof cli === "string" ? cli : cli?.install || "");
// Install and update are one errand with two verbs - post once, then poll the single global
// phase the server keeps for both. `codex update` takes a minute on a slow line for the same
// reason `npm install -g` does, which is why neither holds a request open.
const VERBS = { install: { path: "/api/cli/install", ing: "installing", noun: "installer" },
                update: { path: "/api/cli/update", ing: "updating", noun: "updater" } };

export const useCliInstall = ({ terminal = false } = {}) => {
  const [busy, setBusy] = useState("");
  const [pane, setPane] = useState(null);
  const [note, setNote] = useState(null);              // { bad, text }
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const run = useCallback(async (cli, verb) => {
    const v = VERBS[verb], name = recipeOf(cli);
    if (!name) { setNote({ bad: true, text: `Taskuary has no ${v.noun} for that one` }); return null; }
    const put = (fn, x) => { if (alive.current) fn(x); };
    put(setBusy, name); put(setNote, { text: `${v.ing} ${name}…` });
    try {
      if (terminal) {
        const { data } = await api.get('/api/version');
        if ((data.cli_installer_revision || 0) < 2) {
          put(setBusy, '');
          put(setNote, { bad: true, text: 'Taskuary is still running the previous installer. Restart Taskuary before trying again; no installer was started.' });
          return null;
        }
      }
      const started = await api.post(terminal ? `${v.path}/terminal` : v.path, { name, ...(terminal ? { terminal: true } : {}) });
      if (started.data.sid) put(setPane, { sid: started.data.sid, taskId: started.data.taskId, name, verb });
      else if (terminal) {
        put(setBusy, ""); put(setNote, { bad: true, text: "This server started the installer in the background. Restart Taskuary to enable the installation terminal." });
        return null;
      }
      const end = Date.now() + GIVE_UP_MS;
      for (;;) {
        await wait(POLL_MS);
        if (!alive.current) return null;
        const { data } = await api.get("/api/cli/install/state");
        // the phase is global: only trust it while it is still about the CLI we asked for
        if (data.name && data.name !== name) { put(setBusy, ""); put(setNote, { bad: true, text: `${data.name} is busy right now — try again after it` }); return null; }
        // the SERVER'S own words on the way out: an updater that says what it did beats us
        // saying "done" over the top of it
        if (data.phase === "done") { put(setBusy, ""); put(setNote, { text: data.detail || `${name} is ready` }); return data; }
        if (data.phase === "failed") { put(setBusy, ""); put(setNote, { bad: true, text: data.detail || `could not ${verb} ${name}` }); return null; }
        if (data.detail) put(setNote, { text: data.detail });
        // the server only ever runs one at a time, and a phase that never lands must not poll forever
        if (Date.now() > end) { put(setBusy, ""); put(setNote, { bad: true, text: `${name} is still ${v.ing} — check back in a minute` }); return null; }
      }
    } catch (e) {
      put(setNote, { bad: true, text: terminal && e?.response?.status === 404 ? "Restart Taskuary to enable the installation terminal." : e?.response?.data?.detail || e?.message || "that did not work" });
      put(setBusy, ""); return null;
    }
  }, [terminal]);

  const install = useCallback((cli) => run(cli, "install"), [run]);
  const update = useCallback((cli) => run(cli, "update"), [run]);
  return { install, update, busy, note, setNote, pane, setPane };
};

// "not on this machine — Install". Drawn only where there is a way in: `installable` is the
// server saying it has a recipe that can run on THIS operating system (cursor's installer is
// bash-only, so on Windows the row says so instead of offering a button that cannot work).
export const InstallLine = ({ cli, busy, onInstall, sx = {} }) => {
  if (cli.installed) return null;
  // `why_not` is the server saying WHICH wall this is (no Node, or an installer that refuses
  // this OS). Naming it beats "cannot install this one for you", which left the owner unable
  // to tell a missing dependency from an unsupported platform.
  if (!cli.installable) {
    return <Typography variant="caption" sx={{ color: FAINT, ...sx }}>
      not on this machine — {cli.why_not || "Taskuary cannot install this one for you"}
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

// "Update" - for a CLI that is HERE and too old to do its job. Nothing about that failure looks
// like a version problem from the outside: the CLI exits 1 on every single run, and the reason is
// one sentence inside the JSON it writes to stdout (the owner, 2026-09-11 - codex 0.148.0
// answering "requires a newer version of Codex" to every question a walkthrough asked it).
// `updatable` is the server saying this one has an updater AND is actually installed, so the
// button is never drawn over a road that does not exist - the same rule as `installable`.
export const UpdateLine = ({ cli, busy, onUpdate, sx = {} }) => {
  if (!cli?.updatable) return null;
  return (
    <Button size="small" variant="text" disabled={!!busy} onClick={() => onUpdate(cli)}
      startIcon={<UpgradeIcon sx={{ fontSize: 15 }} />}
      title={`Run ${cli.label}'s own updater on this machine. A CLI too old for the model it is configured with fails every run.`}
      sx={{ fontSize: 11.5, whiteSpace: "nowrap", color: FAINT, ...sx }}>
      {busy === recipeOf(cli) ? "updating…" : "Update"}
    </Button>
  );
};
