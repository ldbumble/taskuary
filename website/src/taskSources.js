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
const INTENT = { task: "task", reply_only: "reply", fyi: "fyi" };
const WHO = { general: "an agent · general", coding: "an agent · coding" };
export const repoTag = (tags, name = "repo") => (String(tags || "").match(new RegExp(`(?:^|[\\s,])${name}:([^\\s,]+)`)) || [])[1] || "";
export function headerFacts({ verdict = null, route = null, task = {} } = {}) {
  const kind = task?.Kind || verdict?.kind || "task";
  // a route that CREATED the task is triage's decision even when its reason carries no head (rows from before the heads, fixtures)
  const said = String(verdict?.intent || routeIntent(route?.Reason) || (route?.Decision === "create" ? (kind === "reply" ? "reply_only" : "task") : "")).toLowerCase();
  const intent = INTENT[said] || "";
  const repo = kind === "coding" ? repoTag(task?.Tags) || repoTag(task?.Tags, "triage-repo") || verdict?.repository || "" : "";
  const profile = kind === "general" ? assignedAgent(task?.Assignee) || verdict?.profile || "" : "";
  const pri = task?.Priority || "normal";
  return {
    triaged: !!intent,
    pills: [
      intent && { key: "intent", label: "Intent", value: intent },
      { key: "who", label: "Who does it", value: WHO[kind] || "yours", tone: WHO[kind] ? "agent" : "" },
      profile && { key: "profile", label: "Profile", value: profile },
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
  if (kind === "coding") return `work for the coding agent${repo ? ` in ${repo}` : ""}`;
  if (kind === "general") return "work for the assistant";
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
