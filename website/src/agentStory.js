// What the agent step says when nothing is live on it (funnel.agent_story): why it never started, or what it did
// before it went. The step showed a Start button and nothing else (the owner, 2026-10-11: "it should say what the
// agent did so far and was interrupted or it never started").

// a live session tells its own story, and a queued start already has its card (QueuedStart) with Start now and Cancel
export const storyShown = (story, { alive, liveRun, queued, closed } = {}) =>
  !!story?.line && !alive && !liveRun && !closed && !(queued && story.kind === "queued");

// WHERE THE STORY GOES, so the step says each thing once (the owner, 2026-10-12, on a stopped session that stacked the story,
// its last message in a bubble and a "Session closed" card repeating it: "follow the format of all agents. main summary,
// then details behind more"). With a record it is the record's first line - folded, over the record's summary; open, over the
// whole record with its timeline behind More. With none it is the account itself - folded, its sentence.
export const storyPlace = (story, { open, hasRecord } = {}) =>
  !story?.line ? null : hasRecord ? (open ? "record" : "summary") : open ? "story" : "line";
