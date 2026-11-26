// One skill open on the Reports page's Skills shelf (SkillShelf.jsx): the browse state's `open` is pb:<slug>, pb:new
export const PB_OPEN = "pb:";
export const pbOpen = (open) => (typeof open === "string" && open.startsWith(PB_OPEN) ? open.slice(PB_OPEN.length) : null);
// A NEW SKILL ASKED FOR SOMEWHERE ELSE - New's Skill tab, or the Assistant writing one into it (the owner, 2026-10-22: "this is not
// skill ui? ... no new skill ui either??"): the words wait here for the shelf's New skill, which may not be mounted yet.
// `start`: Set up with AI was already pressed on New, so the dialog starts it once instead of asking for the same press again
export const NEW_PB = "new-skill";
let asked = null;
export const askSkill = (text = "", start = false) => { asked = { text: String(text || ""), start: !!start }; };
export const takeSkillAsk = () => { const a = asked; asked = null; return a; };
