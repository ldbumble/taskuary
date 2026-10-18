// THE TASK SECTION'S FACTS (the redesign of section 1, 2026-10-16): what triage decided, as read-only pills in the header,
// and where the task came from, as conversations - pure, so node --test reads them without React or MUI.
import { assignedAgent } from "./agentIdentity.js";
import { routeIntent, routeWhy } from "./triageVerdict.js";

const CHANNEL_NAMES = { email: "Email", whatsapp: "WhatsApp", telegram: "Telegram", slack: "Slack", teams: "Teams", github: "GitHub",
  monday: "Monday", jira: "Jira", linear: "Linear", imessage: "iMessage", discord: "Discord", report: "Report", assistant: "Assistant",
  google_chat: "Google Chat", sms: "SMS", calendar: "Calendar" };
export const channelName = (ch) => CHANNEL_NAMES[ch] || (ch ? ch[0].toUpperCase() + ch.slice(1).replace(/_/g, " ") : "Message");
const CHATS = new Set(["whatsapp", "teams", "slack", "telegram", "imessage", "discord", "mattermost", "rocketchat", "matrix", "google_chat", "sms"]);
export const isChat = (ch) => CHATS.has(ch);

export const isMine = (m) => m?.Status === "context" || m?.Direction === "out" || !!m?.mine;
export const senderOf = (m) => (isMine(m) ? "You" : m?.FromName || m?.FromEmail || channelName(m?.Channel));
const oneLine = (s) => String(s || "").replace(/\s+/g, " ").trim();
// "RE: Fwd: the export" and "the export" are one email thread when the mail carries no thread id
const bareSubject = (s) => oneLine(s).replace(/^((re|fw|fwd|aw|sv)\s*:\s*)+/i, "").toLowerCase();

// ONE CONVERSATION, ONE GROUP: the thread id the channel gave it, else the chat (SourceName) or the subject. NEWEST FIRST (the
// owner, 2026-10-16: "yes newest first for messages"): the conversation that moved last leads, and inside one the latest message
// is on top and the one that started it at the bottom. `first` and `last` stay the opening and the latest message.
export function groupConversations(messages = [], { ms = (s) => Date.parse(s) || 0, clean = (s) => s } = {}) {
  const groups = new Map();
  for (const m of [...messages].sort((a, b) => ms(a.SentAt) - ms(b.SentAt))) {
    const key = m.ConversationId ? `c:${m.ConversationId}`
      : isChat(m.Channel) && m.SourceName ? `s:${m.Channel}:${m.SourceName}`
      : m.Subject ? `t:${m.Channel}:${bareSubject(m.Subject)}` : `m:${m.MessageId}`;
    if (!groups.has(key)) groups.set(key, { key, channel: m.Channel || "", msgs: [] });
    groups.get(key).msgs.push({ ...m, who: senderOf(m), excerpt: oneLine(clean(m.ReadText ?? m.BodyText)).slice(0, 240) });
  }
  return [...groups.values()].map((g) => {
    const first = g.msgs[0], last = g.msgs[g.msgs.length - 1], people = new Set(g.msgs.map((m) => m.who));
    const title = isChat(g.channel) ? first.SourceName || first.Subject || first.who : first.Subject || first.SourceName || first.who;
    return { ...g, msgs: [...g.msgs].reverse(), title: oneLine(title), count: g.msgs.length, people: people.size, first, last };
  }).sort((a, b) => ms(b.last.SentAt) - ms(a.last.SentAt));
}

// the names behind "· · · 21 more": who wrote them, most frequent first, the rest counted
export const namesOf = (msgs, max = 3) => {
  const n = new Map();
  msgs.forEach((m) => n.set(m.who, (n.get(m.who) || 0) + 1));
  const names = [...n.entries()].sort((a, b) => b[1] - a[1]).map(([w]) => w);
  return names.length > max ? `${names.slice(0, max).join(", ")} and ${names.length - max} more` : names.join(", ");
};
// A LONG CONVERSATION SHOWS ITS ENDS: the latest `keep` on top, how many are between and who wrote them, then the message that started it
export function previewRows(group, keep = 2, all = false) {
  const ms = group?.msgs || [];
  if (all || ms.length <= keep + 2) return ms.map((m) => ({ m }));
  const hid = ms.slice(keep, ms.length - 1);
  return [...ms.slice(0, keep).map((m) => ({ m })), { gap: hid.length, names: namesOf(hid) }, { m: ms[ms.length - 1] }];
}
// how many messages the previews leave out - none means there is nothing for "Show all" to add
export const hidden = (groups, keep = 2) => groups.reduce((n, g) => n + (g.count > keep + 2 ? g.count - keep - 1 : 0), 0);

// CLOSE OUT READS THE CONVERSATION IT ANSWERS CONDENSED: its latest `keep`, newest first - the draft answers the top line - and how
// many are under them and who wrote them. The whole of it is in Task (the owner, 2026-10-16: "in close out chats condensed version?")
export function latestRows(group, keep = 4) {
  const ms = group?.msgs || [];
  if (ms.length <= keep + 1) return ms.map((m) => ({ m }));
  const hid = ms.slice(keep);
  return [...ms.slice(0, keep).map((m) => ({ m })), { gap: hid.length, names: namesOf(hid) }];
}
// whether "Show all" changes anything: an email thread's hidden middle, or a chat's back-and-forth - a chat of three lines still reads
// as one in bubbles (the owner, 2026-10-16: "wasn't this supposed to be a chat back and forth if you hit show all?")
export const expands = (groups, keep = 2) => hidden(groups, keep) > 0 || groups.some((g) => isChat(g.channel) && g.count > 1);

export function cameFromLabel(groups) {
  const n = groups.reduce((s, g) => s + g.count, 0);
  if (!n) return "";
  return `Came from · ${n} message${n === 1 ? "" : "s"}${groups.length > 1 ? ` in ${groups.length} conversations` : ""}`;
}
export const groupMeta = (g) => [channelName(g.channel), `${g.count} message${g.count === 1 ? "" : "s"}`,
  g.people > 1 ? `${g.people} people` : ""].filter(Boolean).join(" · ");

// THE ASK IN ONE LINE: its first sentence, the whole text kept for the tooltip when that cut anything
export function askLine(text, max = 220) {
  const s = oneLine(text);
  if (!s) return { line: "", cut: false };
  const m = /^.+?[.!?](?=\s|$)/.exec(s);
  let line = m ? m[0] : s;
  if (line.length > max) line = `${line.slice(0, max).replace(/\s+\S*$/, "")}…`;
  return { line, cut: line !== s };
}

// WHAT TRIAGE DECIDED, as facts you read - never a control (the owner, 2026-10-16: "why are there dropdowns by the triage results?
// you can't change it"). The task row is the live answer for who, profile, repository and priority; the verdict names the intent.
// in plain words: "Who does it: an agent · general" was the app's own bookkeeping read out to a finance user (2026-10-17 audit)
const INTENT = { task: "task", reply_only: "reply", fyi: "fyi" };   // TaskPage.sortedLine reads these ids into its own words
const WHO = { general: "an agent", coding: "a coding agent" };
export const repoTag = (tags, name = "repo") => (String(tags || "").match(new RegExp(`(?:^|[\\s,])${name}:([^\\s,]+)`)) || [])[1] || "";
// A WORKFLOW RUN has no message behind it and nobody triaged it (workflows.run): what started it is on the task as a tag, and the
// workflow it belongs to rides on the detail (workflows.of_task) - the owner, 2026-10-16: "what does it show triggered it in the task card?"
const STARTED_BY = { schedule: "its schedule", manual: "you (Run now)", assistant: "the assistant", phone: "you, from your phone" };
// WHERE A TASK CAME FROM, in plain words: "from email · created 1m ago by triage" named the machinery (the walk's WORDS, 2026-10-17).
// The sorter that made it is "sorted", the owner is "you", anything else just made it.
const SORTERS = new Set(["triage", "router", "routing", "classifier"]), OWNER = new Set(["owner", "manual", "you", "user"]);
export function madeLine(task = {}, ago = "") {
  const by = String(task?.CreatedBy || "").trim().toLowerCase(), src = String(task?.Source || "").trim();
  const how = SORTERS.has(by) ? `sorted ${ago}` : OWNER.has(by) || !src || src === "manual" ? `made by you ${ago}` : `made ${ago}`;
  return [src && src !== "manual" ? `from ${src}` : "", how.trim()].filter(Boolean).join(" · ");
}
export const isWorkflowRun = (task) => task?.Source === "workflow";
export function startedBy(task = {}, wf = null) {
  const t = wf?.trigger || repoTag(task?.Tags, "workflow-trigger");
  const by = wf?.started_by || STARTED_BY[t] || "";
  return by && t === "schedule" && wf?.schedule ? `${by} (${wf.schedule})` : by;
}
// the run's own title is "<workflow> - 2026-10-16 08:00": with the workflow gone, that is still its name
export const workflowTitle = (task = {}, wf = null) => wf?.title || String(task?.Title || "").replace(/ - \d{4}-\d{2}-\d{2} \d{2}:\d{2}$/, "");
// CAME FROM, for a run: the workflow and what started it - where a message would be, since there is none
export function workflowOrigin(task = {}, wf = null) {
  if (!isWorkflowRun(task)) return null;
  const by = startedBy(task, wf);
  // ...and, when it ran as steps (flow.py), what each step did - the run's own record, not the agent's account of it
  return { title: workflowTitle(task, wf), by, line: by ? `Started by ${by}` : "A workflow run",
    link: wf?.source_id != null ? `#report=${wf.source_id}` : "", ...(Array.isArray(wf?.steps) && wf.steps.length ? { steps: wf.steps, repairs: wf.repairs || [], sourceId: wf.source_id, runId: wf.run_id } : {}) };
}
export function headerFacts({ verdict = null, route = null, task = {}, workflow = null } = {}) {
  const kind = task?.Kind || verdict?.kind || "task";
  const run = isWorkflowRun(task);
  // a route that CREATED the task is triage's decision even when its reason carries no head (rows from before the heads, fixtures)
  const said = run ? ""
    : String(verdict?.intent || routeIntent(route?.Reason) || (route?.Decision === "create" ? (kind === "reply" ? "reply_only" : "task") : "")).toLowerCase();
  const intent = INTENT[said] || "";
  const repo = kind === "coding" ? repoTag(task?.Tags) || repoTag(task?.Tags, "triage-repo") || verdict?.repository || "" : "";
  const profile = kind === "general" ? assignedAgent(task?.Assignee) || verdict?.profile || "" : "";
  const pri = task?.Priority || "normal";
  const by = run ? startedBy(task, workflow) : "";
  return {
    triaged: !!intent,
    workflow: run,
    pills: [
      run && { key: "workflow", label: "Workflow", value: workflowTitle(task, workflow) },
      by && { key: "trigger", label: "Started by", value: by },
      // ...and what it runs on: the general agents' brain, or the harder model and effort this workflow asked for (workflows.brain)
      run && workflow?.runs_on && { key: "runs_on", label: "Runs on", value: workflow.runs_on, tone: "agent" },
      intent && { key: "intent", label: "What it is", value: intent },
      { key: "who", label: "Who does it", value: WHO[kind] || "yours", tone: WHO[kind] ? "agent" : "" },
      profile && { key: "profile", label: "Agent", value: profile },
      repo && { key: "repo", label: "Repository", value: repo, mono: true },
      // a start that stopped on "which repository?" (funnel.HELD_REPO) says so where the repository would be; the pick is on the bar
      !repo && kind === "coding" && /(?:^|[\s,])held:repo(?:$|[\s,])/.test(String(task?.Tags || "")) && { key: "repo", label: "Repository", value: "none - not started", tone: "alert" },
      { key: "priority", label: "Priority", value: pri, tone: pri === "urgent" ? "alert" : "" },
    ].filter(Boolean),
  };
}

// THE QUIET LINE UNDER THE MESSAGES: when triage judged it, whose it made it, and why - the route record leads with who now
// ("work for the coding agent in org/app"); older rows said "task", so their head is worked out the way categories.route_head does
export function routeHead(reason, { intent = "", kind = "", repo = "" } = {}) {
  const m = /^triage:\s*([^·]*?)\s-\s/.exec(String(reason || ""));
  const said = m ? m[1].trim() : "";
  if (/^(yours to do|work for |needs a reply|nothing to do)/i.test(said)) return said;
  const i = intent || routeIntent(reason);
  if (i === "fyi") return "nothing to do";
  if (i === "reply_only") return "needs a reply";
  if (kind === "coding") return `work for a coding agent${repo ? ` in ${repo}` : ""}`;
  if (kind === "general") return "work for an agent";
  if (kind === "reply") return "needs a reply";
  return i || kind === "task" ? "yours to do" : said;
}
export function triageLine({ route = null, verdict = null, task = {}, messages = [], ms = (s) => Date.parse(s) || 0 } = {}) {
  const made = ms(task?.CreatedAt);
  // ...joined AFTER the task was made: ingest folds a sender's next message onto the task it continues
  const later = made ? messages.filter((m) => !isMine(m) && m.MessageId !== route?.MessageId && ms(m.CreatedAt || m.SentAt) > made).length : 0;
  if (!route) return { later, head: "", why: "", at: "" };
  const facts = headerFacts({ verdict, route, task });
  const head = routeHead(route.Reason, { intent: String(verdict?.intent || ""), kind: task?.Kind || "",
    repo: facts.pills.find((p) => p.key === "repo")?.value || "" });
  const why = oneLine(verdict?.why || routeWhy(route.Reason).split(" · ")[0]);
  return { later, head, why: /^triage:/i.test(why) ? "" : why, at: route.CreatedAt || "" };   // a head with no reason after it says no why
}
