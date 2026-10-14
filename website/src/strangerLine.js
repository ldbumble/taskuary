// The card's one line for a stranger's task (origin.py): null for the owner's and trusted work, so nothing renders for them.
export const strangerLine = (d) => d?.origin?.origin === "stranger" ? { text: "Stranger's words · runs in auto mode", why: d.origin.why || "" } : null;
