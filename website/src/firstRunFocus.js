// Which AI card stands alone on the first run: the one being checked, else the one whose fix is open - unless the owner asked to
// see them all. Clicking ChatGPT left every other card on the screen, so it looked like nothing happened (2026-10-15).
// `signing`: the card a browser sign-in is under way for (ChatGPT); a fix names its card by `key` when it is not a CLI's
export const focusOf = (st, busy, browsing, signing = null) => browsing ? null : signing || (busy ? `cli-${busy}`
  : st?.step === "ai" && st?.fix?.name ? (st.fix.key || `cli-${st.fix.name}`) : null);

// The sign-in link a CLI's login prints, read off its screen (/api/terminals/{sid}/screen) so the step can offer it as a link instead
// of a terminal: a full row is a wrapped one, so it joins the next without a break (2026-10-15: the raw pane was "broken display").
export const signinUrl = (screen) => {
  const cols = screen?.cols || 0, rows = screen?.lines || [];
  const text = rows.map((l, i) => l + (i < rows.length - 1 && cols && l.length >= cols - 1 ? "" : "\n")).join("");
  return (text.match(/https:\/\/[^\s"'<>]+/) || [""])[0];
};
