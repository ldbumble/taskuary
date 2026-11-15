// QUIT AND A WAITING UPDATE, said in one place (the owner, 2026-10-25: "Close keeps Taskuary running. Quit is an explicit option" -
// in the browser's top line too). Pure, so the words are pinned by a test and the components only draw them.

// the desktop window has the tray's Quit; this one is for the browser, where nothing else stops the server (pywebview puts its bridge on
// every page it hosts)
export const inDesktop = (w = typeof window === "undefined" ? null : window) => !!(w && w.pywebview);

// the hover says the consequence; the press is the decision (no confirm box - the owner, 2026-10-19)
// `running`: the server's own words for what is live (GET /api/quit - "1 running agent and 1 workflow run")
export const quitTitle = (running = "") => `Quit Taskuary - stops it here${running ? `, and the ${running} with it` : ""}`;

// what the page left behind says: SHUTTING DOWN while the server still answers (the owner, 2026-11-13: "it should say shutting down if it
// needs a few seconds to close") - then it has stopped, what stopped with it, and how to start it again
export const stoppedLines = (stopped = [], down = true) => !down
  ? ["Shutting down…", `Stopping ${stopped.length ? `the work on ${stopped.join(", ")} and ` : ""}what Taskuary started - this takes a few seconds.`] : [
  "Taskuary has stopped",
  stopped.length ? `The work on ${stopped.join(", ")} stopped with it - it waits on your list for when you start Taskuary again.`
    : "Nothing is lost - start Taskuary again and it catches up on everything that came in.",
];

// Update now with work running: it waits, and the card says what for ("Update waits for 1 running agent") until the last one stops
export const updateWaiting = (data) => !!(data && (data.waiting || data.queued));
export const waitingNote = (data) => (updateWaiting(data) ? `${data.waits || "Update waits for running work"} - it starts by itself when that is done.` : "");
// WHICH INSTALL THIS IS, AND SO HOW IT UPDATES (update.how). A road with no words here - the demo answers "demo" - says nothing: it read "This is ."
const HOW = {
  setup: "the installed desktop app — the new installer is downloaded and runs quietly after this window closes; it reopens by itself. Windows asks for your OK only if Taskuary was installed for all users",
  exe: "the one-file desktop app (Taskuary.exe) — the installer is downloaded and runs quietly after this window closes; Taskuary moves into its installed home with a Start menu entry, the one file is removed, and it reopens by itself",
  pip: "a pip install — `pip install -U taskuary` runs, then the same command line is relaunched",
  source: "a source checkout — update it with `git pull` in the repository, then restart; nothing here can do that for you",
};
export const howLine = (how) => (HOW[how] ? `This is ${HOW[how]}.` : "");
