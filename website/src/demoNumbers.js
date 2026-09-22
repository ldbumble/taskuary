// A fictional, repeatable general-assistant walkthrough, selected with ?workflow=numbers.
// These are authored sample records, never figures read from a connected account.
export const NUMBERS_TASK = 18;
export const NUMBERS_MESSAGE = 938;
export const NUMBERS_REVIEW = 903;
export const NUMBERS_REQUEST = 'Can you send me the latest August vendor spend numbers before the operations review? Please include the total, the change from July, and a breakdown by category.';
export const NUMBERS_DRAFT = 'Hi Ruth,\n\nAugust vendor spend was $192,600, up $14,200 (8.0%) from July’s $178,400.\n\n• Supplies: $78,400\n• Services: $64,200\n• Software: $50,000\n\nThe three categories reconcile to the total. These are posted invoices through August 31; open purchase orders are excluded.\n\nDana';
export const NUMBERS_RESULT = `## August vendor spend is ready for review

| Category | August |
| :-- | --: |
| Supplies | $78,400 |
| Services | $64,200 |
| Software | $50,000 |
| **Total** | **$192,600** |

July was **$178,400**. August increased **$14,200 (8.0%)**.

**Checked:** the three categories add up to $192,600. The comparison uses posted invoices in both months.

**Source:** Northwind Finance → posted vendor invoices → through August 31. Open purchase orders are excluded.

I prepared the reply to Ruth on its task. Nothing has been sent.

*Fictional demo records and scripted analysis; no database or AI was called.*`;

export function installNumbersWorkflow(state, assistant) {
  const created = '2026-09-03 10:22:00';
  const task = { TaskId: NUMBERS_TASK, ref: 'TQ-0018', Title: 'Prepare the latest vendor spend numbers', Summary: NUMBERS_REQUEST,
    Kind: 'general', Status: 'open', Priority: 'normal', Assignee: 'agent:analyst', Source: 'email', SourceRef: 'demo:vendor-numbers', CreatedBy: 'triage', CreatedAt: created };
  const message = { MessageId: NUMBERS_MESSAGE, TaskId: NUMBERS_TASK, ExternalId: 'demo-vendor-numbers', ConversationId: 'demo:vendor-numbers',
    Channel: 'email', SourceName: 'Outlook mail', Subject: 'Latest vendor spend numbers?', FromName: 'Ruth Bennett', FromEmail: 'rbennett@northwind.example',
    SentAt: created, CreatedAt: created, BodyText: NUMBERS_REQUEST, Brief: NUMBERS_REQUEST, Direction: 'in', Status: 'routed' };
  state['/api/tasks'].data.unshift(task);
  state['/api/tasks?active=1'].data.unshift(structuredClone(task));
  state['/api/tasks/detail'][NUMBERS_TASK] = { task, ref: task.ref, messages: [message], attachments: [], artifacts: [],
    routes: [{ MessageId: NUMBERS_MESSAGE, TaskId: NUMBERS_TASK, Decision: 'create', Reason: 'A request for current internal numbers: prepare the analysis and draft a reply for review.', RoutedBy: 'triage', CreatedAt: created }],
    comments: [], runs: [], audit: [], reviews: [], session: null, transcript: null };
  state['/api/messages/one'][NUMBERS_MESSAGE] = message;
  state['/api/feed'].data.unshift({ ...message, Preview: NUMBERS_REQUEST, Title: task.Title, TaskKind: 'general', TaskStatus: 'open', MsgStatus: 'routed',
    Decision: 'create', RouteDecision: 'create', RouteReason: 'Current internal figures → general assistant with the analyst profile', Category: 'task', NeedsYou: 1,
    ChainSize: 1, CanSend: true, ReviewId: null, ReviewStatus: null, HasDraft: 0 });
  state['/api/tasks/detail'][`${NUMBERS_TASK}:assistant`] = { messages: [], session: null, defaultPick: 'cli:analyst', providers: [
    { id: 'cli:analyst', pick: 'cli:analyst', type: 'cli', label: 'Claude Code · general assistant', model: '' },
    { id: 'cli:codex', pick: 'cli:codex', type: 'cli', label: 'Codex · general assistant', model: '' },
    { id: '9', pick: '9', type: 'ollama', label: 'Local model · Ollama', model: '' },
  ] };
  const item = { key: `msg:${NUMBERS_MESSAGE}`, kind: 'asked', lane: 'asked', title: message.Subject, who: 'Ruth Bennett', when: created,
    why: 'prepare the latest numbers and a reply for review', mid: NUMBERS_MESSAGE, tid: NUMBERS_TASK, ref: task.ref, channel: 'email', preview: NUMBERS_REQUEST };
  assistant.pile.items = [item]; assistant.pile.lanes = [{ lane:'asked', word:'new request', role:'working', n:1 }]; assistant.pile.alerts=[];
  assistant.pile.muted=0; assistant.pile.rules=[];
  // Start at the real welcome screen. The owner's Walk me through action surfaces the request.
  assistant.messages = [];
  assistant.transcripts[assistant.activeTaskId] = assistant.messages;
  state['/api/reviews'].data = [];
  return state;
}

export function finishNumbersWorkflow(state) {
  let review = state['/api/reviews'].data.find(r => r.ReviewId === NUMBERS_REVIEW);
  if (review) return review;
  review = { ReviewId: NUMBERS_REVIEW, TaskId: NUMBERS_TASK, MessageId: NUMBERS_MESSAGE, Kind:'draft', Status:'pending',
    DraftText:NUMBERS_DRAFT, FinalText:null, Reason:'Vendor spend summary prepared for your review', CreatedAt:'2026-09-03 10:24:00',
    Title:'Prepare the latest vendor spend numbers', Subject:'Latest vendor spend numbers?', FromName:'Ruth Bennett', FromEmail:'rbennett@northwind.example',
    Channel:'email', SourceName:'Outlook mail', Preview:NUMBERS_REQUEST, CanSend:true };
  state['/api/reviews'].data.unshift(review);
  state['/api/tasks/detail'][NUMBERS_TASK].reviews=[review];
  const row=state['/api/feed'].data.find(r=>r.MessageId===NUMBERS_MESSAGE);
  Object.assign(row,{ReviewId:NUMBERS_REVIEW,ReviewStatus:'pending',HasDraft:1,NeedsYou:1,Category:'review'});
  return review;
}
