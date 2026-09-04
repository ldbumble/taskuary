// The static demo has no concierge process behind it. These are deliberately scripted,
// invented conversations and Timeline posts: enough real-shaped data to demonstrate the
// product without implying that an AI, mailbox, or agent is running in the visitor's browser.

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

const reviewCard = {
  key: "review:1", kind: "review", lane: "approve", title: "AP cutover - Thursday?", who: "Ruth Bennett",
  when: "2026-09-03 03:25:19", why: "a reply is drafted and waiting for your yes", mid: 7, tid: 3,
  ref: "TQ-0003", rid: 1, channel: "email", preview: "Are we still moving AP over on Thursday? I need to tell the team.",
};

const pileItems = [
  {
    key: "agent:7", kind: "agent", lane: "blocked", title: "Census sync fails when a site has no manager",
    who: "Marcus Reed", when: "2026-09-03 09:35:19", why: "the coder needs a choice before changing skip behavior",
    mid: 17, tid: 7, ref: "TQ-0007", agent: "coder", working: "coder", asking: true,
    channel: "github", preview: "Should a missing manager skip only that site, or fail the entire sync?",
    tail: ["I reproduced the null manager case.", "Should a missing manager skip only that site, or fail the entire sync?"],
  },
  { ...reviewCard, surfaced: true, surfaced_at: "2026-09-03 10:20:00" },
  {
    key: "msg:15", kind: "asked", lane: "asked", title: "One more onboarding detail for the AP clerk",
    who: "Marcus Reed", when: "2026-09-03 08:21:19", why: "a follow-up was added to the onboarding thread",
    mid: 15, tid: 6, ref: "TQ-0006", channel: "email", preview: "Please include the purchasing approval group too.",
  },
  {
    key: "idea:renewal", kind: "idea", lane: "forgotten", title: "The copier renewal thread has gone quiet",
    who: "Tom Alvarez", when: "2026-09-02 16:15:00", why: "no reply since Thursday; the quote expires next week",
    idea_kind: "cold", channel: "assistant", action: { type: "followup", mid: 6 }, mid: 6,
  },
  {
    key: "report:11", kind: "report", lane: "report", title: "Helpdesk tickets by day, last 14",
    who: "Helpdesk report", when: "2026-09-03 05:53:19", why: "the scheduled report landed normally",
    mid: 11, source_id: 7, channel: "report", bad: false,
  },
  {
    key: "msg:16", kind: "fyi", lane: "fyi", title: "Vendor portal maintenance Sunday, 02:00-04:00",
    who: "Platform Updates", when: "2026-09-03 08:58:19", why: "an automated notice; nothing to do",
    mid: 16, channel: "email", preview: "The vendor portal will be unavailable during the maintenance window.",
  },
  {
    key: "agent:2", kind: "agent", lane: "working", title: "New starter on Monday - laptop + accounts",
    who: "Priya Shah", when: "2026-09-03 00:20:19", why: "the coder has it; nothing for you until it stops",
    mid: 2, tid: 2, ref: "TQ-0002", agent: "coder", working: "coder", asking: false, channel: "email",
  },
];

const currentMessages = [
  {
    id: "demo-current-1", role: "assistant", at: "2026-09-03 10:14:00",
    text: "Morning. I filed the maintenance notice and the newsletter. Three things still deserve a look; I put the cutover reply first.",
  },
  {
    id: "demo-current-2", role: "user", at: "2026-09-03 10:16:00",
    text: "What actually needs me before the operations review?",
  },
  {
    id: "demo-current-3", role: "assistant", at: "2026-09-03 10:16:10",
    text: "Ruth needs the Thursday cutover confirmed, and the census-sync coder needs one behavior choice. The onboarding follow-up can wait until those are clear.",
  },
  {
    id: "demo-current-4", role: "user", at: "2026-09-03 10:19:00",
    text: "Start with Ruth. Is the draft ready?",
  },
  {
    id: "demo-current-5", role: "assistant", at: "2026-09-03 10:19:10",
    text: "Yes. It confirms Thursday and says the export will be reconciled Wednesday night. Read the invented draft below; in this demo, Approve never sends anything.",
    card: reviewCard,
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
    { id: "demo-8899-2", role: "assistant", at: "2026-09-03 08:03:10", text: "First: Priya's new-starter request became TQ-0002 and is already with the coder.", card: { key: "agent:2", kind: "agent", lane: "working", title: "New starter on Monday - laptop + accounts", tid: 2, ref: "TQ-0002", agent: "coder", channel: "email" } },
    { id: "demo-8899-3", role: "user", at: "2026-09-03 08:05:00", text: "Good. What else?" },
    { id: "demo-8899-4", role: "assistant", at: "2026-09-03 08:05:10", text: "Ruth asked whether Thursday still holds for AP cutover. A short reply is drafted and waiting for review.", card: reviewCard },
    { id: "demo-8899-5", role: "user", at: "2026-09-03 08:07:00", text: "Leave that for the close check. Anything noisy?" },
    { id: "demo-8899-6", role: "assistant", at: "2026-09-03 08:07:10", text: "Two FYIs: a maintenance window and a newsletter. Neither started work, and both were filed." },
    { id: "demo-8899-7", role: "user", at: "2026-09-03 08:11:00", text: "That's right. Done." },
    { id: "demo-8899-8", role: "assistant", at: "2026-09-03 08:12:00", text: "Overnight is clear. The cutover reply remains in Review for later." },
  ],
  8898: [
    { id: "demo-8898-1", role: "user", at: "2026-09-02 16:38:00", text: "What changed in month-end since lunch?" },
    { id: "demo-8898-2", role: "assistant", at: "2026-09-02 16:38:10", text: "The reconciliation traced the 4,180 difference to four inter-company rows omitted by the export. The fix is tested; no ledger entries were changed." },
    { id: "demo-8898-3", role: "user", at: "2026-09-02 16:41:00", text: "Keep the task open until finance checks the file." },
    { id: "demo-8898-4", role: "assistant", at: "2026-09-02 16:42:00", text: "Kept open. Finance's check is the remaining step on TQ-0001.", card: { key: "task:1", kind: "task", lane: "asked", title: "Month-end close is short by 4,180", tid: 1, ref: "TQ-0001", why: "waiting for finance to check the corrected export" } },
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

export function createDemoAssistantState() {
  return {
    activeTaskId: 8900,
    task: { TaskId: 8900, Title: "What needs me before the ops review?", Kind: "general", Status: "open", Source: "assistant", SourceRef: "assistant:dock", CreatedAt: "2026-09-03 10:14:00" },
    messages: structuredClone(DEMO_ASSISTANT_TRANSCRIPTS[8900]),
    chats: structuredClone(DEMO_ASSISTANT_CHATS),
    transcripts: structuredClone(DEMO_ASSISTANT_TRANSCRIPTS),
    pile: {
      rev: "demo-assistant-1", items: structuredClone(pileItems), hidden: 0, muted: 2,
      rules: ["vendor newsletters", "automated success notices"], events: [],
      alerts: [
        { key: "alert:agent:7", item: "agent:7", kind: "agent", lane: "blocked", text: "coder asked you something on TQ-0007" },
      ],
      lanes: [
        { lane: "blocked", word: "agent waiting", role: "you", n: 1 },
        { lane: "approve", word: "reply pending", role: "you", n: 1 },
        { lane: "asked", word: "asked you", role: "working", n: 1 },
        { lane: "forgotten", word: "slipped", role: "info", n: 1 },
        { lane: "report", word: "report", role: "info", n: 1 },
        { lane: "fyi", word: "fyi", role: null, n: 1 },
        { lane: "working", word: "agent working", role: "working", n: 1 },
      ],
    },
  };
}

export function installDemoAssistantTimeline(state) {
  const feed = state?.["/api/feed"]?.data;
  if (!Array.isArray(feed)) return state;
  const have = new Set(feed.map((row) => row.MessageId));
  for (const post of DEMO_ASSISTANT_TIMELINE) {
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
