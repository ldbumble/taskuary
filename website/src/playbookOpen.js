// One playbook open on the Reports page's Playbooks shelf (PlaybookShelf.jsx): the browse state's `open` is pb:<slug>, pb:new
export const PB_OPEN = "pb:";
export const pbOpen = (open) => (typeof open === "string" && open.startsWith(PB_OPEN) ? open.slice(PB_OPEN.length) : null);
// A NEW PLAYBOOK ASKED FOR SOMEWHERE ELSE - New's Playbook tab, or the Assistant writing one into it (the owner, 2026-10-22: "this is not
// playbook ui? ... no new playbook ui either??"): the words wait here for the shelf's New playbook, which may not be mounted yet.
// `start`: Set up with AI was already pressed on New, so the dialog starts it once instead of asking for the same press again
export const NEW_PB = "new-playbook";
let asked = null;
export const askPlaybook = (text = "", start = false) => { asked = { text: String(text || ""), start: !!start }; };
export const takePlaybookAsk = () => { const a = asked; asked = null; return a; };
