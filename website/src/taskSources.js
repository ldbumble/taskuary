// THE TASK SECTION'S FACTS (the redesign of section 1, 2026-10-16): what triage decided, as read-only pills in the header,
// and where the task came from, as conversations - pure, so node --test reads them without React or MUI.
import { assignedAgent } from "./agentIdentity.js";
import { routeIntent, routeWhy } from "./triageVerdict.js";
import { plural } from "./timeWords.js";
import { level } from "./priority.js";

const CHANNEL_NAMES = { email: "Email", whatsapp: "WhatsApp", telegram: "Telegram", slack: "Slack", teams: "Teams", github: "GitHub",
  monday: "Monday", jira: "Jira", linear: "Linear", imessage: "iMessage", discord: "Discord", report: "Report", assistant: "Assistant",
  google_chat: "Google Chat", sms: "SMS", calendar: "Calendar" };
export const channelName = (ch) => CHANNEL_NAMES[ch] || (ch ? ch[0].toUpperCase() + ch.slice(1).replace(/_/g, " ") : "Message");
const CHATS = new Set(["whatsapp", "teams", "slack", "telegram", "imessage", "discord", "mattermost", "rocketchat", "matrix", "google_chat", "sms"]);
export const isChat = (ch) => CHATS.has(ch);

export const isMine = (m) => m?.Status === "context" || m?.Direction === "out" || !!m?.mine;
export const senderOf = (m) => (isMine(m) ? "You" : m?.FromName || m?.FromEmail || channelName(m?.Channel));
const oneLine = (s) => String(s || "").replace(/\s+/g, " ").trim();
// ...cut on a word, never mid-word ("qualifying donor" stood as the end of a sentence, 2026-10-28)
const clip = (s, n) => s.length <= n ? s : `${s.slice(0, n).replace(/\s+\S*$/, "")}…`;
// AN ADVISOR IDEA'S OWN LINE on a task is Taskuary's words, not something that came in: Came from says it once (detail.raised) and shows
// the mail it was about - it drew as the message, "Advisor · Advisor" over the Advisor's text (2026-10-28)
export const isIdeaLine = (m) => m?.Channel === "assistant" && /^idea:/.test(String(m?.ExternalId || ""));
// WHO · WHERE · WHEN, each said once: a line whose sender and source are one name ("Advisor · Advisor") says it once
export const byLine = (...parts) => parts.filter((p, i) => p && parts.findIndex((q) => String(q).toLowerCase() === String(p).toLowerCase()) === i).join(" · ");
// ...and WHERE is the sender's address on mail: a mail's SourceName is the owner's own mailbox it arrived in, and "Omar Keller ·
// alex@northwind.example" read as Omar's address (the email walk, 2026-10-29). A chat or a report keeps its own name.
export const cameFromWhere = (m) => String(m?.SourceName || "").includes("@") ? (m?.FromEmail || channelName(m?.Channel)) : (m?.SourceName || channelName(m?.Channel));
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
    groups.get(key).msgs.push({ ...m, who: senderOf(m), excerpt: clip(oneLine(clean(m.ReadText ?? m.BodyText)), 240) });
  }
  return [...groups.values()].map((g) => {
    const first = g.msgs[0], last = g.msgs[g.msgs.length - 1], people = new Set(g.msgs.map((m) => m.who));
    // a Teams line's SourceName is the owner's own account it was read through (channels.ingest_teams_chats), not the chat: the owner's
    // address headed a colleague's conversation (2026-10-26) - its Subject is the chat's topic, or "Teams chat with <them>"
    const room = g.channel === "teams" ? "" : first.SourceName;
    const title = isChat(g.channel) ? room || first.Subject || first.who : first.Subject || first.SourceName || first.who;
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
// FROM LISTS IT NEWEST ON TOP (the redesign, owner-approved 2026-10-21): the latest `keep` messages - a burst of chat lines, a thread with
// your replies in it - and the older ones folded behind "Show N older" at the foot, never the opening message pinned under a gap.
// `all` draws every one, still newest first. Group messages are newest first already (groupConversations).
// WHICH MAIL ASKED FOR WHICH TO-DO (the owner, 2026-10-22: "when tasks come from multiple emails should it not say which email it
// comes from ... especially in goals"): a box's `src` is the message that brought it (store.merge_task_checklist). Said only where
// there is more than one message to tell apart - one mail's list needs no "from" on every row - and never for a box with no source
export function todoSources(items = [], groups = []) {
  const msgs = (groups || []).flatMap((g) => g?.msgs || []);
  if (msgs.length < 2) return new Map();
  const by = new Map(msgs.map((m) => [m.MessageId, m]));
  return new Map((items || []).filter((i) => i?.src != null && by.has(i.src)).map((i) => [i.id, by.get(i.src)]));
}
export function fromRows(group, keep = 3, all = false) {
  const ms = group?.msgs || [];
  if (all || ms.length <= keep + 1) return ms.map((m) => ({ m }));
  const hid = ms.slice(keep);
  return [...ms.slice(0, keep).map((m) => ({ m })), { older: hid.length, names: namesOf(hid) }];
}
// EVERY FILE BELONGS TO ITS MESSAGE (the owner, 2026-10-20: a voice note drawn loose under the Came from card, outside the thread):
// the task detail's attachment rows by MessageId, so each condensed row knows what rode in with it and draws it under itself
// A SIGNATURE'S PICTURE IS NOT A FILE OF THE MESSAGE (the owner, 2026-10-28: "I don't need these images unless they relate to the actual
// message"): an inline image the same name and size on two or more of the task's messages is the sender's signature logo, so it is
// left out wherever the conversation lists files
const sigKey = (a) => `${a?.Name || a?.name || ""}|${a?.Size ?? a?.size ?? ""}`;
export const signatureImages = (atts = []) => {
  const on = new Map();
  for (const a of atts || []) if ((a?.Inline ?? a?.inline) && a?.MessageId != null) on.set(sigKey(a), new Set([...(on.get(sigKey(a)) || []), a.MessageId]));
  return new Set([...on].filter(([, mids]) => mids.size > 1).map(([k]) => k));
};
export const filesByMessage = (atts = []) => {
  const by = new Map(), sig = signatureImages(atts);
  for (const a of atts || []) if (a?.MessageId != null && !sig.has(sigKey(a))) by.set(a.MessageId, [...(by.get(a.MessageId) || []), a]);
  return by;
};
const AUDIO = /\.(ogg|opus|mp3|m4a|aac|wav|webm|flac|amr)$/i;
export const isAudioFile = (a) => String(a?.ContentType || a?.content_type || "").startsWith("audio/") || !!a?.is_audio || AUDIO.test(a?.Name || a?.name || "");
// a condensed row's words: a voice note's transcript without its "(🎤 voice note ...)" mark, and for a message that is only a file
// what the file is - never "(no text - see the attachment)" or the bridge's hash of a file name
const VOICE_MARK = /\s*\(🎤 voice note[\s\S]*\)\s*$/i, NO_TEXT = /^\(no text - see the attachment\)$/;
export function rowText(m = {}, files = []) {
  const words = String(m.excerpt || "").replace(VOICE_MARK, "").trim();
  if (words && !NO_TEXT.test(words)) return words;
  if (m.Subject) return m.Subject;
  if (files.some(isAudioFile) || VOICE_MARK.test(m.excerpt || "")) return "Voice note";
  return files.length ? plural(files.length, "attachment") : "(no text)";
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
// ...and From's: an older message folded away (fromRows), or a chat's back-and-forth
export const fromExpands = (groups, keep = 3) => groups.some((g) => g.count > keep + 1 || (isChat(g.channel) && g.count > 1));

export function cameFromLabel(groups) {
  const n = groups.reduce((s, g) => s + g.count, 0);
  if (!n) return "";
  return `Came from · ${plural(n, "message")}${groups.length > 1 ? ` in ${groups.length} conversations` : ""}`;
}
export const groupMeta = (g) => [channelName(g.channel), plural(g.count, "message"),
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
  return { title: workflowTitle(task, wf), by, line: by ? `Started by ${by}` : "A routine run",
    link: wf?.source_id != null ? `#report=${wf.source_id}` : "", ...(wf?.by_code ? { byCode: true } : {}), ...(Array.isArray(wf?.steps) && wf.steps.length ? { steps: wf.steps, repairs: wf.repairs || [], sourceId: wf.source_id, runId: wf.run_id } : {}) };
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
  const pri = level(task?.Priority);
  const by = run ? startedBy(task, workflow) : "";
  return {
    triaged: !!intent,
    workflow: run,
    pills: [
      run && { key: "workflow", label: "Routine", value: workflowTitle(task, workflow) },
      by && { key: "trigger", label: "Started by", value: by },
      // ...and what it runs on: the general agents' brain, or the harder model and effort this workflow asked for (workflows.brain)
      run && workflow?.runs_on && { key: "runs_on", label: "Runs on", value: workflow.runs_on, tone: "agent" },
      intent && { key: "intent", label: "What it is", value: intent },
      // ...a run of steps with no agent step is done by those steps (workflows.of_task by_code), not by the agent its kind names
      run && workflow?.by_code ? { key: "who", label: "Who does it", value: "its steps", tone: "agent" }
        : { key: "who", label: "Who does it", value: WHO[kind] || "yours", tone: WHO[kind] ? "agent" : "" },
      profile && { key: "profile", label: "Agent", value: profile },
      repo && { key: "repo", label: "Repository", value: repo, mono: true },
      // a start that stopped on "which repository?" (funnel.HELD_REPO) says so where the repository would be; the pick is on the bar
      !repo && kind === "coding" && /(?:^|[\s,])held:repo(?:$|[\s,])/.test(String(task?.Tags || "")) && { key: "repo", label: "Repository", value: "none - not started", tone: "alert" },
      { key: "priority", label: "Priority", value: pri, tone: pri === "urgent" ? "alert" : pri === "important" ? "info" : "" },
    ].filter(Boolean),
  };
}

// WHAT TRIAGE MADE OF IT IN ONE PLAIN LINE (the audit, 2026-10-17: "Triage decided · Intent task · Who does it an agent · general" was the
// sorter's own vocabulary): "Sorted as: a task for an assistant · normal priority". A held repository is a warning, never "in none".
const factOf = (facts, k) => facts.pills.find((p) => p.key === k && p.tone !== "alert")?.value || "";
const whatOf = (facts, kind) => { const intent = factOf(facts, "intent");
  return intent === "reply" || kind === "reply" ? "a reply to send" : intent === "fyi" ? "for your information"
    : `a task ${{ general: "for an assistant", coding: "for your coding tool" }[kind] || "for you"}`; };
export const sortedLine = (facts, kind) => {
  const what = whatOf(facts, kind), repo = factOf(facts, "repo");
  const head = facts.triaged ? `Sorted as: ${what}` : what.charAt(0).toUpperCase() + what.slice(1);
  return [head, repo && `in ${repo}`, `${facts.pills.find((p) => p.key === "priority")?.value || "regular"} priority`].filter(Boolean).join(" · ");
};
// ...AT THE FOOT OF FROM (the redesign, owner-approved 2026-10-21): "Sorted as: <what> · <priority> · <why>" - the why is the one
// triage recorded (triageLine), never written here
export const triageSays = (facts, kind, why = "") => [sortedLine(facts, kind), oneLine(why)].filter(Boolean).join(" · ");

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
