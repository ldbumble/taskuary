// THE ANSWER TO "DID THAT TAKE?" A switch that flips, a box you leave, a rule you save - each of these
// used to post and say nothing either way, so a refusal looked exactly like a success and the owner
// found out a week later that the setting never stuck. One small notice, bottom-left, for both: a
// brief "Saved", or the reason it was not in words, which stays until it is read.
import React, { useCallback, useState } from "react";
import { Button, Snackbar } from "@mui/material";
import { plainError } from "./apiError.js";

export function useSaveNote() {
  const [note, setNote] = useState(null);
  // run(fn, {ok, fail, lead, undo}): success says `ok` ("Saved" by default); a failure says `lead` + why, and throws nothing
  const run = useCallback(async (fn, { ok = "Saved", fail, lead = "Not saved — ", undo } = {}) => {
    try { const r = await fn(); if (ok) setNote({ text: ok, undo, n: Date.now() }); return { ok: true, r }; }
    catch (e) { setNote({ text: lead + plainError(e, fail), bad: true, n: Date.now() }); return { ok: false, e }; }
  }, []);
  const say = useCallback((text, extra = {}) => setNote({ text, ...extra, n: Date.now() }), []);
  const el = (
    <Snackbar key={note?.n || "none"} open={!!note} onClose={(_e, why) => why !== "clickaway" && setNote(null)}
      autoHideDuration={note?.bad ? 9000 : note?.undo ? 7000 : 2200} anchorOrigin={{ vertical: "bottom", horizontal: "left" }}
      message={note?.text}
      ContentProps={{ sx: note?.bad ? { borderLeft: "4px solid #6b2733" } : {} }}
      action={note?.undo ? <Button size="small" onClick={() => { const u = note.undo; setNote(null); u(); }}>Undo</Button> : null} />
  );
  return { run, say, note: el };
}
