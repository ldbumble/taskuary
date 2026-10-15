// What setup mode's rail shows (SetupSteps.jsx): each step, done or not, and the one that is next - from the first run's own state.
export const stepsOf = (st) => {
  if (!st) return [];
  const mailIn = st.step === "reading" || st.step === "done";
  const rows = [
    { key: "ai", label: "Your AI", done: st.step !== "ai", sub: st.step !== "ai" ? st.brain?.name || "" : "" },
    { key: "mail", label: "Your email", done: mailIn, sub: mailIn ? "connected" : "" },
    { key: "about", label: "About your work", done: !!st.about_done, sub: st.about_done ? "saved" : "" },
    { key: "other", label: "More connections", done: false, optional: true, sub: "optional" },
    { key: "finish", label: "Finish", done: !!st.dismissed, sub: st.step === "done" ? "ready" : st.step === "reading" ? "sorting your mail" : "" },
  ];
  const at = rows.find((r) => !r.done && !r.optional && (r.key !== "about" || mailIn))?.key
    || (mailIn && st.about_done ? "finish" : "");
  return rows.map((r) => ({ ...r, current: r.key === at }));
};
