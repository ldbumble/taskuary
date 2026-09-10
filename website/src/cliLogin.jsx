// The Sign in button for a coding CLI, shared by the setup wizard and the AI CLI agents page.
//
// The Install button ended on a CLI with no credentials, and the app's own answer to that was a
// sentence telling the owner to open a terminal. Taskuary has had an interactive pty all along:
// this opens the CLI's own sign-in in it, as an ordinary setup task, so the pane is on the Board
// and Done closes it the way it closes any other setup session.
//
// Nothing here types a credential. The CLI's own `/login` is typed server-side; what the owner
// enters, they enter themselves, in the pane, watching it go in.
import React, { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@mui/material";
import LoginIcon from "@mui/icons-material/Login";
import api from "./api";
import { SessionPane } from "./TerminalView.jsx";
import { canSignIn, signInTitle } from "./cliLogin.js";

export { canSignIn, signInTitle };

export const useCliLogin = () => {
  const [opening, setOpening] = useState("");
  const [pane, setPane] = useState(null);              // { sid, taskId, name }
  const [note, setNote] = useState(null);              // { bad, text }
  const alive = useRef(true);
  useEffect(() => () => { alive.current = false; }, []);

  const signIn = useCallback(async (cli) => {
    const name = typeof cli === "string" ? cli : cli?.login || "";
    if (!name) { setNote({ bad: true, text: "Taskuary does not know how to sign that one in" }); return null; }
    const put = (fn, v) => { if (alive.current) fn(v); };
    put(setOpening, name); put(setNote, null);
    try {
      const { data } = await api.post("/api/cli/login", { name });
      put(setPane, { sid: data.sid, taskId: data.taskId, name });
      // a second press reattaches: say so, or the owner waits for a pane that is already theirs
      put(setNote, { text: data.existing ? "that sign-in is already open — it is the pane below"
                                         : "finish the sign-in in the pane below" });
      put(setOpening, ""); return data;
    } catch (e) {
      put(setNote, { bad: true, text: e?.response?.data?.detail || e?.message || "that did not work" });
      put(setOpening, ""); return null;
    }
  }, []);

  return { signIn, opening, pane, setPane, note, setNote };
};

export const SignInButton = ({ cli, opening, onSignIn, sx = {} }) => {
  if (!canSignIn(cli)) return null;
  return (
    <Button size="small" variant="outlined" disabled={!!opening} onClick={() => onSignIn(cli)}
      startIcon={<LoginIcon sx={{ fontSize: 14 }} />} title={signInTitle(cli)}
      sx={{ fontSize: 11.5, whiteSpace: "nowrap", ...sx }}>
      {opening === cli.login ? "opening…" : "Sign in"}
    </Button>
  );
};

// The pane itself, wherever the caller puts it. One session id - the Board is showing the same one.
export const LoginPane = ({ pane, height = "46vh" }) => (pane?.sid ? <SessionPane sid={pane.sid} height={height} /> : null);
