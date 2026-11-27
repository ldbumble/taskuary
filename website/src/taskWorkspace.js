// CONTINUE ON THE AGENT'S OWN BAR. A coding agent's Continue reopens its CLI session, which nothing else on the page does. A general
// agent's open card has its composer, and what you type there continues the same conversation - a second door (the owner,
// 2026-09-29) - EXCEPT when its run ended under it (`ended`, the task detail's runEnded: its CLI died part-way through a turn and the
// run failed, or it was cut off): then Continue picks the saved conversation back up (2026-10-21). ...and so does one the owner STOPPED
// (the owner, 2026-11-03: after a restart it offered only Run another agent): a stopped agent always offers Continue
export const RUN_ENDED = ["failed", "disconnected", "stopped"];
export const barContinues = ({ canContinue, isGeneral, ended } = {}) => !!canContinue && (!isGeneral || RUN_ENDED.includes(ended));
