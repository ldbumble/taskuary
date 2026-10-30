// The static demo has no concierge process behind it. These are deliberately scripted,
// invented conversations and Timeline posts: enough real-shaped data to demonstrate the
// product without implying that an AI, mailbox, or agent is running in the visitor's browser.
import { hint, label } from "./buttons.js";
import { onYou, WORD } from "./lanes.js";

export const DEMO_ASSISTANT_TIMELINE = [
  {
    MessageId: 901, Channel: "assistant", SourceName: "Taskuary", Subject: "Before the 11:30 operations review",
    FromName: "Taskuary", FromEmail: null, SentAt: "2026-09-03 10:18:00", ConversationId: "assistant:morning-ops",
    Preview: "The East Wing Wi-Fi issue is the only open operational item. Marcus is already on it; ask for an ETA before the review.",
    MsgStatus: "feed", SourceLink: null, TaskId: null, Direction: "in", Brief: null,
    Title: null, TaskStatus: null, Priority: null, TaskKind: null, TaskTags: null,
    NeedsYou: 0, ChainSize: 1, Decision: "feed", RouteReason: "the assistant's post: a morning check", ReviewId: null,
    ReviewStatus: null, ReviewKind: null, HasDraft: null, Attachments: 0, AnsweredAt: null, TheirTurn: 0,
    Category: "assistant", CanSend: false,
    BodyText: "## Before the 11:30 operations review\n\nThe East Wing Wi-Fi issue is the only open operational item. Marcus is already on it; ask for an ETA before the review.\n\n**Why I raised it:** the outage arrived this morning and the review starts in just over an hour."
  },
  {
    MessageId: 902, Channel: "assistant", SourceName: "Taskuary", Subject: "Two replies can close loops before lunch",
    FromName: "Taskuary", FromEmail: null, SentAt: "2026-09-03 08:46:00", ConversationId: "assistant:reply-loops",
    Preview: "Ruth needs the AP cutover date and Sam needs the Q3 file. Both answers are short; one draft is ready and one still needs a sentence.",
    MsgStatus: "feed", SourceLink: null, TaskId: null, Direction: "in", Brief: null,
    Title: null, TaskStatus: null, Priority: null, TaskKind: null, TaskTags: null, NeedsYou: 0, ChainSize: 1,
    Decision: "feed", RouteReason: "the assistant's post: a follow-up check", ReviewId: null, ReviewStatus: null, ReviewKind: null,
    HasDraft: null, Attachments: 0, AnsweredAt: null, TheirTurn: 0, Category: "assistant", CanSend: false,
    BodyText: "## Two replies can close loops before lunch\n\nRuth needs the AP cutover date and Sam needs the Q3 file. Both answers are short; one draft is ready and one still needs a sentence.\n\n**My take:** clear Ruth first because her answer gates Thursday's cutover."
  },
  {
    MessageId: 903, Channel: "assistant", SourceName: "Taskuary", Subject: "The vendor renewal thread has gone quiet",
    FromName: "Taskuary", FromEmail: null, SentAt: "2026-09-02 16:15:00", ConversationId: "assistant:vendor-renewal",
    Preview: "No answer since last Thursday on the copier renewal. I would leave it until Friday, then send one concise follow-up.",
    MsgStatus: "feed", SourceLink: null, TaskId: null, Direction: "in", Brief: null,
    Title: null, TaskStatus: null, Priority: null, TaskKind: null, TaskTags: null, NeedsYou: 0, ChainSize: 1,
    Decision: "feed", RouteReason: "the assistant's post: a quiet-thread check", ReviewId: null, ReviewStatus: null, ReviewKind: null,
    HasDraft: null, Attachments: 0, AnsweredAt: null, TheirTurn: 0, Category: "assistant", CanSend: false,
    BodyText: "## The vendor renewal thread has gone quiet\n\nNo answer since last Thursday on the copier renewal. I would leave it until Friday, then send one concise follow-up.\n\n**Why I raised it:** the quote expires next week, but another message today would only add noise."
  },
];

// Every id below is BOUND to the recording by what it is (bindIds): the numbers were written against one
// recording, and the next one moved them - the cutover card opened the overnight-import draft, and the
// "onboarding" row pointed at a task that had become an invoice (2026-09-23).
const reviewCard = {
  bind: { review: "AP cutover - Thursday?" }, kind: "review", lane: "approve", title: "AP cutover - Thursday?", who: "Ruth Bennett",
  when: "2026-09-03 03:25:19", why: "a reply is drafted and waiting for your yes", channel: "email",
  preview: "Are we still moving AP over on Thursday? I need to tell the team.",
};

// THE DEMO OPENS ON ITS TOUR (taskuary/demo.py TOUR): the owner's own to-do, the rail's first row as it is the server demo's, and
// what /api/demo's `opens` names, so the canvas opens on it here too
export const DEMO_TOUR = "Start here - what Taskuary can do";
const pileItems = [
  {
    bind: { task: DEMO_TOUR, key: "task" }, kind: "todo", lane: "yours", title: DEMO_TOUR, who: "Taskuary", when: "2026-09-02 23:58:00",
    why: "the tour of the demo: every step is something to try here", channel: "own",
  },
  // the two rows the tour sends a visitor to that the morning below does not already hold
  {
    bind: { task: "Month-end close is short by 4,180", key: "task" }, kind: "todo", lane: "yours", title: "Month-end close is short by 4,180",
    who: "Marcus Reed", when: "2026-09-03 01:10:00", why: "a concrete ask, addressed to you, with a date on it", channel: "email",
  },
  {
    bind: { task: "northwind/importers#214 - census sync fails when a site has no manager", key: "agent" },
    kind: "agent", lane: "blocked", title: "northwind/importers#214 - census sync fails when a site has no manager",
    who: "Marcus Reed", when: "2026-09-03 09:35:19", why: "the agent needs one choice from you before it changes anything",
    agent: "claude", working: "claude", asking: true,
    // the answers it named, and the request they bind to: a raised hand is answered by picking one
    request_id: "q7", request_kind: "input_needed",
    choices: ["Skip only that site and log it", "Fail the whole sync", "Ask me each time"],
    channel: "github", preview: "Should a missing manager skip only that site, or fail the entire sync?",
    tail: ["I reproduced the null manager case.", "Should a missing manager skip only that site, or fail the entire sync?"],
  },
  { ...reviewCard, surfaced: true, surfaced_at: "2026-09-03 10:20:00" },
  {
    bind: { review: "Invoice 88213 - past due" }, kind: "review", lane: "approve", title: "Invoice 88213 - past due", who: "Tom Alvarez",
    when: "2026-09-03 02:30:00", why: "a reply is drafted for you to send", channel: "email",
  },
  {
    bind: { task: "Year-end audit - the first document requests", key: "msg" }, kind: "asked", lane: "asked",
    title: "Year-end audit - they want it by the 15th", who: "Priya Shah", when: "2026-09-03 08:21:19",
    why: "a date was added to the audit requests", channel: "email", preview: "And they would like all of it by the 15th.",
  },
  {
    key: "idea:renewal", kind: "idea", lane: "forgotten", title: "The copier renewal thread has gone quiet",
    who: "Tom Alvarez", when: "2026-09-02 16:15:00", why: "no reply since Thursday; the quote expires next week",
    idea_kind: "cold", channel: "assistant", action: { type: "followup", mid: 903 }, mid: 903,   // its own post (DEMO_ASSISTANT_TIMELINE) - 6 was a thank-you
  },
  {
    bind: { report: "Helpdesk tickets by day, last 14" }, kind: "report", lane: "report", title: "Helpdesk tickets by day, last 14",
    who: "Helpdesk report", when: "2026-09-03 05:53:19", why: "the scheduled report landed normally",
    channel: "report", bad: false,
  },
  // ...and the dashboard every install comes with, refreshed on its morning schedule (store.SEEDED_REPORTS)
  {
    bind: { report: "Taskuary at a glance" }, kind: "report", dashboard: true, lane: "report", title: "Taskuary at a glance",
    who: "Taskuary at a glance", when: "2026-09-03 07:00:12", why: "the built-in dashboard refreshed on its schedule",
    channel: "report", bad: false,
  },
  {
    bind: { msg: "Vendor portal maintenance window, Sunday 02:00-04:00" }, kind: "fyi", lane: "fyi", title: "Vendor portal maintenance Sunday, 02:00-04:00",
    who: "Platform Updates", when: "2026-09-03 08:58:19", why: "an automated notice; nothing to do",
    channel: "email", preview: "The vendor portal will be unavailable during the maintenance window.",
  },
  {
    bind: { task: "New starter on Monday - laptop + accounts", key: "agent" }, kind: "agent", lane: "working", title: "New starter on Monday - laptop + accounts",
    who: "Priya Shah", when: "2026-09-03 00:20:19", why: "a regular agent has it; nothing for you until it stops",
    agent: "Taskuary", working: "Taskuary", asking: false, channel: "email",
  },
];

const currentMessages = [
  {
    id: "demo-current-1", role: "assistant", at: "2026-09-03 10:14:00",
    // "{n}" is the scripted rail's own count of what waits on you (createDemoAssistantState) - a written "Three" drifted from the rail (B23)
    text: "Morning. I filed the maintenance notice and the newsletter. {n} still deserve a look; I put the cutover reply first.",
  },
  {
    id: "demo-current-2", role: "user", at: "2026-09-03 10:16:00",
    text: "What actually needs me before the operations review?",
  },
  {
    id: "demo-current-3", role: "assistant", at: "2026-09-03 10:16:10",
    text: "Ruth needs the Thursday cutover confirmed, and the agent on the census sync needs one choice from you. The audit requests can wait until those are clear.",
  },
  {
    id: "demo-current-4", role: "user", at: "2026-09-03 10:19:00",
    text: "Start with Ruth. Is the draft ready?",
  },
  {
    id: "demo-current-5", role: "assistant", at: "2026-09-03 10:19:10",
    text: "Yes. It confirms Thursday and says the export will be reconciled Wednesday night. Read the invented draft below; in this demo, Send never sends anything.",
    card: reviewCard,
    // the words under it, as a live turn carries them - without them the demo opened on a card with no Next
    chips: [{ verb: "next", label: label("next"), hint: hint("next") }],
  },
];

export const DEMO_ASSISTANT_CHATS = [
  { taskId: 8900, title: "What needs me before the ops review?", at: "2026-09-03 10:19:10", started: "2026-09-03 10:14:00", turns: 5, seen: 1, mail: 1, minutes: 5, open: true },
  { taskId: 8899, title: "Clear the overnight inbox", at: "2026-09-03 08:12:00", started: "2026-09-03 08:03:00", turns: 8, seen: 5, mail: 4, minutes: 9, open: false },
  { taskId: 8898, title: "What changed in month-end?", at: "2026-09-02 16:42:00", started: "2026-09-02 16:38:00", turns: 4, seen: 2, mail: 1, minutes: 4, open: false },
  { taskId: 8897, title: "Prep for the vendor review", at: "2026-09-01 14:27:00", started: "2026-09-01 14:19:00", turns: 6, seen: 3, mail: 2, minutes: 8, open: false },
];

export const DEMO_ASSISTANT_TRANSCRIPTS = {
  8900: currentMessages,
  8899: [
    { id: "demo-8899-1", role: "user", at: "2026-09-03 08:03:00", text: "Walk me through what landed overnight." },
    { id: "demo-8899-2", role: "assistant", at: "2026-09-03 08:03:10", text: "First: Priya's new-starter request is with an agent - it is writing up the laptop and access requests.", card: { bind: { task: "New starter on Monday - laptop + accounts", key: "agent" }, kind: "agent", lane: "working", title: "New starter on Monday - laptop + accounts", agent: "Taskuary", channel: "email" } },
    { id: "demo-8899-3", role: "user", at: "2026-09-03 08:05:00", text: "Good. What else?" },
    { id: "demo-8899-4", role: "assistant", at: "2026-09-03 08:05:10", text: "Ruth asked whether Thursday still holds for AP cutover. A short reply is drafted and waiting for review.", card: reviewCard },
    { id: "demo-8899-5", role: "user", at: "2026-09-03 08:07:00", text: "Leave that for the close check. Anything noisy?" },
    { id: "demo-8899-6", role: "assistant", at: "2026-09-03 08:07:10", text: "Two FYIs: a maintenance window and a newsletter. Neither started work, and both were filed." },
    { id: "demo-8899-7", role: "user", at: "2026-09-03 08:11:00", text: "That's right. Done." },
    { id: "demo-8899-8", role: "assistant", at: "2026-09-03 08:12:00", text: "Overnight is clear. The cutover reply remains on the task for later." },
  ],
  8898: [
    { id: "demo-8898-1", role: "user", at: "2026-09-02 16:38:00", text: "What changed in month-end since lunch?" },
    { id: "demo-8898-2", role: "assistant", at: "2026-09-02 16:38:10", text: "The reconciliation traced the 4,180 difference to four inter-company rows omitted by the export. The fix is tested; no ledger entries were changed." },
    { id: "demo-8898-3", role: "user", at: "2026-09-02 16:41:00", text: "Keep the task open until finance checks the file." },
    { id: "demo-8898-4", role: "assistant", at: "2026-09-02 16:42:00", text: "Kept open. Finance's check is the remaining step on the month-end task.", card: { bind: { task: "Month-end close is short by 4,180", key: "task" }, kind: "task", lane: "asked", title: "Month-end close is short by 4,180", why: "waiting for finance to check the corrected export" } },
  ],
  8897: [
    { id: "demo-8897-1", role: "user", at: "2026-09-01 14:19:00", text: "Get me ready for the vendor review." },
    { id: "demo-8897-2", role: "assistant", at: "2026-09-01 14:19:10", text: "Three threads matter: the copier renewal, AP ageing, and Sunday's portal maintenance. The renewal is the only one with a decision." },
    { id: "demo-8897-3", role: "user", at: "2026-09-01 14:22:00", text: "What would you push on?" },
    { id: "demo-8897-4", role: "assistant", at: "2026-09-01 14:22:10", text: "Push on price protection beyond October. Leave implementation dates alone until the AP cutover is confirmed." },
    { id: "demo-8897-5", role: "user", at: "2026-09-01 14:26:00", text: "Anything I promised them?" },
    { id: "demo-8897-6", role: "assistant", at: "2026-09-01 14:27:00", text: "Only a Friday answer on renewal quantities. I would send that after the review, not before." },
  ],
};

// The ids an item needs, found in the recording by what the item IS - a task's title, a review's subject, a
// message's subject, a report's name. A name the recording does not have leaves the item as written.
export function bindIds(fx, item) {
  if (!item?.bind) return item;
  const { bind, ...rest } = item;
  const tasks = fx?.["/api/tasks"]?.data || [], reviews = fx?.["/api/reviews"]?.data || [], feed = fx?.["/api/feed"]?.data || [];
  const src = fx?.["/api/sources"], sources = Array.isArray(src) ? src : src?.data || [];
  const ref = (tid) => `TQ-${String(tid).padStart(4, "0")}`;
  const out = { ...rest };
  if (bind.task) {
    const t = tasks.find((x) => x.Title === bind.task);
    if (t) {
      const latest = feed.filter((r) => r.TaskId === t.TaskId).sort((a, b) => b.MessageId - a.MessageId)[0];
      Object.assign(out, { tid: t.TaskId, ref: ref(t.TaskId), ...(latest ? { mid: latest.MessageId } : {}),
        key: bind.key === "msg" && latest ? `msg:${latest.MessageId}` : `${bind.key || "task"}:${t.TaskId}` });
    }
  }
  if (bind.review) {
    const r = reviews.find((x) => x.Subject === bind.review);
    if (r) Object.assign(out, { key: `review:${r.ReviewId}`, rid: r.ReviewId, mid: r.MessageId, tid: r.TaskId, ref: ref(r.TaskId) });
  }
  if (bind.msg) {
    const m = feed.find((x) => x.Subject === bind.msg);
    if (m) Object.assign(out, { key: `msg:${m.MessageId}`, mid: m.MessageId });
  }
  if (bind.report) {
    const m = feed.find((x) => x.Channel === "report" && String(x.Subject || "").startsWith(bind.report));
    const s = sources.find((x) => (x.Address || x.Title) === bind.report);
    if (m) Object.assign(out, { key: `report:${m.MessageId}`, mid: m.MessageId, ...(s ? { source_id: s.SourceId } : {}) });
  }
  return out;
}

export function createDemoAssistantState(fx = {}) {
  const bound = (list) => list.map((m) => (m.card ? { ...m, card: bindIds(fx, m.card) } : m));
  const items = pileItems.map((i) => bindIds(fx, i));
  const waits = items.filter((i) => onYou(i)).length;   // the rail's own on you, as the opener and header count it
  const counted = (m) => (m.text?.includes("{n}") ? { ...m, text: m.text.replace("{n}", waits === 1 ? "One thing" : `${waits} things`) } : m);
  const transcripts = Object.fromEntries(Object.entries(DEMO_ASSISTANT_TRANSCRIPTS).map(([k, v]) => [k, bound(v).map(counted)]));
  const census = items.find((i) => i.lane === "blocked");
  return {
    activeTaskId: 8900,
    task: { TaskId: 8900, Title: "What needs me before the ops review?", Kind: "general", Status: "open", Source: "assistant", SourceRef: "assistant:dock", CreatedAt: "2026-09-03 10:14:00" },
    messages: structuredClone(transcripts[8900]),
    chats: structuredClone(DEMO_ASSISTANT_CHATS),
    transcripts: structuredClone(transcripts),
    pile: {
      rev: "demo-assistant-1", items: structuredClone(items), hidden: 0, muted: 2,
      rules: ["vendor newsletters", "automated success notices"], events: [],
      alerts: [
        { key: `alert:${census?.key}`, item: census?.key, kind: "agent", lane: "blocked", text: `An agent asked you something on ${census?.ref}` },
      ],
      lanes: [
        { lane: "blocked", word: WORD.blocked, role: "you", n: 1 },
        { lane: "yours", word: WORD.yours, role: "you", n: 2 },
        { lane: "approve", word: WORD.approve, role: "you", n: 2 },
        { lane: "asked", word: WORD.asked, role: "working", n: 1 },
        { lane: "forgotten", word: WORD.forgotten, role: "info", n: 1 },
        { lane: "report", word: WORD.report, role: "info", n: 2 },
        { lane: "fyi", word: WORD.fyi, role: null, n: 1 },
        { lane: "working", word: "agent working", role: "working", n: 1 },
      ],
    },
  };
}

export function installDemoAssistantTimeline(state, posts = DEMO_ASSISTANT_TIMELINE) {
  const feed = state?.["/api/feed"]?.data;
  if (!Array.isArray(feed)) return state;
  const have = new Set(feed.map((row) => row.MessageId));
  for (const post of posts) {
    if (have.has(post.MessageId)) continue;
    const { BodyText, ...row } = post;
    feed.push(row);
    state["/api/messages/one"] ||= {};
    state["/api/messages/one"][post.MessageId] = {
      MessageId: post.MessageId, TaskId: post.TaskId, ExternalId: `demo-assistant-${post.MessageId}`,
      ConversationId: post.ConversationId, Channel: post.Channel, SourceName: post.SourceName,
      Subject: post.Subject, FromName: post.FromName, FromEmail: null, SentAt: post.SentAt,
      BodyText, SourceLink: null, Status: post.MsgStatus, CreatedAt: post.SentAt,
      Direction: "in", RecipientsJson: null, MailMetaJson: null, Brief: null,
    };
  }
  feed.sort((a, b) => String(b.SentAt || "").localeCompare(String(a.SentAt || "")));
  return state;
}
