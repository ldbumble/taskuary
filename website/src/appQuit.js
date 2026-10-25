// QUIT AND A WAITING UPDATE, said in one place (the owner, 2026-10-25: "Close keeps Taskuary running. Quit is an explicit option" -
// in the browser's top line too). Pure, so the words are pinned by a test and the components only draw them.

// the desktop window has the tray's Quit; this one is for the browser, where nothing else stops the server (pywebview puts its bridge on
// every page it hosts)
export const inDesktop = (w = typeof window === "undefined" ? null : window) => !!(w && w.pywebview);

// the hover says the consequence; the press is the decision (no confirm box - the owner, 2026-10-19)
// `running`: the server's own words for what is live (GET /api/quit - "1 running agent and 1 workflow run")
export const quitTitle = (running = "") => `Quit Taskuary - stops it here${running ? `, and the ${running} with it` : ""}`;

// what the page left behind says: it has stopped, what stopped with it, and how to start it again
export const stoppedLines = (stopped = []) => [
  "Taskuary has stopped",
  stopped.length ? `The work on ${stopped.join(", ")} stopped with it - it waits on your list for when you start Taskuary again.`
    : "Nothing is lost - start Taskuary again and it catches up on everything that came in.",
];

// Update now with work running: it waits, and the card says what for ("Update waits for 1 running agent") until the last one stops
export const updateWaiting = (data) => !!(data && (data.waiting || data.queued));
export const waitingNote = (data) => (updateWaiting(data) ? `${data.waits || "Update waits for running work"} - it starts by itself when that is done.` : "");
