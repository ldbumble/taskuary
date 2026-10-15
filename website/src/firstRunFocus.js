// Which AI card stands alone on the first run: the one being checked, else the one whose fix is open - unless the owner asked to
// see them all. Clicking ChatGPT left every other card on the screen, so it looked like nothing happened (2026-10-15).
export const focusOf = (st, busy, browsing) => browsing ? null : busy ? `cli-${busy}` : st?.step === "ai" && st?.fix?.name ? `cli-${st.fix.name}` : null;
