// AN ITEM ON THE PROMPT BOX AS A CHIP (the owner, 2026-11-05: "attach the report or fyi list to the prompt box on bottom and make them type in"):
// the item's own ItemSections takes the hand (takeHands) and draws its Agent tab's box with the item a chip on it; his words start the agent.
// `hand`: { verb, items: [{ key, title }], start({ verb, text, files, items }) }. false: no box of the item's is drawn to take it
const HANDS = new Map();
export const handToItem = (key, hand) => { const f = key && HANDS.get(key); if (!f) return false; f(hand); return true; };
export const takeHands = (key, f) => { HANDS.set(key, f); return () => { if (HANDS.get(key) === f) HANDS.delete(key); }; };

// ONE MOVE ON AN ARRIVAL IN THE LIST (the owner, 2026-11-25: under a marketing mail the row stood Make it a task, Send to coding agent, Send to
// agent, Not for me and Talk about it): a message not yet on a task has Send to agent - the press puts it, and the list's other messages, on the
// box as chips, the pressed one first; one agent starts on the first chip left, the rest named for it to read. `moved`: the line went to a task
export const whoName = (w) => String(w || "someone").replace(/\s*<[^>]*>/g, "") || "someone";
export const AGENT = "regular_agent";
export const arrivalMoves = (i, moved = null) => (i?.mid && !i.tid && !moved ? [AGENT] : []);
export const arrivalHand = (i, items, movedTo, onAgent) => ({ verb: AGENT,
  items: [i, ...items.filter((x) => x.key !== i.key)].filter((x) => arrivalMoves(x, movedTo[x.key]).length).map((x) => ({ key: x.key, title: `${whoName(x.who)}: ${x.title || ""}` })),
  start: async (o) => {
    const [lead, ...rest] = o.items.map((c) => items.find((x) => x.key === c.key)).filter(Boolean);
    const also = rest.length ? `\n\nTHE OTHER MESSAGES OF THIS LIST IT IS ABOUT (read each with read_message)\n${rest.map((x) => `m${x.mid} - ${whoName(x.who)}: ${x.title || ""}`).join("\n")}` : "";
    await onAgent?.(lead, { verb: o.verb, text: `${o.text}${also}`, files: o.files });
  } });
