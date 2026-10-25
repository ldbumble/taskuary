"""WHAT THE ASSISTANT DOES WITH WHAT THE OWNER TYPES - ~120 everyday asks, run against the demo world (the owner, 2026-10-20: "can you
test out the assistant makes sense to all sorts of queries?" after "Clear all the FYI, please." was answered "Next.").

Each ask runs three ways, none of them a real model (no CLI is ever started - make_cli_llm and build_llm raise here):
  1. DEMO - the demo's scripted brain (demo.brain), the one a visitor to `taskuary --demo` talks to. It reads keywords, so this is
     where a keyword fast path can misfire: its line must be the one the ask is about, or the honest "beyond a script".
  2. IDEAL - a scripted brain that answers the way a good model would (`ideal`: its CALL lines, then its words). What is graded is
     what Taskuary's deterministic road does with that answer: the button it lights, the page it opens, the look-up it runs.
  3. CARRIED - whether the real model's prompt (system + turn) names a tool that could satisfy the ask (`tools`); an ask with no
     tool at all is UNSUPPORTED, listed by how often an owner would say it.

Grades: right | wrong | unsupported (no tool exists) | bare-Next (answered "Next." over an ask that was not Next).
`python -m tests.assistant_queries` prints the table; tests/test_assistant_queries.py holds every grade.
"""
import json, os, re
from collections import Counter
from contextlib import ExitStack
from unittest import mock

# the table each ask is typed over - the demo world's own rows (demo.seed)
TABLES = {'todo': 'msg:1', 'review': 'review:2', 'agent': 'agent:6', 'fyi': 'msg:5', 'report': 'report:10', 'coding': 'msg:17', None: None}


def c(_kind, **params): return 'CALL: ' + json.dumps({'kind': _kind, 'params': params})


class Q:
    """One ask. `ideal`: the scripted answers in order (a CALL line, then words after a look-up). `expect`: the outcome the deterministic
    road must reach - light:<verb> | open:<href> | new:<kind> | next | draft:<verb> | read:<tool> | link:<href> | cleared | words.
    `tools`: what in the real prompt could satisfy it - () when nothing can (unsupported), including a tool the catalogue has but the desk
    has no button for. `demo`: the scripted demo line that fits - reply | report | list | open (an item or report brought up) | lit (a row button lit) | out (beyond a script). `freq`: how often an owner
    would say it, 1-5 - ranks the unsupported list."""
    def __init__(self, cat, text, table, ideal, expect, tools=None, demo='out', freq=3, sort=None, live=None, note='', phone=False):
        self.cat, self.text, self.table, self.expect, self.demo, self.freq, self.sort = cat, text, table, expect, demo, freq, sort
        self.live, self.note, self.phone = live, note, phone      # live: the task whose agent session runs; note: why it grades so; phone: a phone chat
        self.ideal = ideal if isinstance(ideal, list) else [ideal]
        kinds = [json.loads(a[6:])['kind'] for a in self.ideal if isinstance(a, str) and a.startswith('CALL: ')]
        self.tools = tuple(kinds[:1]) if tools is None else tuple(tools)


T1, T4, T6, T12 = 'TQ-0001', 'TQ-0004', 'TQ-0006', 'TQ-0012'
CASES = [
    # ── navigation: a page, a report, a task by ref or by name ──
    Q('navigation', 'open settings', None, 'Here: [Settings](#settings=config).', 'link:#settings', tools=('pages',), freq=4),
    Q('navigation', 'show me my connections', None, 'They are here: [Connections](#connector=).', 'link:#connector', tools=('connections.list', 'pages'), freq=3),
    Q('navigation', 'take me to the AP ageing report', None, 'Here it is: [AP ageing over 30 days, weekly](#report=5).', 'link:#report', tools=('pages',), demo='open', freq=3),
    Q('navigation', f'open {T4}', 'todo', f'Here: [{T4}](#task=4).', 'link:#task=4', tools=('pages',), demo='open', freq=5),
    Q('navigation', 'open the invoice 88213 task', 'todo', [c('tasks.list', contains='invoice 88213'), f'That is [{T4}](#task=4).'], 'read:tasks.list', demo='open', freq=4),
    Q('navigation', "pull up Marcus's month-end close", None, [c('tasks.list', contains='month-end close'), f'That is [{T1}](#task=1).'], 'read:tasks.list', demo='open', freq=4),
    Q('navigation', 'where do I set up the AI?', None, 'Under [Connections → AI](#settings=config&group=How%20mail%20is%20sorted).', 'link:#settings', tools=('pages',), freq=3),
    Q('navigation', 'open the agent profiles', None, 'Here: [Profiles](#profiles).', 'link:#profiles', tools=('pages',), freq=2),
    Q('navigation', 'show me the workflows', None, 'Here: [Workflows](#report=workflows).', 'link:#report=workflows', tools=('pages',), freq=2),
    Q('navigation', 'go to the memory page', None, 'Here: [Verdicts & notes](#settings=memory).', 'link:#settings=memory', tools=('pages',), freq=2),
    Q('navigation', 'open the GitHub connection', None, 'Here: [GitHub](#connector=github).', 'link:#connector=github', tools=('pages',), freq=2),
    Q('navigation', 'show me the new starter task', None, [c('tasks.list', contains='new starter'), 'That is [TQ-0002](#task=2).'], 'read:tasks.list', demo='open', freq=3),
    Q('navigation', 'bring up the census sync bug', None, [c('tasks.list', contains='census sync'), f'That is [{T12}](#task=12).'], 'read:tasks.list', demo='open', freq=3),
    Q('navigation', 'open the audit log', None, 'Here: [Audit](#settings=audit).', 'link:#settings=audit', tools=('pages',), freq=1),
    # ── bulk: sets of items ──
    Q('bulk', 'Clear all the FYI, please.', 'todo', c('pipe.clear', select={'kind': 'fyi'}), 'cleared', freq=5),
    Q('bulk', 'mark all the fyi read', 'fyi', c('pipe.clear', select={'kind': 'fyi'}), 'cleared', freq=5),
    # one FYI on the table is still "the FYI": marking read names the set, never Next (the real-CLI walk, 2026-10-20)
    Q('bulk', 'mark the FYI read', 'fyi', c('pipe.clear', select={'kind': 'fyi'}), 'cleared', freq=5),
    Q('bulk', 'mark everything read', 'todo', c('pipe.clear', select={'everything': True}), 'cleared', freq=3),
    Q('bulk', 'clear all the reports', 'todo', c('pipe.clear', select={'category': 'report'}), 'cleared', freq=4),
    Q('bulk', 'get rid of everything from Platform Updates', 'todo', c('pipe.clear', select={'sender': 'Platform Updates'}), 'cleared', freq=3),
    Q('bulk', 'clear the newsletters', 'todo', c('pipe.clear', select={'contains': 'newsletter'}), 'cleared', freq=3),
    Q('bulk', 'clear the fyi older than 6 hours', 'todo', c('pipe.clear', select={'kind': 'fyi', 'older_than_hours': 6}), 'cleared', freq=2),
    Q('bulk', 'clear all my to-dos', 'todo', c('pipe.clear', select={'lane': 'yours'}), 'words', freq=2,
      note='what is on the owner is never swept by typed words: each has its own button, and the line says so'),
    Q('bulk', 'clear them all', 'todo', c('pipe.clear', select={}), 'words', tools=('pipe.clear',), freq=3),
    Q('bulk', 'stop sending me mail from Platform Updates', 'fyi', c('not_ours_sender'), 'light:not_ours', tools=('not_ours_sender', 'preference.exclude_sender'), freq=3),
    Q('bulk', 'snooze everything from Ruth until Monday', 'todo', c('pipe.defer', select={'sender': 'Ruth'}, until='monday 9am'), 'did:pipe.defer', freq=3),
    Q('bulk', 'close all the tasks from Priya', 'todo', c('pipe.close', select={'sender': 'Priya'}), 'did:pipe.close', freq=2),
    Q('bulk', 'archive all the read mail', 'todo', 'Read mail is already off the rail - it stays on the Timeline.', 'words', tools=(), freq=2),
    Q('bulk', 'approve all the drafts', 'review', c('review.each'), 'light:approve', freq=2),
    Q('bulk', 'mark all the approvals as done', 'review', c('pipe.close', select={'kind': 'review'}), 'did:pipe.close', freq=1),
    # ── item actions over the table ──
    Q('item', 'reply to this', 'todo', c('reply'), 'draft:reply', demo='reply', freq=5),
    Q('item', 'tell Marcus I will look at it this afternoon', 'todo', c('reply', text='I will look at it this afternoon'), 'draft:reply', freq=5),
    Q('item', 'reply and loop Priya in', 'todo', c('reply', cc=['Priya Shah']), 'draft:reply', demo='reply', freq=3),
    Q('item', 'send it', 'review', c('approve'), 'light:approve', freq=5),
    Q('item', 'redraft it shorter', 'review', c('redraft', text='shorter'), 'draft:redraft', freq=4),
    Q('item', 'send this to an agent', 'todo', c('regular_agent', text='find the 4,180 gap in the month-end close'), 'light:regular_agent', freq=4),
    Q('item', 'hand this to a coding agent', 'coding', c('coding_agent', text='fix the census sync'), 'light:regular_agent', freq=4,
      note='the demo world has no coding CLI, so a coding hand-off is the one Send to agent (coding needs a CLI)'),
    Q('item', 'remind me tomorrow', 'todo', c('task.defer', until='tomorrow 9am'), 'light:defer', demo='lit', freq=5),
    Q('item', 'remind me about this on friday at 2pm', 'todo', c('task.defer', until='friday 2pm'), 'light:defer', demo='lit', freq=4),
    Q('item', 'not ours', 'fyi', c('not_ours'), 'pressed:not_ours', freq=4),
    Q('item', 'this is not ours', 'todo', c('task.not_a_task'), 'pressed:remove', freq=3, note="a task's row has Remove - not a task, not Not ours"),
    Q('item', 'change the priority to high', 'todo', c('task.update', priority='high'), 'light:priority', freq=3),
    Q('item', 'make this urgent', 'todo', c('task.update', priority='urgent'), 'light:priority', freq=3),
    Q('item', 'mark this done', 'todo', c('close'), 'pressed:close', demo='lit', freq=5),
    Q('item', 'done', 'todo', c('close'), 'pressed:close', demo='lit', freq=4),
    Q('item', 'close it, the bank feed reconciled', 'todo', c('task.complete', note='the bank feed reconciled'), 'pressed:close_note', freq=3),
    Q('item', 'assign it to me', 'todo', c('task.update', assignee='owner'), 'light:assign', freq=2),
    Q('item', 'forward this to Priya', 'todo', c('task.handoff', who='Priya Shah'), 'light:forward', freq=3),
    Q('item', 'ask Marcus which account it is', 'todo', c('task.clarify', text='Which account is short?'), 'light:ask_sender', freq=3),
    Q('item', 'put it on my list', 'fyi', c('mine'), 'light:mine', freq=3),
    Q('item', 'next', 'todo', c('next'), 'next', freq=5),
    Q('item', 'skip this one', 'todo', c('next'), 'next', freq=4),
    Q('item', 'remember that Marcus owns the bank feed', 'todo', c('remember', text='Marcus owns the bank feed'), 'open:#settings=memory', freq=2),
    Q('item', 'split this into two tasks', 'todo', c('task.split', text='the bank feed; the 4,180 gap'), 'light:split', freq=1),
    Q('item', 'file a note on it: waiting on the bank', 'todo', c('task.comment', text='waiting on the bank'), 'did:task.comment', freq=2),
    Q('item', 'set the due date to friday', 'todo', c('task.update', due='friday'), 'did:task.update', freq=2),
    Q('item', 'tick the second to-do', 'todo', c('task.check', item='2'), 'did:task.check', freq=3),
    Q('item', 'note on the first to-do: the bank has it', 'todo', c('task.check', item='1', note='the bank has it'), 'did:task.check', freq=2),
    Q('item', 'add a to-do: call the bank', 'todo', c('task.checklist', add=['call the bank']), 'did:task.checklist', freq=3),
    Q('item', 'press Review changes', 'todo', c('button.light', button='remove'), 'pressed:remove', freq=1, note='any row button, by name'),
    Q('item', 'reopen it', 'todo', c('task.reopen', ref='TQ-0015'), 'light:reopen', freq=2),
    Q('item', 'delete this', 'todo', c('task.not_a_task'), 'pressed:remove', freq=2),
    # ── questions ──
    Q('question', "what's waiting on me", None, [c('pipe.list'), 'Ten things are on you.'], 'read:pipe.list', demo='list', freq=5),
    Q('question', 'what is this about?', 'todo', [c('task.read', ref=T1), 'The month-end close is short by 4,180.'], 'read:task.read', freq=5),
    Q('question', 'what did Priya ask?', None, [c('sender.read', who='Priya Shah'), 'She asked about the new starter.'], 'read:sender.read', freq=4),
    Q('question', 'when is my next meeting?', None, [c('calendar.read', **{'from': 'today'}), 'The AP cutover dry run.'], 'read:calendar.read', freq=4),
    Q('question', f'what did the agent do on {T6}?', None, [c('task.read', ref=T6), 'It reconciled most of the export.'], 'read:task.read', demo='open', freq=4),
    Q('question', 'what is on my calendar tomorrow', None, [c('calendar.read', **{'from': 'tomorrow'}), 'Nothing yet.'], 'read:calendar.read', freq=4),
    Q('question', 'did I miss anything?', None, [c('missed.check'), 'Nothing slipped.'], 'read:missed.check', freq=4),
    Q('question', 'anything urgent?', None, [c('pipe.list'), 'Nothing is marked urgent.'], 'read:pipe.list', freq=4),
    Q('question', 'what failed today?', None, [c('errors.list', days=1), 'Nothing failed.'], 'read:errors.list', freq=3),
    Q('question', 'find the mail about the Q3 numbers', None, [c('timeline.search', contains='Q3 numbers'), 'Sam asked for them.'], 'read:timeline.search', freq=4),
    Q('question', 'what drafts are waiting for my yes?', None, [c('approvals.list'), 'Five drafts wait.'], 'read:approvals.list', freq=3),
    Q('question', 'what do you remember about me?', None, [c('memory.list'), 'Nothing yet.'], 'read:memory.list', freq=2),
    Q('question', 'how many open tasks do I have', None, [c('tasks.list'), 'Fourteen.'], 'read:tasks.list', demo='list', freq=3),
    Q('question', 'why did I never see the vendor portal notices', None, [c('rules.list', about='vendor portal'), 'No rule filters them.'], 'read:rules.list', freq=2),
    Q('question', 'how do I set up a report?', None, [c('docs.search', query='set up a report'), 'Press New, then Report.'], 'read:docs.search', demo='open', freq=3),
    Q('question', "what's the PO approval limit here", None, [c('knowledge.search', query='PO approval limit'), 'Nothing written down about it.'], 'read:knowledge.search', freq=2),
    Q('question', 'what did I do yesterday', None, [c('activity.list', days=2), 'You closed six.'], 'read:activity.list', freq=2),
    Q('question', 'what did I ask you to do this week', None, [c('asks.list', status='all'), 'Two asks.'], 'read:asks.list', freq=2),
    Q('question', 'who is Ruth Bennett', None, [c('sender.read', who='Ruth Bennett'), 'She writes about the AP cutover.'], 'read:sender.read', freq=2),
    # ── the memory, read and corrected in words (slice 7 of the memory redesign, approved 2026-10-25) ──
    Q('memory', "who's Gail to me", None, [c('memory.about', who='Gail'), 'Nothing in the memory about her yet.'], 'read:memory.about', freq=3),
    Q('memory', 'Gail moved to Ops', None, c('memory.remember', note='Gail Moreno moved to Ops', about='gail@northwind.example'), 'did:memory.remember', freq=2),
    Q('memory', 'forget that Ray does payroll', None, [c('memory.about', who='Ray'), 'Nothing in the memory says that about Ray.'], 'read:memory.about', freq=2,
      note='the demo world has learned nothing yet; the closing and forgetting itself is tests/test_memory_edit.py'),
    Q('question', 'summarize my day', None, [c('pipe.list'), 'Ten on you; two meetings.'], 'read:pipe.list', demo='list', freq=4),
    # ── settings ──
    Q('settings', 'turn off sounds', None, c('setting.set', setting='hand_sound', value='0'), 'open:#settings=config', freq=3),
    Q('settings', 'change my signature', None, c('setting.set', setting='email_signature', value='Alex'), 'open:#settings=config', freq=3),
    Q('settings', 'connect Outlook', None, c('setup', text='connect Outlook'), 'open:#connector=outlook', sort={'kind': 'connection', 'provider': 'outlook'}, freq=4),
    Q('settings', 'turn off background sync', None, c('setting.set', setting='poll_minutes', value='0'), 'open:#settings=config', freq=2),
    Q('settings', 'stop marking mail read in my inbox', None, c('setting.set', setting='mark_read_enabled', value='0'), 'open:#settings=config', freq=2),
    Q('settings', 'what timezone am I in', None, [c('setting.read', key='timezone'), 'Your timezone is set to the computer.'], 'read:setting.read', freq=1),
    Q('settings', 'turn off the desktop notifications', None, c('setting.set', setting='hand_desktop', value='0'), 'open:#settings=config', freq=2),
    Q('settings', 'switch off the GitHub connection', None, c('connection.pause', name='GitHub'), 'open:#connector=github', freq=1),
    Q('settings', 'test the Outlook connection', None, c('connection.test', name='Outlook'), 'open:#connector=outlook', freq=2),
    Q('settings', 'which AI runs triage?', None, [c('agents.list'), 'Triage uses the default brain.'], 'read:agents.list', freq=2),
    Q('settings', 'use dark mode', None, 'The theme is the switch in the top bar.', 'words', tools=(), freq=2),
    Q('settings', 'make the font bigger', None, 'Text size follows the browser: Ctrl and + makes it bigger.', 'words', tools=(), freq=1),
    # ...siblings of "update taskuary" (2026-10-23): the app's own settings and connections are its screens, never an agent's job; one
    # it does not have is said in words - never a hand-off to build or find it
    Q('settings', 'turn on quiet hours', None, [c('app.find', query='quiet hours'), 'There is no quiet-hours switch - the sound and the desktop notification are '
      'each their own setting under Notifications.'], 'read:app.find', freq=2, note='no such setting: said in words, never an agent sent to build it'),
    Q('settings', 'turn on share links', None, 'Sharing is per task - the Share button on its row; there is no switch for it.', 'words', tools=('words',), freq=2,
      note='no such setting: a task is shared from its own row'),
    Q('settings', 'connect my bank', None, c('setup', text='connect my bank'), 'open:#connector=teller', sort={'kind': 'connection', 'provider': 'teller'}, freq=2),
    # ── agents ──
    Q('agents', 'stop the agent', 'agent', c('stop_agent'), 'light:stop_agent', freq=4, live=6),
    Q('agents', 'stop the agent', 'agent', [c('stop_agent'), 'Nothing is running on it now - there is nothing to stop.'], 'words', freq=2,
      note='no session is running on the task: Stop and save is not on its row'),
    Q('agents', 'continue it', 'agent', [c('agent.continue', ref=T6), 'It has no saved session to pick up - Send to agent starts one.'], 'words', freq=3,
      note='the demo task has no saved session, so Continue is not on its row'),
    Q('agents', 'what is the agent doing?', 'agent', [c('agents.now'), 'It is reconciling the August export.'], 'read:agents.now', freq=4),
    Q('agents', 'which agents are running', None, [c('agents.now'), 'One, on TQ-0006.'], 'read:agents.now', freq=3),
    Q('agents', 'tell the agent to skip the inter-company rows', 'agent', c('answer_agent', text='skip the inter-company rows'), 'words', tools=('answer_agent', 'agent.answer'), freq=3),
    Q('agents', f'start an agent on {T12}', None, c('dispatch.prepare', ref=T12, kind='coding'), 'light:regular_agent', demo='open', freq=3),
    Q('agents', 'research what Payworth charges per seat', None, c('task.create_from_text', kind='general', text='research what Payworth charges per seat', title='Payworth seat price'), 'new:agent:general', freq=3),
    Q('agents', 'have a coding agent fix the census sync timeout', None, c('task.create_from_text', kind='coding', text='fix the census sync timeout', title='Census sync timeout'), 'new:agent', freq=3, note='no coding CLI in the demo world: written into New as an agent job'),
    Q('agents', 'kill all the agents', None, 'Each agent stops from its own row - there is no stop-all.', 'words', tools=(), freq=1),
    # ── reports ──
    Q('reports', 'run the end of day report', None, c('report.run', title='End of day checkup'), 'open:#report=', demo='open', freq=4),
    Q('reports', 'run the AP ageing again', 'report', c('rerun'), 'open:#report=', freq=3),
    Q('reports', 'pause the headcount report', None, c('report.pause', title='Headcount by site'), 'open:#report=', demo='open', freq=2),
    Q('reports', 'every monday send me the overdue invoices', None, c('setup', text='every monday send me the overdue invoices'), 'new:report', sort={'kind': 'report'}, demo='report', freq=3),
    Q('reports', 'what did the helpdesk report say?', None, [c('report.read', title='Helpdesk tickets'), 'Fourteen rows.'], 'read:report.read', demo='open', freq=3),
    Q('reports', 'list my reports', None, [c('reports.list'), 'Five reports.'], 'read:reports.list', demo='open', freq=2),
    Q('reports', 'delete the headcount report', None, c('report.delete', title='Headcount by site'), 'open:#report=', demo='open', freq=1),
    Q('reports', 'make the AP ageing daily', None, c('report.edit', title='AP ageing', config={'daily_at': '08:00'}), 'open:#report=', demo='report', freq=2),
    # ── chit-chat and the ambiguous ──
    Q('chat', 'hi', None, 'Morning - ten things are on you.', 'words', tools=('words',), freq=4),
    Q('chat', 'thanks', 'todo', 'Any time.', 'words', tools=('words',), freq=4),
    Q('chat', 'what can you do?', None, [c('docs.search', query='assistant'), 'I bring up the button or the page for what you ask.'], 'read:docs.search', freq=3),
    Q('chat', "what's the weather", None, 'I cannot see the weather from here.', 'words', tools=('words',), freq=1),
    Q('chat', 'help', None, [c('docs.search', query='getting started'), 'Ask me what is waiting, or to draft a reply.'], 'read:docs.search', freq=3),
    Q('chat', 'ugh', 'todo', 'Long day? The next one is a quick one.', 'words', tools=('words',), freq=1),
    Q('chat', 'do the thing', 'todo', 'Which thing - the reply, or Mark done?\nOPTIONS: Reply | Mark done', 'words', tools=('words',), freq=1),
    Q('chat', 'tell me a joke', None, 'I keep the jokes for after the inbox is clear.', 'words', tools=('words',), freq=1),
    Q('chat', 'what should I do next?', 'todo', 'Reply to Marcus about the 4,180 - he is waiting.', 'words', tools=('words',), freq=4),
    # ── typos ──
    Q('typos', 'clera all teh fyi', 'todo', c('pipe.clear', select={'kind': 'fyi'}), 'cleared', freq=3),
    Q('typos', 'remidn me tmrw', 'todo', c('task.defer', until='tomorrow'), 'light:defer', freq=3),
    Q('typos', 'mark tihs done', 'todo', c('close'), 'pressed:close', demo='lit', freq=3),
    Q('typos', 'whats waitng on me', None, [c('pipe.list'), 'Ten things.'], 'read:pipe.list', demo='list', freq=3),
    Q('typos', 'opne settigns', None, 'Here: [Settings](#settings=config).', 'link:#settings', tools=('pages',), freq=2),
    Q('typos', 'repyl to marcus', 'todo', c('reply'), 'draft:reply', freq=3),
    # ── WhatsApp-style short replies ──
    Q('short', 'yes', 'review', c('approve'), 'light:approve', freq=5),
    Q('short', '2', 'todo', 'Ok.', 'words', tools=('digit',), demo='lit', freq=4),
    Q('short', 'skip', 'todo', c('next'), 'next', freq=4),
    Q('short', 'no', 'review', 'Then it stays as drafted - nothing is sent.', 'words', tools=('words',), freq=4),
    Q('short', 'ok', 'todo', 'Ok.', 'words', tools=('words',), freq=4),
    Q('short', 'later', 'todo', c('task.defer', until='tomorrow 9am'), 'light:defer', freq=3),
    Q('short', 'k', 'todo', 'Ok.', 'words', tools=('words',), freq=2),
    Q('short', '👍', 'todo', 'Ok.', 'words', tools=('words',), freq=3),
    Q('short', 'done.', 'todo', c('close'), 'pressed:close', demo='lit', freq=4),
]

def find(query, title_hint=''):
    """The good answer to "bring X up": app.find, then the candidate it lists first, linked - the deterministic part is the index's ranking."""
    def pick(user):
        m = re.search(r'link it as (\[[^\]]+\]\(#[^)]+\))', user)
        return f'Here: {m.group(1)}' if m else 'I could not find it.'
    return [c('app.find', query=query), pick]


BRING_UP = [
    ('turn off the sound', 'sound', '#settings=config&group=Notifications&key=hand_sound'),
    ('where do I change my signature', 'signature', '#settings=config&group=Replies&key=email_signature'),
    ('the sync interval', 'sync interval', '#settings=config&group=Sync%20%26%20startup&key=poll_minutes'),
    ('desktop notifications', 'desktop notification', '#settings=config&group=Notifications&key=hand_desktop'),
    ('which AI does triage', 'triage brain', '#settings=config&group=How%20mail%20is%20sorted&key=triage_ai'),
    ('the assistant model', 'assistant model', '#settings=config&group=How%20mail%20is%20sorted&key=concierge_model'),
    ('stop marking mail read in my inbox setting', 'mark read source', '#settings=config&group=Sync%20%26%20startup&key=mark_read_enabled'),
    ('how many days back it catches up', 'catch-up window', '#settings=config&group=Sync%20%26%20startup&key=startup_sync_days'),
    ('the FYI batching setting', 'fyi read together', '#settings=config&group=Assistant&key=fyi_batch'),
    ('my second Outlook', 'outlook', '#connector=outlook'),
    ('LinkedIn', 'linkedin', '#connector=linkedin'),
    ('the database card', 'database', '#connector=database'),
    ('the Gmail card', 'gmail', '#connector=gmail'),
    ('my bank feed', 'bank feed', '#connector=teller'),
    ('the IMAP mailbox card', 'imap', '#connector=imap'),
    ('WhatsApp connection', 'whatsapp', '#connector=whatsapp'),
    ('the Jira card', 'jira', '#connector=jira'),
    ('the voice AI section', 'voice', '#connections=AI%20%E2%80%94%20voice'),
    ('my email connections', 'email connections', '#connections=Email'),
    ('the AP ageing report', 'AP ageing', '#report=5'),
    ('the end of day report', 'end of day', '#report=2'),
    ('the headcount report', 'headcount', '#report=4'),
    ('my workflows', 'workflows', '#report=workflows'),
    ('my SOUL doc', 'soul', '#settings=docs&doc=soul'),
    ('what it learned', 'learned', '#settings=docs&doc=learned'),
    ('the audit log', 'audit log', '#settings=audit'),
    ('agent profiles', 'profiles', '#profiles'),
    ('the routing rules', 'routing policies', '#settings=policies'),
    # ...Taskuary's own update, by any words for it: Updates, its button lit - never an agent (the owner, 2026-10-23: "i asked assistant to
    # update taskuary and it pulled up general agent")
    ('check for updates', 'updates', '#settings=updates&key=update'),
    ('update taskuary', 'update taskuary', '#settings=updates&key=update'),
    ('install the new version', 'install the new version', '#settings=updates&key=update'),
    ('upgrade the app', 'upgrade the app', '#settings=updates&key=update'),
    ('install the latest release', 'install the latest release', '#settings=updates&key=update'),
    # ...and its siblings: a connection or a brain is its own screen too, never an agent's job
    ('connect my mail', 'email connections', '#connections=Email'),
    ('change the assistant brain', 'assistant brain', '#settings=config&group=How%20mail%20is%20sorted&key=concierge_ai'),
    ('the Hub', 'hub', '#hub'),
]
# ...the demo's script brings a report it names up itself (demo._route); every other bring-up is the real brain's look-up
CASES += [Q('bring-up', t, None, find(q), f'link:{h}', demo='open' if re.fullmatch(r'#report=\d+', h) else 'out', freq=4) for t, q, h in BRING_UP]
CASES += [
    Q('connectors', 'add LinkedIn as a connector', None, c('connection.create', type='linkedin'), 'open:#connector=linkedin', freq=3),
    Q('connectors', 'connect Slack', None, c('connection.create', type='slack'), 'open:#connector=slack', freq=3),
    Q('connectors', 'set up QuickBooks', None, c('connection.create', type='QuickBooks Online'), 'open:#connector=quickbooks', freq=3),
    Q('connectors', 'I want to hook up my second Outlook', None, c('connection.create', type='outlook'), 'open:#connector=outlook', freq=3),
    Q('connectors', 'conect gmial', None, c('connection.create', type='gmail'), 'open:#connector=gmail', freq=2, note='a misspelling: the model reads it'),
    Q('connectors', 'connect Frobnitz', None, [c('connection.create', type='frobnitz'), 'There is no Frobnitz connector.'], 'words', freq=1,
      note='an unknown one: the miss names the closest cards'),
]
# THE PHONE (the owner, 2026-10-20): every act a desk row offers reachable from a phone chat too - the task page's writes at once, an act
# on an item answered yes or no, a send never without its yes
PHONE = [
    Q('phone', 'tick 2', 'todo', c('task.check', item='2'), 'did:task.check', freq=4, phone=True),
    Q('phone', 'note on 1: the bank has it', 'todo', c('task.check', item='1', note='the bank has it'), 'did:task.check', freq=3, phone=True),
    Q('phone', 'add a to-do: call the bank', 'todo', c('task.checklist', add=['call the bank']), 'did:task.checklist', freq=3, phone=True),
    Q('phone', 'note on the task: waiting on the bank', 'todo', c('task.comment', text='waiting on the bank'), 'did:task.comment', freq=3, phone=True),
    Q('phone', 'snooze everything from Ruth until Monday', 'todo', c('pipe.defer', select={'sender': 'Ruth'}, until='monday 9am'), 'did:pipe.defer', freq=3, phone=True),
    Q('phone', 'close all from Priya', 'todo', c('pipe.close', select={'sender': 'Priya'}), 'did:pipe.close', freq=2, phone=True),
    Q('phone', 'mark this done', 'todo', c('close'), 'proposal:task.complete', demo='lit', freq=4, phone=True),
    Q('phone', 'remind me tomorrow', 'todo', c('task.defer', until='tomorrow 9am'), 'proposal:task.defer', demo='lit', freq=4, phone=True),
    Q('phone', 'send it', 'review', c('approve'), 'proposal:review.approve', freq=4, phone=True),
    Q('phone', 'reply to this', 'todo', c('reply'), 'draft:reply', freq=4, phone=True, demo='reply'),
    Q('phone', 'approve all the drafts', 'review', c('review.each'), 'card', freq=2, phone=True),
    # THE APP'S OWN ACTS FROM A PHONE (2026-10-23): one with a tool is its yes or no; Updates has none, so it is named at the desk in words -
    # no link a phone cannot open, and never an agent
    Q('phone', 'connect my gmail', None, c('connection.create', type='gmail'), 'proposal:connection.create', freq=3, phone=True),
    Q('phone', 'turn off the sounds', None, c('setting.set', setting='hand_sound', value='0'), 'proposal:setting.set', freq=2, phone=True),
    Q('phone', 'update taskuary', None, [c('app.find', query='update taskuary'),
                                         lambda user: f"At your desk, {re.search(r'name it, at their desk: (.+)', user).group(1)} - press its update button."],
      'read:app.find', tools=('app.find', 'screens'), freq=3, phone=True),
    Q('phone', 'change the assistant brain', None, [c('app.find', query='assistant brain'),
                                                    lambda user: f"At your desk, {re.search(r'name it, at their desk: (.+)', user).group(1)}."],
      'read:app.find', tools=('app.find', 'screens'), freq=2, phone=True),
]
CASES += PHONE

# not tools, but roads the prompt carries all the same: a link to a page (pages_block), plain words, the desk's numbered action words
ROADS = {'pages': 'APP PAGES', 'screens': 'APP SCREENS', 'words': 'Answer in plain words', 'digit': None}


def _scripted(answers, seen):
    left = list(answers)
    def llm(system, user, **kw):
        seen.append((system, user))
        if not left: return 'Ok.'
        a = left.pop(0)
        return a(user) if callable(a) else a
    return llm


def _world():
    from taskuary import demo, funnel, terminal
    from taskuary.store import MemoryStore
    funnel.invalidate(); funnel.forget_states(); funnel._SOURCES.update(at=0.0, by={})
    s = MemoryStore()
    with mock.patch.object(terminal, 'live_sessions', return_value=[]): demo.seed(s)
    for k in ('learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    s.set_task_checklist(1, ['pull the bank feed', 'find the 4,180', 'send Marcus the answer'], 'owner')
    s.save_connector({'Type': 'outlook', 'Name': 'Work mail', 'Active': 1}, 't')
    funnel.invalidate()
    return s


def _guards(stack, sort=None, live=None):
    """No real model, ever: the CLI and API builders raise, and the set-up sorter answers from the case."""
    from taskuary import concierge, ingest, llm as llm_mod, terminal
    def never(*a, **k): raise AssertionError('a real model was asked for')
    stack.enter_context(mock.patch.object(llm_mod, 'make_cli_llm', never))
    stack.enter_context(mock.patch.object(llm_mod, 'build_llm', never))
    stack.enter_context(mock.patch.object(terminal, 'live_sessions', return_value=[]))
    # a running session on one task, where the case says so - what Stop and save is drawn by (concierge._agent_running)
    stack.enter_context(mock.patch.object(terminal, 'for_task', lambda tid, **k: {'sid': f's{tid}'} if live and int(tid) == int(live) else None))
    stack.enter_context(mock.patch.object(ingest, '_spawn'))
    sorted_ = json.dumps(sort or {'kind': 'report', 'why': 'scripted'})
    stack.enter_context(mock.patch.object(concierge, '_compose_llm', return_value=lambda *a, **k: sorted_))


# THE ACT, SAID (the owner, 2026-10-20: "it should show what it chose to do"): an answer that acted or lit leads with what it did - never a
# bare word. A proposal on a phone is its question; a look-up's answer and a link are the model's own words.
ACTS = ('Opened ', 'Marked ', 'Wrote ', 'Put down ', 'Drafting ', 'Rewriting ', 'Snoozed ', 'Closed ', 'Added ', 'Set ', 'Noted ',
        'Ticked ', 'Unticked ', 'Took ', 'Renamed ', 'Brought up ', 'Remembered ')
def said_what(say: str, got: list, q) -> bool:
    acted = [g for g in got if g.split(':')[0] in ('open', 'new', 'next', 'draft', 'cleared', 'did')]
    # ...and a lit button or a press speaks for itself - the filled button, the card's badge - and says no line (the owner, 2026-10-23)
    if any(g.split(':')[0] in ('light', 'pressed') for g in got): return not say.startswith('Lit ')
    return not acted or say.startswith(ACTS) and len(say.split()) > 3


def outcomes(out: dict, reads: list) -> list:
    """What the turn did, as words a case can expect."""
    o = []
    if (l := out.get('light')) is not None: o.append(f"light:{l.get('verb') or ''}")
    if (p := out.get('pressed')) is not None: o.append(f"pressed:{p.get('verb') or ''}")
    if out.get('open'): o.append(f"open:{out['open']}")
    if out.get('new'): o.append(f"new:{out['new'].get('kind')}" + (f":{out['new'].get('how')}" if out['new'].get('how') else ''))
    d = (out.get('decision') or {}).get('verb')
    if d == 'next': o.append('next')
    elif d in ('reply', 'redraft'): o.append(f'draft:{d}')
    elif d: o.append(f'decision:{d}')
    if out.get('cleared') is not None: o.append('cleared')
    if out.get('did'): o.append(f"did:{out['did']}")
    if out.get('card') or out.get('opened') or out.get('item'): o.append('card')
    if out.get('proposal'): o.append(f"proposal:{out['proposal'].get('kind')}")
    o += [f'read:{k}' for k in reads]
    o += [f'link:{h}' for h in re.findall(r'\]\((#[^)]+)\)', out.get('say') or '')]
    return o or ['words']


MISSES = ('I could not find', 'I could not finish', 'I could not put that', 'could not line', 'Nothing is on the table')


def ideal_turn(q: Q) -> dict:
    from taskuary import concierge, server
    s, seen, reads = _world(), [], []
    real_read = concierge._read
    def read(store, item, call):
        found = real_read(store, item, call); reads.append(call['kind']); return found
    with ExitStack() as st:
        _guards(st, q.sort, q.live)
        st.enter_context(mock.patch.object(server, 'store', s))          # a typed put-down runs its operation (concierge._put_down)
        st.enter_context(mock.patch.object(concierge, '_read', read))
        err = None
        if q.phone: st.enter_context(concierge.delivering(concierge.PHONE))
        try: out = concierge.say(s, q.text, key=TABLES[q.table], llm=_scripted(q.ideal, seen))
        except Exception as e: out, err = {'say': f'RAISED {type(e).__name__}: {e}'}, e
    heard = next((l[len(concierge.OWNER_SAYS):] for _, u in seen[:1] for l in u.splitlines() if l.startswith(concierge.OWNER_SAYS)), '')
    prompt = '\n'.join(f'{a}\n{b}' for a, b in seen[:1])
    got = outcomes(out, reads)
    say = str(out.get('say') or '')
    if not q.tools: grade = 'unsupported'
    elif err: grade = 'wrong'
    elif say.strip() == concierge.RECEIPTS['next'] and q.expect != 'next': grade = 'bare-Next'
    elif any(m in say for m in MISSES) and q.expect not in ('words',): grade = 'wrong'
    elif not said_what(say, got, q): grade = 'silent'
    elif any(g.startswith(q.expect) for g in got): grade = 'right'
    else: grade = 'wrong'
    carried = [t for t in q.tools if (t in prompt if t not in ROADS else (ROADS[t] is None or ROADS[t] in prompt))]
    # what the model was told after its first answer - a miss's own words, when the road refused it
    told = seen[1][1].split('\n\n', 1)[-1][:400] if len(seen) > 1 else ''
    return {'grade': grade, 'got': got, 'say': say, 'heard': heard, 'told': told, 'carried': carried, 'missing': [t for t in q.tools if t not in carried]}


def demo_line(said: str, out: dict | None = None) -> str:
    from taskuary import demo
    if said.startswith(demo.OUT_OF_SCRIPT[:40]): return 'out'
    # ...and the script's routing (demo._route): the item, report or page brought up, or the real button lit on the table's item
    if re.match(r'Here: \[[^\]]+\]\(#(task|report)=', said): return 'open'
    if (out or {}).get('light') or (out or {}).get('pressed'): return 'lit'
    for (rx, line), name in zip(demo.ANSWERS, ('reply', 'report', 'list')):
        if said.startswith(line.split('{')[0][:40]): return name
    return 'other'


def demo_turn(q: Q) -> dict:
    from taskuary import concierge, demo, server
    s = _world()
    with ExitStack() as st:
        _guards(st, q.sort, q.live)
        st.enter_context(mock.patch.object(server, 'store', s))
        try: out = concierge.say(s, q.text, key=TABLES[q.table], llm=demo.brain(store=s))
        except Exception as e: out = {'say': f'RAISED {type(e).__name__}: {e}'}
    said = str(out.get('say') or '')
    line = demo_line(said, out)
    return {'grade': 'right' if line == q.demo else 'bare-Next' if said.strip() == 'Next.' else 'wrong', 'line': line, 'say': said}


def run_all() -> list:
    rows = []
    for q in CASES:
        rows.append({'q': q, 'ideal': ideal_turn(q), 'demo': demo_turn(q)})
    return rows


def table(rows) -> str:
    cats = list(dict.fromkeys(r['q'].cat for r in rows))
    out = ['IDEAL brain, Taskuary\'s road (right / wrong / unsupported / bare-Next / silent) | DEMO brain (right / wrong)']
    for cat in cats + ['ALL']:
        rs = [r for r in rows if cat in ('ALL', r['q'].cat)]
        g, d = Counter(r['ideal']['grade'] for r in rs), Counter(r['demo']['grade'] for r in rs)
        out.append(f"  {cat:<11} {len(rs):>3}  ideal {g['right']:>3} / {g['wrong']:>2} / {g['unsupported']:>2} / {g['bare-Next']:>2} / {g['silent']:>2}"
                   f"   demo {d['right']:>3} / {d['wrong'] + d['bare-Next']:>2}")
    bad = [r for r in rows if r['ideal']['grade'] in ('wrong', 'bare-Next', 'silent')]
    if bad: out += ['', 'IDEAL WRONG:'] + [f"  [{r['q'].cat}] {r['q'].text!r} expect {r['q'].expect} got {r['ideal']['got']} - {r['ideal']['say'][:160]!r}" for r in bad]
    dbad = [r for r in rows if r['demo']['grade'] != 'right']
    if dbad: out += ['', 'DEMO WRONG:'] + [f"  [{r['q'].cat}] {r['q'].text!r} wants {r['q'].demo} got {r['demo']['line']} - {r['demo']['say'][:110]!r}" for r in dbad]
    nc = [r for r in rows if r['ideal']['missing']]
    if nc: out += ['', 'NOT IN THE PROMPT:'] + [f"  {r['q'].text!r}: {r['ideal']['missing']}" for r in nc]
    un = sorted((r for r in rows if r['ideal']['grade'] == 'unsupported'), key=lambda r: -r['q'].freq)
    if un: out += ['', 'UNSUPPORTED (no tool, or no button on the desk), most common first:'] + [
        f"  {r['q'].freq}  {r['q'].text!r}" + (f"  - {r['q'].note}" if r['q'].note else '') for r in un]
    out += ['', 'ROW ACTIONS (desk / phone):'] + [f"  {v:<16} desk: {d or '-':<22} phone: {p or 'UNREACHABLE'}" for v, d, p in reach()]
    return '\n'.join(out)


def reach() -> list:
    """Every button a desk row can draw, and the road that reaches it from the Assistant on the desk and from a phone chat. The desk lights
    any row button (button.light); a phone has no rows, so it reaches an act only by the decision or tool that IS it."""
    from taskuary import buttons, concierge, toolcatalog
    rows = []
    for v, d in buttons.VERBS.items():
        if not d.get('row') or v == 'fix': continue          # fix is a failure's own way out, worn by the failure
        tool = v if v in toolcatalog.DECISIONS else toolcatalog.CHIP_TOOL.get(v) or concierge.PICKER_TOOL.get(v)
        rows.append((v, tool or 'button.light', tool or ''))
    return rows


if __name__ == '__main__':
    import sys, tempfile
    os.environ['TASKUARY_HOME'] = tempfile.mkdtemp(prefix='taskuary-queries-')      # never the owner's home
    from loguru import logger; logger.remove()
    sys.stdout.reconfigure(encoding='utf-8')            # the asks carry arrows and emoji; a Windows console is cp1252
    rows = run_all()
    print(table(rows))
    if '-v' in sys.argv:
        for r in rows: print(f"\n[{r['q'].cat}] {r['q'].text}\n  heard: {r['ideal']['heard']}\n  ideal: {r['ideal']['grade']} {r['ideal']['got']} {r['ideal']['say'][:200]!r}\n  demo:  {r['demo']['line']} {r['demo']['say'][:120]!r}")
