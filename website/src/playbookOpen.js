// One playbook open on the Reports page's Playbooks shelf (PlaybookShelf.jsx): the browse state's `open` is pb:<slug>, pb:new
export const PB_OPEN = "pb:";
export const pbOpen = (open) => (typeof open === "string" && open.startsWith(PB_OPEN) ? open.slice(PB_OPEN.length) : null);
