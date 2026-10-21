// What the agent step says when nothing is live on it (funnel.agent_story): why it never started, or what it did
// before it went. The step showed a Start button and nothing else (the owner, 2026-10-11: "it should say what the
// agent did so far and was interrupted or it never started").

import { agentWord } from "./kinds.js";
import { WORD } from "./lanes.js";

// the chip beside "Agent work" - only the two that wait on the owner wear oxblood. `finished`: its run said it was done - the chip read
// "not started" over "finished its work" (G7, 2026-10-20); the word is the one the list and the Board give it (lanes.json agentdone)
// `failed`: its run said it failed - said as a failure, never "not started" or "stopped" over the reason (owner-approved, 2026-10-21)
export const STORY_CHIP = { held: "waiting on you", interrupted: "interrupted", left: "stopped", idle: "not started", news: "earlier session",
  finished: WORD.agentdone, failed: "failed" };
export const storyAlarm = (kind) => kind === "held" || kind === "interrupted" || kind === "failed";

// a live session tells its own story, and a queued start already has its card (QueuedStart) with Start now and Cancel
export const storyShown = (story, { alive, liveRun, queued, closed } = {}) =>
  !!story?.line && !alive && !liveRun && !closed && !(queued && story.kind === "queued");

// "Start the coding agent" for a step that never ran: "Start an agent" read as if nobody had been chosen, and "Start coder"
// named a profile as if it were a worker (the owner, 2026-10-16) - the button says what the agent IS, by the task's kind
export { agentWord };
export const startLabel = (story, kind, ran) => !ran && story && ["held", "idle"].includes(story.kind) ? `Start ${agentWord(kind)}` : null;

export const hhmm = (ts) => String(ts || "").slice(11, 16);

// WHERE THE STORY GOES, so the step says each thing once (the owner, 2026-10-12, on a stopped session that stacked the story,
// its last message in a bubble and a "Session closed" card repeating it: "follow the format of all agents. main summary,
// then details behind more"). With a record it is the record's first line - folded, over the record's summary; open, over the
// whole record with its timeline behind More. With none it is the account itself - folded, its sentence.
export const storyPlace = (story, { open, hasRecord } = {}) =>
  !story?.line ? null : hasRecord ? (open ? "record" : "summary") : open ? "story" : "line";
