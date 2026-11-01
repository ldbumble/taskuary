// Every "Report this bug" opens one popup: the entry points dispatch, TaskHubPage listens - so a link deep in the chat
// needs no prop threaded down to it. Pure apart from the dispatch, so the request shape can be tested.
export const REPORT_EVENT = "tq-report-bug";
export const openBugReport = (error = null) => window.dispatchEvent(new CustomEvent(REPORT_EVENT, { detail: error }));

// An error the page drew (a receipt, the error line) is usually the sentence over a failure the client just recorded,
// which has the route and stack: read the two together. A bell item is the server's own and stands alone.
export const shownError = (text) => ({ message: String(text || ""), withLast: true });
export const bellError = (p) => ({ message: [p.title, p.detail].filter(Boolean).join("\n"), screen: p.where || "Bell",
  route: p.key ? `problem ${p.key}` : "", at: p.since || "" });
// ...and a connection Check again could not fix: the server's words too, so the client's last failure is not mixed in
export const connError = (card, said) => ({ message: [card.title, said].filter(Boolean).join("\n"), screen: "Connection card",
  route: card.channel ? `connector ${card.channel}` : "", at: card.when || "" });

// A REPORT THE OWNER ASKED FOR (the Assistant's issue.draft, an Advisor "Report this?" - 2026-11-01) carries its kind and their words. A wish
// stands alone - no error, stack, route or actions; a bug reads beside the page's last failure only when the Assistant was asked right after it
const asked = (e) => ({ kind: e.kind, trying: String(e.trying || ""), happened: String(e.happened || "") });

export function draftRequest(snap, e) {
  if (!e) return snap;
  const msg = String(e.message || "").trim();
  if (e.kind === "feature") return { ...snap, screen: e.screen || snap.screen, error: "", stack: "", route: "", at: "", actions: [], ...asked(e) };
  if (e.kind && !e.withLast) return { ...snap, screen: e.screen || snap.screen, error: msg, stack: e.stack || "", route: e.route || "", at: e.at || "", ...asked(e) };
  if (e.kind) return { ...snap, screen: e.screen || snap.screen, error: [...new Set([msg, snap.error].filter(Boolean))].join("\n"), ...asked(e) };
  if (e.withLast) return { ...snap, error: [...new Set([msg, snap.error].filter(Boolean))].join("\n") };
  return { ...snap, screen: e.screen || snap.screen, error: msg, stack: e.stack || "", route: e.route || "", at: e.at || "" };
}

// what "Copy the error" copies when the draft is refused: what the client knows, unscrubbed - the person decides
export const rawError = (req) => [req?.error, req?.stack].filter(Boolean).join("\n\n") || "No error was recorded.";

// the desktop window has no browser of its own: there the server opens the page in the default browser
export const howToOpen = (w) => (w?.pywebview ? "app" : "tab");

// A SEARCH UNDER CONNECTIONS THAT FOUND NO CARD (the owner, 2026-11-01): the same wish concierge.no_card files when "connect X" has no card.
// A name reads as one only when it looks like a product - short and plain; anything else is asked for as "this connection"
export const connectName = (q) => { const s = String(q || "").trim().replace(/\s+/g, " ");
  return s.length >= 2 && s.length <= 40 && /^[\p{L}\p{N}][\p{L}\p{N} .&+'-]*$/u.test(s) ? s : ""; };
export const connectionWish = (q) => { const name = connectName(q);
  return { kind: "feature", screen: "Connections", trying: `Find a card under Connections for ${name || String(q || "").trim().slice(0, 200)}`,
           happened: `A card under Connections for ${name || "a system I searched for"}, so Taskuary can connect to it` }; };
