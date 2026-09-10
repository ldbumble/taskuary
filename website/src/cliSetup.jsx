// Setting a coding CLI up, shared by the setup wizard and the AI CLI agents page.
//
// The Install button ended on a CLI that had never been run, and the app's own answer to that was
// a sentence telling the owner to open a terminal. Taskuary has had an interactive pty all along:
// this opens the CLI in it, as an ordinary setup task, so the pane is on the Board and Done closes
// it the way it closes any other setup session.
//
// What opens is the CLI, plain. It has an onboarding of its own - recommended settings, then the
// sign-in - and it asks better than we could ask on its behalf. Nothing is typed for the owner,
// and nothing here reads what they type back.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@mui/material";
import TerminalIcon from "@mui/icons-material/Terminal";
import api from "./api";
import { SessionPane } from "./TerminalView.jsx";
import { canSetup, setupTitle } from "./cliSetup.js";

export { canSetup, setupTitle };

export const useCliSetup = () => {
  const [opening, setOpening] = useState("");
  const [pane, setPane] = useState(null);              // { sid, taskId, name }
  const [note, setNote] = useState(null);              // { bad, text }
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const openSetup = useCallback(async (cli) => {
    const name = typeof cli === "string" ? cli : cli?.setup || "";
    if (!name) { setNote({ bad: true, text: "Taskuary does not know how to set that one up" }); return null; }
    const put = (fn, v) => { if (alive.current) fn(v); };
    put(setOpening, name); put(setNote, null);
    try {
      const { data } = await api.post("/api/cli/setup", { name });
      put(setPane, { sid: data.sid, taskId: data.taskId, name });
      // a second press reattaches: say so, or the owner waits for a pane that is already theirs
      put(setNote, { text: data.existing ? "that set-up is already open — it is the pane below"
                                         : "answer it in the pane below — it will ask for its settings, then the sign-in" });
      put(setOpening, ""); return data;
    } catch (e) {
      put(setNote, { bad: true, text: e?.response?.data?.detail || e?.message || "that did not work" });
      put(setOpening, ""); return null;
    }
  }, []);

  return { openSetup, opening, pane, setPane, note, setNote };
};

export const SetupButton = ({ cli, opening, onOpen, sx = {} }) => {
  if (!canSetup(cli)) return null;
  return (
    <Button size="small" variant="outlined" disabled={!!opening} onClick={() => onOpen(cli)}
      startIcon={<TerminalIcon sx={{ fontSize: 14 }} />} title={setupTitle(cli)}
      sx={{ fontSize: 11.5, whiteSpace: "nowrap", ...sx }}>
      {opening === cli.setup ? "opening…" : "Set it up"}
    </Button>
  );
};

// The pane itself, wherever the caller puts it. One session id - the Board is showing the same one.
export const CliPane = ({ pane, height = "46vh" }) => (pane?.sid ? <SessionPane sid={pane.sid} height={height} /> : null);
