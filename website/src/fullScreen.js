// AN AGENT SCREEN, GIVEN THE WHOLE WINDOW.
//
// Every surface that shows an agent working is a panel inside something else: the walk sits in a
// column beside the pipe, a Wall tile is one of four across, the Timeline drawer pins its agent tab
// to 480px. That is right for glancing and wrong for watching - and once a browser is beside the
// conversation it is very wrong, because two panes are sharing a box that was only ever sized for
// one (the owner, 2026-09-14: "make the agent chat full screen and you can do it side by side").
//
// So this is a mode, not a route: the pane it belongs to covers the window where it stands, and Esc
// or the button puts it back. Nothing is remembered - full screen is a moment, not a preference.
import { useCallback, useEffect, useState } from "react";

export const FULL_Z = 1250;          // above the app's own chrome, below MUI's modals (1300)

// What a full-screen pane's own sx becomes. `inset: 0` with width/height cleared beats whatever
// height the panel was given where it is mounted (a Wall tile's "340px", the drawer's 480).
export const FULL_SX = { position: "fixed", inset: 0, width: "auto", height: "auto", maxWidth: "none",
  maxHeight: "none", margin: 0, borderRadius: 0, zIndex: FULL_Z };

// Only ONE screen is full at a time. Two agents blown up at once are two fixed panes stacked on the
// same pixels, and the one underneath is unreachable without guessing at Esc.
let closeOther = null;

export function useFullScreen() {
  const [full, setFull] = useState(false);
  const toggle = useCallback(() => setFull((f) => !f), []);
  useEffect(() => {
    if (!full) return undefined;
    if (closeOther && closeOther !== setFull) closeOther(false);
    closeOther = setFull;
    const onKey = (e) => { if (e.key === "Escape") setFull(false); };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (closeOther === setFull) closeOther = null;
    };
  }, [full]);
  return { full, setFull, toggle };
}
