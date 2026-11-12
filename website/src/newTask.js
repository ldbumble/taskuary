// WHO works a new task is decided by one box: the repository picker. A repository means a CLI
// agent in that checkout - a terminal, on the board. "General - no repository, just a question
// to answer" means the assistant's own chat on the Tasks tab (Kind general -> GeneralWorkspace).
// Filing a general question as a coding task is what opened it in a terminal instead, so the
// rule lives here, on its own, where it can be tested.
export const NO_REPO = "none";

// The marker that says "this task was created with a question to ask". It rides on the task
// itself because the first two attempts passed it between components across a navigation and
// lost the race with their own re-renders - once to a stale `detail`, once to the effect that
// cleared it. Server state does not race: the chat reads the tag when it opens, asks, and
// strips it, so a reload never re-asks and a chat opened later still gets the question.
export const ASK_TAG = "ask:assistant";

// ...and the other thing a task can need: a browser of its own. Marked here, the session
// STARTS one (bound to it, restored from your saved cookies, closed with it) instead of
// waiting for the agent to think of running agent-browser - and the agent is told it is there.
export const BROWSER_TAG = "needs:browser";

// ...and the one that says WHO this session is for. A task the router made has somebody waiting
// on an answer, so finishing it should close it and draft the reply - that is the funnel working.
// A session you opened to sit in is the opposite: the agent finishing a step is not you finishing
// the task. Tagged, the agent's `taskuary --done` is refused and you complete it (selfclose.STAY_TAG,
// taskLifecycle.ownerControlsCompletion).
export const STAY_TAG = "stay:open";
export const wantsAsk = (task) => new RegExp(`(^|[\\s,])${ASK_TAG}([\\s,]|$)`).test(String(task?.Tags || ""));
// ...and the owner's desktop apps (agentdesktop.py, 2026-10-31): with Agent Desktop on, only a task marked "needs desktop" gets it
export const DESKTOP_TAG = "needs:desktop";
export const DESKTOP_HOW = 'To use it, turn the Agent Desktop card on and mark a task "needs desktop".';
export const wantsDesktop = (task) => new RegExp(`(^|[\\s,])${DESKTOP_TAG}([\\s,]|$)`).test(String(task?.Tags || ""));
export const withDesktop = (tags, on) => [...String(tags || "").split(/[\s,]+/).filter((t) => t && t !== DESKTOP_TAG), ...(on ? [DESKTOP_TAG] : [])].join(",") || null;
export const wantsBrowser = (task) => new RegExp(`(^|[\\s,])${BROWSER_TAG}([\\s,]|$)`).test(String(task?.Tags || ""));
export const withoutAsk = (tags) => String(tags || "").split(/[\s,]+/).filter((t) => t && t !== ASK_TAG).join(",");

// the picker's value as the API wants it: a repository, or nothing at all
export const repoOf = (pick) => (pick && pick !== NO_REPO ? pick : null);

// how: "live" (an agent starts now), "file" (nobody starts), or "terminal" - which is "live"
// for a question you would rather work in a CLI than in the chat. Asked for explicitly, because
// a General task landing in a terminal by ACCIDENT is the bug this module exists to stop.
export const planTask = (pick, how, browser = false, stayOpen = false) => {
  const repo = repoOf(pick);
  const chat = !repo && how !== "terminal";
  const ask = chat && how === "live";              // "Ask the assistant", not "just file it"
  const tags = [repo ? `repo:${repo}` : (ask ? ASK_TAG : ""), browser ? BROWSER_TAG : "",
    stayOpen ? STAY_TAG : ""].filter(Boolean);
  return { repo, kind: chat ? "general" : "coding", chat, ask, browser, stayOpen: !!stayOpen,
    tags: tags.join(",") || null, start: how === "live" || how === "terminal" };
};

// WORDS TO GO: a job typed into the chat's own box (PromptBox - a general agent's, New's one box) is ready on its words; any other card on its
// plain field's (AboutField onReady). Read off the field alone, the Assistant's general job never pressed its own Send to agent
export const hasWords = ({ agentBox, words, field }) => (agentBox ? !!String(words || "").trim() : !!field);

// THE KINDS THAT REPEAT, built on their own shelf (Reports): a report, a dashboard, a routine. One the Assistant wrote up (`line`, concierge._new)
// goes STRAIGHT into its builder with the setup asked (owner-approved, 2026-11-12): the middle card's Set up with AI asked it all again
export const REPEATS = ["report", "dashboard", "workflow"];
export const goesStraight = (kind, line) => REPEATS.includes(kind) && line != null && line !== "";

// THE ASSISTANT'S PRESS IS MADE ONCE PER LINE, not once per card drawn (NewSheet `start`): the card is drawn again - put down and brought
// back, re-keyed - and a fresh card would press Send to agent again on a job already started (2026-11-02). `line` is the Assistant's line
// that wrote the job (concierge._new); a card with none keeps only its own once.
const pressedLines = new Set();
export const firstPressOf = (line) => {
  if (line == null || line === "") return true;
  if (pressedLines.has(String(line))) return false;
  pressedLines.add(String(line)); return true;
};
