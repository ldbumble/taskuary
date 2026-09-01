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
// A session you opened to sit in is the opposite: you alt-tab, the agent goes quiet, the judge
// reads the last screen as finished, and the task closes out from under you with a reply drafted
// to nobody. Tagged, only an explicit `taskuary --done` ends it (selfclose.STAY_TAG).
export const STAY_TAG = "stay:open";
export const wantsAsk = (task) => new RegExp(`(^|[\\s,])${ASK_TAG}([\\s,]|$)`).test(String(task?.Tags || ""));
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
