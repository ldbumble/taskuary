// Every "Report this bug" opens one popup: the entry points dispatch, TaskHubPage listens - so a link deep in the chat
// needs no prop threaded down to it. Pure apart from the dispatch, so the request shape can be tested.
export const REPORT_EVENT = "tq-report-bug";
export const openBugReport = (error = null) => window.dispatchEvent(new CustomEvent(REPORT_EVENT, { detail: error }));

// An error the page drew (a receipt, the error line) is usually the sentence over a failure the client just recorded,
// which has the route and stack: read the two together. A bell item is the server's own and stands alone.
export const shownError = (text) => ({ message: String(text || ""), withLast: true });
export const bellError = (p) => ({ message: [p.title, p.detail].filter(Boolean).join("\n"), screen: p.where || "Bell",
  route: p.key ? `problem ${p.key}` : "", at: p.since || "" });

export function draftRequest(snap, e) {
  if (!e) return snap;
  const msg = String(e.message || "").trim();
  if (e.withLast) return { ...snap, error: [...new Set([msg, snap.error].filter(Boolean))].join("\n") };
  return { ...snap, screen: e.screen || snap.screen, error: msg, stack: e.stack || "", route: e.route || "", at: e.at || "" };
}

// what "Copy the error" copies when the draft is refused: what the client knows, unscrubbed - the person decides
export const rawError = (req) => [req?.error, req?.stack].filter(Boolean).join("\n\n") || "No error was recorded.";

// the desktop window has no browser of its own: there the server opens the page in the default browser
export const howToOpen = (w) => (w?.pywebview ? "app" : "tab");
