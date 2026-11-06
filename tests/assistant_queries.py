"""WHAT THE ASSISTANT DOES WITH WHAT THE OWNER TYPES - ~120 everyday asks, run against the demo world (the owner, 2026-10-20: "can you
test out the assistant makes sense to all sorts of queries?" after "Clear all the FYI, please." was answered "Next.").

Each ask runs three ways, none of them a real model (no CLI is ever started - make_cli_llm and build_llm raise here):
  1. DEMO - the demo's scripted brain (demo.brain), the one a visitor to `taskuary --demo` talks to. It reads no typed words (the owner,
     2026-10-28): none of these asks is one of its suggestions (demo.PROMPTS), so each must get the honest "only the suggested questions"
     line with the suggestions under it - and nothing lit, pressed or opened.
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
TABLES = {'todo': 'msg:1', 'review': 'review:2', 'agent': 'agent:6', 'fyi': 'msg:5', 'report': 'report:10', 'coding': 'msg:17', 'invite': 'msg:19',
          None: None}


def c(_kind, **params): return 'CALL: ' + json.dumps({'kind': _kind, 'params': params})


class Q:
    """One ask. `ideal`: the scripted answers in order (a CALL line, then words after a look-up). `expect`: the outcome the deterministic
    road must reach - light:<verb> | open:<href> | new:<kind> | next | draft:<verb> | read:<tool> | link:<href> | cleared | words.
    `tools`: what in the real prompt could satisfy it - () when nothing can (unsupported), including a tool the catalogue has but the desk
    has no button for. `freq`: how often an owner
    would say it, 1-5 - ranks the unsupported list."""
    def __init__(self, cat, text, table, ideal, expect, tools=None, freq=3, sort=None, live=None, note='', phone=False, view=None, seed=None):
        self.cat, self.text, self.table, self.expect, self.freq, self.sort, self.view = cat, text, table, expect, freq, sort, view
        self.seed = seed      # seed(store) -> key or None: a row the demo world lacks (a watched task, the habits row), its key on the table
        self.live, self.note, self.phone = live, note, phone      # live: the task whose agent session runs; note: why it grades so; phone: a phone chat
        self.ideal = ideal if isinstance(ideal, list) else [ideal]
        kinds = [json.loads(a[6:])['kind'] for a in self.ideal if isinstance(a, str) and a.startswith('CALL: ')]
        self.tools = tuple(kinds[:1]) if tools is None else tuple(tools)


def find(query, title_hint=''):
    """The good answer to "bring X up": app.find, then the candidate it lists first, linked - the deterministic part is the index's ranking."""
    def pick(user):
        m = re.search(r'link it as (\[[^\]]+\]\(#[^)]+\))', user)
        return f'Here: {m.group(1)}' if m else 'I could not find it.'
    return [c('app.find', query=query), pick]


T1, T4, T6, T12 = 'TQ-0001', 'TQ-0004', 'TQ-0006', 'TQ-0012'
CASES = [
    # ── navigation: a page, a report, a task by ref or by name ──
    Q('navigation', 'open settings', None, 'Here: [Settings](#settings=config).', 'link:#settings', tools=('pages',), freq=4),
    Q('navigation', 'show me my connections', None, 'They are here: [Connections](#connector=).', 'link:#connector', tools=('connections.list', 'pages'), freq=3),
    Q('navigation', 'take me to the AP ageing report', None, find('AP ageing report'), 'link:#msg=10', freq=3),
    Q('navigation', f'open {T4}', 'todo', f'Here: [{T4}](#task=4).', 'link:#task=4', tools=('pages',), freq=5),
    Q('navigation', 'open the invoice 88213 task', 'todo', [c('tasks.list', contains='invoice 88213'), f'That is [{T4}](#task=4).'], 'read:tasks.list', freq=4),
    Q('navigation', "pull up Marcus's month-end close", None, [c('tasks.list', contains='month-end close'), f'That is [{T1}](#task=1).'], 'read:tasks.list', freq=4),
    Q('navigation', 'where do I set up the AI?', None, 'Under [Connections → AI](#settings=config&group=How%20mail%20is%20sorted).', 'link:#settings', tools=('pages',), freq=3),
    Q('navigation', 'open the agent profiles', None, 'Here: [Profiles](#profiles).', 'link:#profiles', tools=('pages',), freq=2),
    Q('navigation', 'show me the workflows', None, 'Here: [Workflows](#report=workflows).', 'link:#report=workflows', tools=('pages',), freq=2),
    Q('navigation', 'go to reports', None, 'Here: [Reports](#report=reports).', 'link:#report=reports', tools=('pages',), freq=4),
    Q('navigation', 'show me my dashboards', None, 'Here: [Dashboards](#report=dashboards).', 'link:#report=dashboards', tools=('pages',), freq=3),
    Q('navigation', 'go to the memory page', None, 'Here: [LEARNED.md](#settings=docs&doc=learned).', 'link:#settings=docs&doc=learned', tools=('pages',), freq=2),
    Q('navigation', 'open the GitHub connection', None, 'Here: [GitHub](#connector=github).', 'link:#connector=github', tools=('pages',), freq=2),
    Q('navigation', 'show me the new starter task', None, [c('tasks.list', contains='new starter'), 'That is [TQ-0002](#task=2).'], 'read:tasks.list', freq=3),
    Q('navigation', 'bring up the census sync bug', None, [c('tasks.list', contains='census sync'), f'That is [{T12}](#task=12).'], 'read:tasks.list', freq=3),
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
    Q('item', 'reply to this', 'todo', c('reply'), 'draft:reply', freq=5),
    Q('item', 'tell Marcus I will look at it this afternoon', 'todo', c('reply', text='I will look at it this afternoon'), 'draft:reply', freq=5),
    Q('item', 'reply and loop Priya in', 'todo', c('reply', cc=['Priya Shah']), 'draft:reply', freq=3),
    Q('item', 'send it', 'review', c('approve'), 'light:approve', freq=5),
    Q('item', 'redraft it shorter', 'review', c('redraft', text='shorter'), 'draft:redraft', freq=4),
    # THE ASSISTANT MAY START AN AGENT (the owner, 2026-11-02: "why can't assistant start an agent. i'm okay with that. it itself should not be
    # the agent"): the words press the row's own Send to agent - the task page's start, dispatch.prepare's road
    Q('item', 'send this to an agent', 'todo', c('regular_agent', text='find the 4,180 gap in the month-end close'), 'did:dispatch.prepare', freq=4),
    Q('item', 'hand this to a coding agent', 'coding', c('coding_agent', text='fix the census sync'), 'did:dispatch.prepare', freq=4,
      note='the demo world has no coding CLI, so a coding hand-off is the one Send to agent (coding needs a CLI)'),
    Q('item', 'start it', 'todo', c('regular_agent'), 'did:dispatch.prepare', freq=4),
    Q('item', 'go ahead and have an agent work on it', 'todo', c('dispatch.prepare', ref=T1, kind='general'), 'did:dispatch.prepare', freq=3),
    Q('item', 'remind me tomorrow', 'todo', c('task.defer', until='tomorrow 9am'), 'light:defer', freq=5),
    Q('item', 'remind me about this on friday at 2pm', 'todo', c('task.defer', until='friday 2pm'), 'light:defer', freq=4),
    Q('item', 'not ours', 'fyi', c('not_ours'), 'pressed:not_ours', freq=4),
    Q('item', 'this is not ours', 'todo', c('task.not_a_task'), 'pressed:remove', freq=3, note="a task's row has Not a task, not Not ours"),
    Q('item', 'change the priority to high', 'todo', c('task.update', priority='high'), 'light:priority', freq=3),
    Q('item', 'make this urgent', 'todo', c('task.update', priority='urgent'), 'light:priority', freq=3),
    Q('item', 'mark this done', 'todo', c('close'), 'pressed:close', freq=5),
    Q('item', 'done', 'todo', c('close'), 'pressed:close', freq=4),
    Q('item', 'close it, the bank feed reconciled', 'todo', c('task.complete', note='the bank feed reconciled'), 'pressed:close_note', freq=3),
    Q('item', 'assign it to me', 'todo', c('task.update', assignee='owner'), 'words', freq=2),
    Q('item', 'forward this to Priya', 'todo', c('task.handoff', who='Priya Shah'), 'light:forward', freq=3),
    # SENT ON TO A PERSON, IN WORDS (the owner, 2026-11-03: "This should be sent to <an address>" right after Should be a task did nothing and
    # said to forward it from their own mail): Hand it to a person comes up with the address in its To - on a task, and on an FYI, whose
    # task it makes first. An address nobody here has written from is still an address
    Q('item', 'send this to gail@vendor.example', 'todo', c('task.handoff', who='gail@vendor.example'), 'hand:gail@vendor.example', freq=4),
    Q('item', 'send this to gail@vendor.example', 'fyi', c('task.handoff', who='gail@vendor.example'), 'hand:gail@vendor.example', freq=4),
    Q('item', 'forward this to Gail', 'todo', c('task.handoff', who='Gail Moreno'), 'hand:Gail Moreno', freq=4),
    Q('item', 'forward this to Gail', 'fyi', c('task.handoff', who='Gail Moreno'), 'hand:Gail Moreno', freq=4),
    Q('item', 'this should go to Ray', 'todo', c('task.handoff', who='Ray Colton', note='Yours to take from here.'), 'hand:Ray Colton', freq=3),
    Q('item', 'this should go to Ray', 'fyi', c('task.handoff', who='Ray Colton'), 'hand:Ray Colton', freq=3),
    # ...and the row's own id, which the canvas lists it by: forward was no tool, and the turn dropped it with nothing said
    Q('item', 'hand it to gail@vendor.example', 'todo', c('forward', who='gail@vendor.example'), 'hand:gail@vendor.example', freq=2),
    Q('item', 'ask Marcus which account it is', 'todo', c('task.clarify', text='Which account is short?'), 'light:reply', freq=3),
    Q('item', 'put it on my list', 'fyi', c('mine'), 'light:mine', freq=3),
    Q('item', 'next', 'todo', c('next'), 'next', freq=5),
    Q('item', 'skip this one', 'todo', c('next'), 'next', freq=4),
    # ...and with nothing on the table the walk words bring the first row up as its card - never a task read out in words, and a later
    # "mark this done" over no card brings the named one up lit, never closes it (the 2026-10-26 sweep)
    Q('item', 'walk me through my tasks', None, c('next'), 'card', freq=5),
    Q('item', 'start over', None, c('next'), 'card', freq=3),
    Q('item', 'mark this done', None, c('close', on=T1), 'light:close', freq=3),
    Q('item', 'remember that Marcus owns the bank feed', 'todo', c('remember', text='Marcus owns the bank feed'), 'did:memory.remember', freq=2),
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
    Q('question', "what's waiting on me", None, [c('pipe.list'), 'Ten things are on you.'], 'read:pipe.list', freq=5),
    Q('question', 'what is this about?', 'todo', [c('task.read', ref=T1), 'The month-end close is short by 4,180.'], 'read:task.read', freq=5),
    Q('question', 'what did Priya ask?', None, [c('sender.read', who='Priya Shah'), 'She asked about the new starter.'], 'read:sender.read', freq=4),
    Q('question', 'when is my next meeting?', None, [c('calendar.read', **{'from': 'today'}), 'The AP cutover dry run.'], 'read:calendar.read', freq=4),
    Q('question', f'what did the agent do on {T6}?', None, [c('task.read', ref=T6), 'It reconciled most of the export.'], 'read:task.read', freq=4),
    Q('question', 'what is on my calendar tomorrow', None, [c('calendar.read', **{'from': 'tomorrow'}), 'Nothing yet.'], 'read:calendar.read', freq=4),
    Q('question', 'did I miss anything?', None, [c('missed.check'), 'Nothing slipped.'], 'read:missed.check', freq=4),
    Q('question', 'anything urgent?', None, [c('pipe.list'), 'Nothing is marked urgent.'], 'read:pipe.list', freq=4),
    Q('question', 'what failed today?', None, [c('errors.list', days=1), 'Nothing failed.'], 'read:errors.list', freq=3),
    Q('question', 'find the mail about the Q3 numbers', None, [c('timeline.search', contains='Q3 numbers'), 'Sam asked for them.'], 'read:timeline.search', freq=4),
    Q('question', 'what drafts are waiting for my yes?', None, [c('approvals.list'), 'Five drafts wait.'], 'read:approvals.list', freq=3),
    Q('question', 'what do you remember about me?', None, [c('memory.list'), 'Nothing yet.'], 'read:memory.list', freq=2),
    Q('question', 'how many open tasks do I have', None, [c('tasks.list'), 'Fourteen.'], 'read:tasks.list', freq=3),
    Q('question', 'why did I never see the vendor portal notices', None, [c('rules.list', about='vendor portal'), 'No rule filters them.'], 'read:rules.list', freq=2),
    Q('question', 'how do I set up a report?', None, [c('docs.search', query='set up a report'), 'Press New, then Report.'], 'read:docs.search', freq=3),
    Q('question', "what's the PO approval limit here", None, [c('knowledge.search', query='PO approval limit'), 'Nothing written down about it.'], 'read:knowledge.search', freq=2),
    Q('question', 'what did I do yesterday', None, [c('activity.list', days=2), 'You closed six.'], 'read:activity.list', freq=2),
    Q('question', 'what did I ask you to do this week', None, [c('asks.list', status='all'), 'Two asks.'], 'read:asks.list', freq=2),
    Q('question', 'who is Ruth Bennett', None, [c('sender.read', who='Ruth Bennett'), 'She writes about the AP cutover.'], 'read:sender.read', freq=2),
    # ── the memory, read and corrected in words (slice 7 of the memory redesign, approved 2026-10-25) ──
    Q('memory', "who's Gail to me", None, [c('memory.about', who='Gail'), 'Nothing in the memory about her yet.'], 'read:memory.about', freq=3),
    Q('memory', 'Gail moved to Ops', None, c('memory.remember', note='Gail Moreno moved to Ops', about='gail@northwind.example'), 'did:memory.remember', freq=2),
    Q('memory', 'forget that Ray does payroll', None, [c('memory.about', who='Ray'), 'Nothing in the memory says that about Ray.'], 'read:memory.about', freq=2,
      note='the demo world has learned nothing yet; the closing and forgetting itself is tests/test_memory_edit.py'),
    Q('question', 'summarize my day', None, [c('pipe.list'), 'Ten on you; two meetings.'], 'read:pipe.list', freq=4),
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
    Q('agents', f'start an agent on {T12}', None, c('dispatch.prepare', ref=T12, kind='coding'), 'light:regular_agent', freq=3,
      note='a task not in front of the owner comes up with its Send to agent lit, as a put-down off the table does'),
    # A NEW PROMPT FOR THE AGENT AT WORK (the owner, 2026-11-02: "send a new prompt into the general/coding agent"): Tell the agent's road
    Q('agents', 'tell the agent to use the main branch', 'todo', c('agent.tell', text='use the main branch'), 'did:agent.tell', freq=4, live=1),
    Q('agents', 'also have it check the March file', 'todo', c('agent.answer', text='also check the March file'), 'did:agent.tell', freq=3, live=1,
      note='an answer to an agent that asked nothing is its next prompt, never "nothing on it is waiting for an answer"'),
    Q('agents', 'tell the agent to skip the empty rows', 'todo', c('answer_agent', text='skip the empty rows'), 'did:agent.tell', freq=3, live=1),
    Q('agents', 'tell the agent to use the main branch', 'todo', [c('agent.tell', text='use the main branch'),
      'No agent is working on TQ-0001 - Send to agent starts one.'], 'words', freq=2, note='nobody at work: said, nothing queued'),
    Q('agents', 'start a researcher on what Payworth charges per seat', None,
      c('task.create_from_text', kind='general', text='what Payworth charges per seat', title='Payworth seat price'), 'press:new', freq=3),
    Q('agents', 'research what Payworth charges per seat', None, c('task.create_from_text', kind='general', text='research what Payworth charges per seat', title='Payworth seat price'), 'new:agent:general', freq=3),
    Q('agents', 'have a coding agent fix the census sync timeout', None, c('task.create_from_text', kind='coding', text='fix the census sync timeout', title='Census sync timeout'), 'new:agent', freq=3, note='no coding CLI in the demo world: written into New as an agent job'),
    Q('agents', 'kill all the agents', None, c('agents.stop', all=True), 'words', freq=1, note='none running in the demo world: said, nothing pressed'),
    # ── reports ──
    Q('reports', 'run the end of day report', None, c('report.run', title='End of day checkup'), 'open:#report=', freq=4),
    Q('reports', 'run the AP ageing again', 'report', c('rerun'), 'open:#report=', freq=3),
    Q('reports', 'pause the headcount report', None, c('report.pause', title='Headcount by site'), 'open:#report=', freq=2),
    Q('reports', 'every monday send me the overdue invoices', None, c('setup', text='every monday send me the overdue invoices'), 'new:report', sort={'kind': 'report'}, freq=3),
    Q('reports', 'what did the helpdesk report say?', None, [c('report.read', title='Helpdesk tickets'), 'Fourteen rows.'], 'read:report.read', freq=3),
    Q('reports', 'list my reports', None, [c('reports.list'), 'Five reports.'], 'read:reports.list', freq=2),
    Q('reports', 'delete the headcount report', None, c('report.delete', title='Headcount by site'), 'open:#report=', freq=1),
    Q('reports', 'make the AP ageing daily', None, c('report.edit', title='AP ageing', config={'daily_at': '08:00'}), 'open:#report=', freq=2),
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
    Q('typos', 'mark tihs done', 'todo', c('close'), 'pressed:close', freq=3),
    Q('typos', 'whats waitng on me', None, [c('pipe.list'), 'Ten things.'], 'read:pipe.list', freq=3),
    Q('typos', 'opne settigns', None, 'Here: [Settings](#settings=config).', 'link:#settings', tools=('pages',), freq=2),
    Q('typos', 'repyl to marcus', 'todo', c('reply'), 'draft:reply', freq=3),
    # ── WhatsApp-style short replies ──
    Q('short', 'yes', 'review', c('approve'), 'light:approve', freq=5),
    # a digit names a numbered chip only where numbered chips are drawn - a card under its line; a task drawn as its own view has none,
    # and "2" there pressed a Mark done that was not on screen (2026-10-26): the model reads it as typed
    Q('short', '2', 'fyi', 'Ok.', 'words', tools=('digit',), freq=4),
    Q('short', '3', 'todo', 'Which one do you mean?', 'words', tools=('digit',), freq=3),
    Q('short', 'skip', 'todo', c('next'), 'next', freq=4),
    Q('short', 'no', 'review', 'Then it stays as drafted - nothing is sent.', 'words', tools=('words',), freq=4),
    Q('short', 'ok', 'todo', 'Ok.', 'words', tools=('words',), freq=4),
    Q('short', 'later', 'todo', c('task.defer', until='tomorrow 9am'), 'light:defer', freq=3),
    Q('short', 'k', 'todo', 'Ok.', 'words', tools=('words',), freq=2),
    Q('short', '👍', 'todo', 'Ok.', 'words', tools=('words',), freq=3),
    Q('short', 'done.', 'todo', c('close'), 'pressed:close', freq=4),
]

BRING_UP = [
    ('turn off the sound', 'sound', '#settings=config&group=Notifications&key=hand_sound'),
    ('where do I change my signature', 'signature', '#settings=config&group=Replies&key=email_signature'),
    ('the sync interval', 'sync interval', '#settings=config&group=Sync%20%26%20startup&key=poll_minutes'),
    ('desktop notifications', 'desktop notification', '#settings=config&group=Notifications&key=hand_desktop'),
    ('which AI sorts my mail', 'AI that sorts your mail', '#settings=config&group=How%20mail%20is%20sorted&key=triage_ai'),
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
    # ...a report by its newest run, as a Search pick opens it - read or not (the owner, 2026-11-03: "open the report should open the report like
    # search"); one that never ran, by its page
    ('the AP ageing report', 'AP ageing', '#msg=10'),
    ('the end of day report', 'end of day', '#report=2'),
    ('the headcount report', 'headcount', '#msg=9'),
    ('open the report about Kesler Medical', 'Kesler Medical', '#msg=10'),
    ('my routines', 'routines', '#report=workflows'),   # the shelf's name since 2026-10-29
    ('my SOUL doc', 'soul', '#settings=docs&doc=soul'),
    ('what it learned', 'learned', '#settings=docs&doc=learned'),
    ('the audit log', 'audit log', '#settings=audit'),
    ('agent profiles', 'profiles', '#profiles'),
    ('the mail rules', 'mail rules', '#settings=policies'),
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
CASES += [Q('bring-up', t, None, find(q), f'link:{h}', freq=4) for t, q, h in BRING_UP]
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
    Q('phone', 'mark this done', 'todo', c('close'), 'proposal:task.complete', freq=4, phone=True),
    Q('phone', 'remind me tomorrow', 'todo', c('task.defer', until='tomorrow 9am'), 'now:task.defer', freq=4, phone=True),
    Q('phone', 'send it', 'review', c('approve'), 'proposal:review.approve', freq=4, phone=True),
    Q('phone', 'reply to this', 'todo', c('reply'), 'draft:reply', freq=4, phone=True),
    Q('phone', 'tell the agent to use the main branch', 'todo', c('agent.tell', text='use the main branch'), 'did:agent.tell', freq=3, phone=True, live=1),
    Q('phone', 'have an agent find what Payworth charges per seat', None,
      c('task.create_from_text', kind='general', text='what Payworth charges per seat', title='Payworth seat price'), 'proposal:task.create_from_text',
      freq=3, phone=True, note='runs at once on the words (auto) - only a coding job with its checkout still to pick waits'),
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

# THE PAGE THE OWNER HAS UP (pageview.py, the owner 2026-10-30: "the assistant should be able to interact directly with the current view or
# page"): a box filled, a button pressed through the page's own handlers - never an outward Send (pointed at instead) and never a secret
IMAP = {'area': 'connections', 'title': 'the IMAP mailbox card (Connections)', 'item': {'kind': 'connector', 'id': 3, 'title': 'IMAP mailbox'},
        'fields': [{'key': 'host', 'label': 'IMAP server', 'value': ''}, {'key': 'user', 'label': 'Username', 'value': ''},
                   {'key': 'Secret', 'label': 'App password', 'value': '', 'secret': True, 'state': 'empty'}],
        'buttons': [{'id': 'test', 'label': 'Test'}, {'id': 'save', 'label': 'Save'}]}
TASKPAGE = {'area': 'task', 'item': {'kind': 'task', 'id': 4, 'ref': T4, 'title': 'Invoice 88213 - past due'},
            'fields': [{'key': 'draft', 'label': 'Reply draft', 'value': 'Hi Marcus - paid today.'}],
            'buttons': [{'id': 'row:close', 'label': 'Mark done'}, {'id': 'row:approve', 'label': 'Send'}, {'id': 'row:defer', 'label': 'Remind me'}]}
SETTINGSPAGE = {'area': 'settings', 'title': 'Settings', 'fields': [{'key': 'poll_minutes', 'label': 'Check mail every (minutes)', 'value': '5'}],
                'buttons': [{'id': 'save', 'label': 'Save'}]}
def v(**o): return 'VIEW: ' + json.dumps(o)
POWERS = [
    Q('page', 'fill in imap.zoho.com as the server', None, ['Filled in the server.\n' + v(op='set', field='host', value='imap.zoho.com')], 'view:set:host',
      tools=('words',), view=IMAP, freq=4),
    Q('page', 'test it', None, [v(op='press', button='test')], 'view:press:test', tools=('words',), view=IMAP, freq=4),
    Q('page', 'put my password in: hunter2', None, ['Your password is yours to paste into its box - I never type a secret.'], 'words', tools=('words',), view=IMAP,
      freq=2, note='a secret is never set, whatever the owner typed'),
    Q('page', 'send it', None, ['Send is yours to press.\n' + v(op='press', button='row:approve')], 'view:point', tools=('words',), view=TASKPAGE, freq=4,
      note='an outward send pressed by the model comes back a point: the real button lit for the owner'),
    Q('page', 'mark it done', None, [v(op='press', button='row:close')], 'view:press:row:close', tools=('words',), view=TASKPAGE, freq=4),
    Q('page', 'make it check every 15 minutes and save', None, [v(op='set', field='poll_minutes', value='15') + '\n' + v(op='press', button='save')],
      'view:press:save', tools=('words',), view=SETTINGSPAGE, freq=2),
    # ── troubleshooting: Taskuary itself, read and repaired inline (the inline troubleshooter, 2026-10-23) ──
    Q('troubleshoot', "whatsapp isn't working", None, [c('app.health', name='whatsapp'), 'WhatsApp is not connected - its card has the QR to scan.'],
      'read:app.health', freq=4),
    Q('troubleshoot', 'my outlook stopped syncing', None, [c('app.health', name='outlook'), 'Work mail synced a few minutes ago; nothing is failing.'],
      'read:app.health', freq=4),
    Q('troubleshoot', 'sync my work mail now', None, [c('app.repair', name='Work mail', how='sync'),
      'The sync did not fix it - Work mail still needs its sign-in on its card.'], 'read:app.repair', freq=3),
    Q('troubleshoot', 'is everything working?', None, [c('app.health'), 'Nothing is failing.'], 'read:app.health', freq=3),
    Q('troubleshoot', 'what broke overnight', None, [c('errors.list', days=1), 'Nothing failed overnight.'], 'read:errors.list', freq=2),
    # ── Taskuary's own tracker: a bug or a feature request drafted, scrubbed, the owner submits (report-a-bug, 2026-10-14) ──
    Q('feedback', 'taskuary crashed when I opened reports', None,
      [c('issue.draft', kind='bug', trying='open Reports', happened='the app crashed'), 'A bug report is drafted below - read it and press Submit on GitHub.'],
      'read:issue.draft', freq=3),
    Q('feedback', 'I wish taskuary could read my Teams calls', None,
      [c('issue.draft', kind='feature', trying='have Teams calls read', happened='there is no way to'), 'A feature request is drafted below for your Submit.'],
      'read:issue.draft', freq=2),
    Q('feedback', 'you need a Frobnitz connector, can you request it', None,
      [c('issue.draft', kind='feature', trying='connect Frobnitz', happened='there is no Frobnitz card'), 'A feature request is drafted below for your Submit.'],
      'read:issue.draft', freq=2,
      note='a missing connection is a feature request on GitHub (the owner, 2026-11-01)'),
    # ── help, and what changed (the help pages ship with the app; What's new, 2026-11-01) ──
    Q('help', "what's new in this version?", None, [c('docs.search', query="what's new"), 'This update reads its help without an add-on.'], 'read:docs.search', freq=3),
    Q('help', 'what changed in the last update', None, [c('docs.search', query='what changed'), 'The help pages ship with the app now.'], 'read:docs.search', freq=3),
    Q('help', 'how does Watch it work?', None, [c('docs.search', query='watch it'), 'The task stays open under Watching, still walked, until the thread moves.'],
      'read:docs.search', freq=2),
    Q('help', 'what is the Advisor?', None, [c('docs.search', query='advisor'), 'It lights the button it thinks you will press.'], 'read:docs.search', freq=2),
    # ── work that is an agent's, never done in the chat (the owner, 2026-11-01: "probably should have put agent on it") ──
    Q('agentwork', 'make me an image of the AP ageing as a bar chart', None,
      c('task.create_from_text', kind='general', text='a bar chart image of the AP ageing report', title='AP ageing chart'), 'new:agent:general', freq=3),
    Q('agentwork', 'write a spreadsheet of every vendor we paid last month', None,
      c('task.create_from_text', kind='general', text='a spreadsheet of every vendor paid last month', title='Vendors paid last month'), 'new:agent:general', freq=3),
    Q('agentwork', 'where is the spreadsheet the agent made?', None, [c('outputs.find', query='spreadsheet', kind='xlsx'), 'No agent has made one yet.'],
      'read:outputs.find', freq=3),
    Q('agentwork', 'stop all the agents', None, c('agents.stop', all=True), 'did:agents.stop', freq=2, live=6),
    # ── the row's newer buttons, by the words for them ──
    Q('row', "watch this, it's Gail's problem", 'todo', c('task.watch'), 'light:watch', freq=4),
    Q('row', 'keep an eye on it until Paula answers', 'todo', c('task.watch', what='reply'), 'light:watch', freq=3),
    Q('row', 'this is a coding task', 'todo', c('task.set_kind', kind='coding'), 'light', freq=2),
    Q('row', 'it is a duplicate of TQ-0002', 'todo', c('task.merge', into='TQ-0002'), 'light', freq=2),
    Q('row', 'block this sender', 'fyi', c('block_sender'), 'light', freq=3),
    Q('row', 'archive this', 'fyi', c('message.archive'), 'pressed:not_ours', freq=3, note="an FYI's row files it with Not ours - its one way off the pipe"),
    Q('row', 'accept it', 'invite', c('accept_invite'), 'light:accept_invite', freq=3),
    Q('row', 'prepare me for this meeting', 'invite', [c('prepare'), 'Prepare comes with the meeting on your calendar - accept it first and it is there.'],
      'words', freq=3, note="Prepare is a calendar meeting's button; an invite's row has Accept, Decline and Propose"),
    Q('row', 'pause this report', 'report', c('report_off'), 'light', freq=2),
    # ── sets of mail, newer verbs ──
    Q('sets', 'dismiss the newsletters', 'todo', c('pipe.remove', select={'contains': 'newsletter'}), 'did:pipe.remove', freq=3),
    Q('sets', 'unsubscribe me from the newsletters', 'todo', [c('pipe.block', select={'contains': 'newsletter'}, how='unsubscribe'),
      'None of them has an unsubscribe link - say block them and their sender never reaches triage again.'], 'words', freq=2),
    Q('sets', 'block whoever sends the newsletters', 'todo', c('pipe.block', select={'contains': 'newsletter'}), 'did:pipe.block', freq=2),
    Q('sets', 'put the vendor portal mail on my list', 'todo', c('pipe.mine', select={'contains': 'vendor portal'}), 'did:pipe.mine', freq=2),
    # ── new things: a meeting, a dashboard, a routine ──
    Q('new', 'set up a meeting with Gail about the budget on friday', None, c('meeting.new', who=['Gail Moreno'], about='the budget', when='friday'),
      'go:#connector', freq=3, note='no calendar in the demo world: the card that connects one, as a button under the line'),
    Q('new', 'make me a dashboard of open tasks by person', None, c('setup', text='a dashboard of open tasks by person'), 'new:report',
      sort={'kind': 'report'}, freq=2),
    Q('new', 'walk me through setting up a report', None, c('script.start', name='set up a report'), 'new:report', freq=2),
    # ── people and the routing they teach ──
    Q('people', 'Erin is my manager', None, c('people.relate', who='Erin Blake', relation='manager'), 'did:people.relate', freq=3),
    Q('people', 'Ray owns payroll', None, c('people.relate', who='Ray Colton', owns='payroll'), 'did:people.relate', freq=3),
    Q('people', "jobs like this are mine, not an agent's", 'todo', c('routing.remember', field='kind', value='task'),
      'did:routing.remember', freq=2),
    # ── the app's own things, read and brought back ──
    Q('app', 'what did I delete recently?', None, [c('deleted.list'), 'Nothing removed in the last 30 days.'], 'read:deleted.list', freq=1),
    Q('app', 'bring back the headcount report', None, [c('deleted.restore', what='Headcount by site'), 'Nothing was deleted in the last 30 days - it is still under Reports.'],
      'words', freq=1, note='nothing deleted in the demo world: said'),
    Q('app', 'turn the GitHub connection back on', None, c('connection.resume', name='GitHub'), 'open:#connector=github', freq=2),
    Q('app', 'put the headcount report back on its schedule', None, c('report.resume', title='Headcount by site'), 'open:#report=', freq=2),
    Q('app', 'remove the vendor portal rule', None, [c('rule.change', about='vendor portal', how='remove'), 'There is no rule for the vendor portal to remove.'],
      'words', freq=1, note='the demo world has no rules: said'),
    Q('app', 'which repositories can agents work in?', None, [c('repos.list'), 'northwind/importers.'], 'read:repos.list', freq=2),
    Q('app', 'what notification settings are there?', None, [c('settings.list', group='Notifications'), 'Sound and desktop notifications.'],
      'read:settings.list', freq=2),
    Q('app', 'how is the Work mail connection set up?', None, [c('connection.read', name='Work mail'), 'Outlook, on.'], 'read:connection.read', freq=2),
    Q('app', 'show me the board', None, c('page.open', page='board'), 'open', freq=2),
    Q('app', 'search everything for 88213', None, c('page.open', page='search', query='88213'), 'open', freq=2),
    Q('app', 'save to the hub: the bank feed lags a day at month end', None,
      c('hub.publish', title='The bank feed lags a day at month end', body='Reconcile on the 2nd, not the 1st.'), 'open:#hub', freq=1,
      note="the Hub's Write one is the press (2026-11-02) - it was refused, and the model said a Hub with posts was not set up"),
    # ── the rest of the catalogue an owner says in passing ──
    Q('row', 'decline it', 'invite', c('decline_invite'), 'light:decline_invite', freq=3),
    Q('row', 'can we do thursday instead', 'invite', c('propose_time', text='thursday'), 'light:propose_time', freq=3),
    Q('row', 'triage this again', 'fyi', [c('message.retriage'), 'Triage already sorted this one as an FYI - Should be a task makes it one.'], 'words', freq=1,
      note="Sort it again is for a message triage could not sort; an FYI's row has none"),
    Q('row', 'make this a task', 'fyi', c('task.create_from_message', kind='task'), 'light:mine', freq=3),
    Q('row', 'put it in northwind/importers', 'coding', c('task.set_repo', repo='northwind/importers'), 'light', freq=1),
    Q('row', 'email what it found to gail@northwind.example', 'agent', c('task.share', who='gail@northwind.example'), 'light:share_result', freq=2,
      note="Email a summary is one of Share's ways now - Share comes up lit"),
    Q('app', 'what am I connected to?', None, [c('connections.list'), 'Work mail (Outlook).'], 'read:connections.list', freq=3),
    Q('app', 'only alert me on the AP ageing when there are over 10 rows', None,
      c('report.route', title='AP ageing', line='alert', how='rule', rule='count', count=10), 'open:#report=', freq=2),
    Q('people', 'that is wrong about Gail', None, [c('memory.about', who='Gail'), 'Nothing in the memory about Gail yet, so nothing to take out.'],
      'read:memory.about', freq=2),
    Q('app', 'set me up as an AP rep', None, c('role.apply', role='ap_rep'),
      'open:#profiles', freq=2, note="on the desk a role is Profiles' own Set up - its questions are asked there"),
]
CASES += POWERS

# THE TASK PAGE, ASKED ABOUT WHILE IT IS UP (the audit, 2026-11-02): Came from, the Agent section, Close out, the action row, the to-dos, the
# notes, the draft - each ask typed with the task on the table AND its view sent, as the chat does (AssistantView: the table's key + context())
def _row(*vs): return [{'id': f'row:{v}', 'label': l} for v, l in vs]
def ticked_step(s):
    "The 4,180 step already ticked: an untick of an open step changes nothing, and the receipt says so (effects._changed)."
    s.tick_checklist_item(1, s.task_checklist(1)[1]['id'], True, 'owner')


TASK1V = {'area': 'task', 'title': f'{T1} - Month-end close is short by 4,180', 'item': {'kind': 'task', 'id': 1, 'ref': T1, 'title': 'Month-end close is short by 4,180'},
          'fields': [{'key': 'title', 'label': 'Title', 'value': 'Month-end close is short by 4,180'},
                     {'key': 'what_should_the_agent_do', 'label': 'What should the agent do?', 'value': ''}],
          'buttons': _row(('reply', 'Reply'), ('close', 'Mark done'), ('regular_agent', 'Send to agent'), ('defer', 'Remind me'), ('watch', 'Watch it'),
                          ('split', 'Split or merge'), ('share_result', 'Share'), ('forward', 'Hand it to a person'), ('remove', 'Not a task'),
                          ('close_note', 'Close with a note'))
                     + [{'id': 'show_where_this_came_from', 'label': 'Show where this came from'}, {'id': 'expand_to_the_whole_canvas', 'label': 'Expand to the whole canvas'}]}
TASK4V = {'area': 'task', 'title': f'{T4} - Invoice 88213 - past due', 'item': {'kind': 'task', 'id': 4, 'ref': T4, 'title': 'Invoice 88213 - past due'},
          'fields': [{'key': 'title', 'label': 'Title', 'value': 'Invoice 88213 - past due'},
                     {'key': 'draft', 'label': 'Reply draft', 'value': 'Hi Tom - we recieved it and it is paid today.'}],
          'buttons': _row(('approve', 'Send'), ('redraft', 'Redraft'), ('close', 'Mark done'), ('defer', 'Remind me'), ('watch', 'Watch it'), ('attach', 'Attach a file'))}
TASK6V = {'area': 'task', 'title': f'{T6} - Reconcile the August GL export', 'item': {'kind': 'task', 'id': 6, 'ref': T6, 'title': 'Reconcile the August GL export'},
          'fields': [{'key': 'title', 'label': 'Title', 'value': 'Reconcile the August GL export'}],
          'buttons': _row(('stop_agent', 'Stop and save'), ('close', 'Mark done'), ('defer', 'Remind me'), ('watch', 'Watch it'))}
AREA_TASK = [
    # ── questions about the task on screen: its facts ride the turn, or task.read reads the whole story ──
    Q('task', 'what is this task about?', 'todo', [c('task.read', ref=T1), 'Marcus says the month-end close is short by 4,180.'], 'read:task.read', view=TASK1V, freq=5),
    Q('task', 'who sent this?', 'todo', 'Marcus Reed.', 'words', tools=('words',), view=TASK1V, freq=4),
    Q('task', 'where did this come from', 'todo', ['From a mail from Marcus.\n' + v(op='press', button='show_where_this_came_from')],
      'view:press:show_where_this_came_from', tools=('words',), view=TASK1V, freq=3, note="Came from is a fold on the page: its own button opens it"),
    Q('task', 'what did the agent do on this?', 'agent', [c('task.read', ref=T6), 'It is reconciling the export now.'], 'read:task.read', view=TASK6V, freq=4, live=6),
    # ── the row's buttons, by the owner's words for them ──
    Q('task', 'remind me about this on monday', 'todo', c('task.defer', until='monday 9am'), 'light:defer', view=TASK1V, freq=5),
    Q('task', 'remnd me tomorow', 'todo', c('task.defer', until='tomorrow 9am'), 'light:defer', view=TASK1V, freq=3, note='a misspelling: the model reads it'),
    Q('task', 'watch it till marcus answers', 'todo', c('task.watch', what='reply'), 'light:watch', view=TASK1V, freq=4),
    Q('task', 'close it out with a note: the bank fixed the feed', 'todo', c('task.complete', note='the bank fixed the feed'), 'pressed:close_note', view=TASK1V,
      freq=3, tools=('task.complete',)),
    Q('task', "this isn't a task", 'todo', c('task.not_a_task'), 'pressed:remove', view=TASK1V, freq=3),
    Q('task', 'make this urgent', 'todo', c('task.update', priority='urgent'), 'light:priority', view=TASK1V, freq=3),
    Q('task', 'split this into two jobs', 'todo', c('task.split', text='the bank feed; the 4,180 gap'), 'light:split', view=TASK1V, freq=2),
    Q('task', 'this is the same as TQ-0004, merge them', 'todo', c('task.merge', into=T4), 'light:split', view=TASK1V, freq=2),
    Q('task', 'hand this to Paula', 'todo', c('task.handoff', who='Paula Vance'), 'light:forward', view=TASK1V, freq=3),
    Q('task', 'share this with erin@northwind.example', 'todo', c('task.share', who='erin@northwind.example'), 'light:share_result', view=TASK1V, freq=2),
    Q('task', 'reply to marcus saying we are looking into it', 'todo', c('reply', text='we are looking into it'), 'draft:reply', view=TASK1V, freq=4),
    # ── the Agent section: Send to agent with the job in its box, pressed for the owner (2026-11-02); a live one stopped ──
    Q('task', 'get an agent to find the 4,180', 'todo', c('regular_agent', text='find the 4,180 gap in the month-end close'), 'did:dispatch.prepare', view=TASK1V, freq=4),
    Q('task', 'put "reconcile against the bank statement" in the agent box and start it', 'todo',
      [v(op='set', field='what_should_the_agent_do', value='reconcile against the bank statement') + '\n' + v(op='press', button='row:regular_agent')],
      'view:press:row:regular_agent', tools=('words',), view=TASK1V, freq=2, note='Send to agent starts work here and sends nothing out: pressed, not pointed'),
    Q('task', 'stop the agent', 'agent', c('agent.stop'), 'light:stop_agent', view=TASK6V, freq=3, live=6),
    Q('task', 'send this to the coding agent', 'coding', c('coding_agent', text='fix the census sync when a site has no manager'), 'did:dispatch.prepare',
      freq=3, note="the Agent section's one Send to agent starts either kind"),
    Q('task', 'continue the agent', 'agent', [c('agent.continue'), 'There is no saved session on TQ-0006 to pick up - Send to agent starts a new one.'], 'words',
      view=TASK6V, freq=3, note='no saved session: said, and what starts one - never "name the task" over the task on screen'),
    Q('task', 'tell the agent to use the main branch', 'agent', c('agent.answer', text='use the main branch'), 'did:agent.tell', view=TASK6V, live=6, freq=2,
      note='an agent at work is not waiting on an answer: the words are its next prompt, Tell the agent\'s road (the owner, 2026-11-02)'),
    Q('task', 'change who does this to me', 'todo', c('task.set_kind', kind='task'), 'light:change_kind', view=TASK1V, freq=2),
    Q('task', 'expand this', 'todo', [v(op='press', button='expand_to_the_whole_canvas')], 'view:press:expand_to_the_whole_canvas', tools=('words',), view=TASK1V, freq=2),
    # ── the to-dos and the notes: the task page's own writes, run and said ──
    Q('task', 'tick of the first step', 'todo', c('task.check', item='1'), 'did:task.check', view=TASK1V, freq=4, note='a misspelling: the model reads it'),
    Q('task', 'untick find the 4,180', 'todo', c('task.check', item='2', done=False), 'did:task.check', view=TASK1V, freq=2, seed=ticked_step),
    Q('task', 'add a step: email the bank', 'todo', c('task.checklist', add=['email the bank']), 'did:task.checklist', view=TASK1V, freq=4),
    Q('task', 'add a note: Paula is checking the bank feed', 'todo', c('task.comment', text='Paula is checking the bank feed'), 'did:task.comment', view=TASK1V, freq=4),
    Q('task', 'set the due date to friday', 'todo', c('task.update', due='friday'), 'did:task.update', view=TASK1V, freq=3),
    Q('task', 'rename this to Month-end close - bank feed gap', 'todo', [v(op='set', field='title', value='Month-end close - bank feed gap')], 'view:set:title',
      tools=('words',), view=TASK1V, freq=2),
    # ── the draft under Close out: fixed in its box, redrafted, its Send lit for the owner ──
    Q('task', 'fix the typo in the draft', 'review', ['Fixed "recieved".\n' + v(op='set', field='draft', value='Hi Tom - we received it and it is paid today.')],
      'view:set:draft', tools=('words',), view=TASK4V, freq=3),
    Q('task', 'redraft it shorter', 'review', c('redraft', text='shorter'), 'draft:redraft', view=TASK4V, freq=3),
    Q('task', 'cc gail on the reply', 'review', c('redraft', text='copy Gail Moreno'), 'draft:redraft', view=TASK4V, freq=2),
    Q('task', 'scrap the draft, no reply needed', 'review', c('close'), 'pressed:close', view=TASK4V, freq=3,
      note='a reply draft is never rejected (the owner, 2026-10-01): Mark done closes it with nothing sent'),
    Q('task', 'reject the draft', 'review', [c('review.reject'), c('redraft', text='write it again')], 'draft:redraft', view=TASK4V, freq=2,
      tools=('review.reject',), note="the miss names Redraft and Mark done, the draft's real ways out"),
    Q('task', 'ask tom when it was paid', 'review', c('task.clarify', text='When was it paid?'), 'light:reply', view=TASK4V, freq=2),
    Q('task', 'aprove and send', 'review', ['Send is yours to press.\n' + v(op='press', button='row:approve')], 'view:point:row:approve', tools=('words',),
      view=TASK4V, freq=4, note='a send is lit for the owner, never pressed'),
    Q('task', 'attach the invoice pdf', 'review', c('button.light', button='Attach a file'), 'light:attach', view=TASK4V, freq=2,
      note='a file picker is the owner\'s to fill: its button lit'),
    # ── how the page works: its help ──
    Q('task', 'wat does close out do', 'todo', [c('docs.search', query='close out'), 'Close out holds the reply and Mark done.'], 'read:docs.search', view=TASK1V, freq=2),
    Q('task', "why can't I see the agent section", 'todo', [c('docs.search', query='agent section task page'), 'It opens when an agent is on the task.'],
      'read:docs.search', view=TASK1V, freq=2),
]
CASES += AREA_TASK

# THE WORK RAIL AND ITS WALK (the rail audit, 2026-11-02; the owner: "test it all works ... to be able to help the user on every page"): Next
# and Back, a section by its heading, the FYI's All read, Watching, the Advisor's ideas and its habits row, sets put away or closed. The demo
# world has no watched task, idea or habit: each case that needs one seeds it (invented lines, nobody real)
T2 = 'TQ-0002'
def watched(s):
    from taskuary import funnel, watch
    watch.watch(s, 2); funnel.invalidate()
TEAM_GROUP = '120363000000000001@g.us'
def wa_group(s):
    "A connected WhatsApp with the team's group on its roster (wanames), never a chat Taskuary reads."
    from taskuary import wanames
    s.save_connector({'Type': 'whatsapp', 'Name': 'WhatsApp', 'Active': 1}, 't')
    s.set_setting(wanames.KEY, json.dumps({TEAM_GROUP: 'Northwind team'}), 't')
def habits_row(s):
    "Two habits on the one row: one the Advisor adopted, one it asks about (habits.tick, as tests/test_habits_row.py builds it)."
    from datetime import datetime
    from taskuary import funnel, habits, learn, learnedgraph as lg
    day = datetime.now().strftime('%Y-%m-%d')
    ln = lambda k, t, sc, ev: lg.fmt({'key': k, 'text': t, 'ev': ev, 'score': sc, 'seen': day, 'status': 'proposed'})
    doc = s.get_doc('learned') or '# LEARNED\n'
    if learn.PROP_START not in doc: doc += f"\n## Proposed rules — your call\n{learn.PROP_START}\n{learn.PROP_END}\n"
    add = '\n'.join([ln('sso threads', '{{owner_first}} closes sign-in help threads directly; they need no drafted reply', 12, [f'rv{i}' for i in range(1, 9)]),
                     ln('fwd fyi', 'Forwarded FYI mail from the facilities team needs no reply', 5, ['rv20', 'rv21'])])
    s.save_doc('learned', doc.replace(learn.PROP_END, add + '\n' + learn.PROP_END), 'reflect')
    habits.tick(s); funnel.invalidate()
    return f"idea:{s._one('SELECT * FROM idea WHERE Key=?', (habits.KEY,))['IdeaId']}"
def idea_row(s):
    from datetime import datetime
    from taskuary import funnel
    i = s.upsert_idea({'key': 'idea:weekly-ledger', 'kind': 'idea', 'sig': 'y', 'text': 'The ledger reconciliation repeats monthly - worth automating.',
                       'action': {}}, datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    funnel.invalidate(); return f"idea:{i['IdeaId']}"
def meeting_row(s):
    "A meeting coming up in 40 minutes, on a calendar the demo world lacks (`agenda`, read by _guards) - invented people."
    from datetime import datetime, timedelta
    from taskuary import funnel
    at = lambda m: (datetime.now() + timedelta(minutes=m)).strftime('%Y-%m-%dT%H:%M:%S')
    s.agenda = [{'subject': 'Ledger cut-over plan', 'start': at(40), 'end': at(70), 'who': ['Gail Moreno', 'Paula Vance'], 'where': 'Teams',
                 'about': 'Which entities move first', 'join': 'https://meet.northwind.example/cutover', 'all_day': False, 'id': 'ev-cutover'}]
    funnel.invalidate(); return f"meeting:{at(40)[:16]}:Ledger cut-over plan"
AREA_RAIL = [
    Q('rail', 'whats nxt', 'todo', c('next'), 'next', freq=4),
    Q('rail', 'go back to the one before', 'todo', c('button.light', button='back'), 'card', freq=4,
      note='Back is the walk bar\'s press beside Next - it was refused "has no Back button"'),
    Q('rail', 'walk me through the reports', None, c('next', section='Reports'), 'card', freq=3, note="the heading's own press (railwalk.section)"),
    Q('rail', 'start me on the fyi', 'todo', c('next', section='FYI'), 'card', freq=3),
    Q('rail', 'go through the advisor ideas', None, c('next', section='Advisor'), 'words', freq=2, note='none in the demo world: said so'),
    Q('rail', 'all read on the fyi please', 'fyi', c('pipe.clear', select={'kind': 'fyi'}), 'cleared', freq=4),
    Q('rail', 'mark the reports read', 'report', c('pipe.clear', select={'category': 'report'}), 'cleared', freq=4),
    Q('rail', 'how many fyis do I have', None, [c('pipe.list'), 'Four FYI wait.'], 'read:pipe.list', freq=3),
    Q('rail', 'snooze all the fyi til monday', 'todo', c('pipe.defer', select={'kind': 'fyi'}, until='monday 9am'), 'did:pipe.defer', freq=3),
    Q('rail', 'put the reports away until tomorrow', 'todo', c('pipe.defer', select={'category': 'report'}, until='tomorrow 9am'), 'did:pipe.defer', freq=2),
    Q('rail', 'close everything for later', None, [c('pipe.close', select={'lane': 'later'}), 'Nothing is put away for later.'], 'words', freq=1,
      note='nothing For later in the demo world: said whole, never "Nothing waiting is , so"'),
    # ── Watching (watch.py): kept open for somebody else, walked after Tasks (the owner, 2026-11-02) ──
    Q('rail', 'what am I watching?', None, [c('tasks.list'), f'You are watching {T2}.'], 'read:tasks.list', freq=3, seed=watched),
    Q('rail', f'where did {T2} go', None, [c('task.read', ref=T2), 'You are watching it - it is under Watching, still in your walk.'], 'read:task.read',
      freq=2, seed=watched),
    Q('rail', f'stop watching {T2}', None, c('task.watch', what='off', ref=T2), 'light:watch', freq=3, seed=watched,
      note="the row's Watch it reads Stop watching while it watches - lit for the owner"),
    Q('rail', 'watch TQ-0002 for me', None, c('task.watch', ref=T2), 'light:watch', freq=3),
    Q('rail', 'close all the watched ones', None, [c('tasks.list'), c('pipe.close', select={'keys': [T2]})], 'did:pipe.close', freq=1, seed=watched),
    # ── the Advisor's rows: an idea, and the one habits row (habits.py) ──
    Q('rail', 'put the advisor idea on my list', 'idea', c('mine'), 'light:mine', freq=2, seed=idea_row),
    Q('rail', 'no more ideas like this', 'idea', c('not_ours_kind'), 'light:not_ours', freq=2, seed=idea_row,
      note="one of the idea's Not ours choices - it was refused as no button"),
    Q('rail', 'what habits did you learn about me?', 'habit', 'You close sign-in help threads yourself, so I will not draft replies to them.', 'words',
      tools=('words',), freq=2, seed=habits_row),
    Q('rail', 'adopt the one about forwarded fyi', 'habit', c('memory.wrong', key='fwd fyi', how='keep'), 'did:memory.wrong', freq=2, seed=habits_row,
      note='keep was no `how` - refused'),
    Q('rail', 'the sign-in one is not right', 'habit', c('memory.wrong', key='sso threads', how='wrong'), 'did:memory.wrong', freq=2, seed=habits_row),
    Q('rail', 'no to the fyi one', 'habit', c('memory.wrong', key='fwd fyi', how='wrong'), 'did:memory.wrong', freq=1, seed=habits_row),
    # ── a meeting coming up: Prepare and Send to agent on its row, the agent box's words leading (the owner, 2026-11-02) ──
    Q('rail', 'send this meeting to an agent to prep me - pull the open issues with these people', 'meeting',
      c('regular_agent', text='Prep me for this meeting: pull the open issues with Gail Moreno and Paula Vance'), 'did:task.create_from_text', freq=4, seed=meeting_row,
      note="the row's Send to agent, pressed with the owner's words; the meeting rides under them"),
    # ...and Prepare by words: the CALL was dropped as no decision at all (prepare was missing from concierge.VERBS) and the answer was "Ok."
    Q('rail', 'prepare me for this meeting', 'meeting', c('prepare'), 'did:calendar.prepare', freq=4, seed=meeting_row,
      note="the row's Prepare, pressed - an agent start the Assistant may make (2026-11-02)"),
    # ...while a job that is not about the meeting stays the model's call: `new` makes it a task of its own, written into New
    Q('rail', 'get an agent to research three expense tools', 'meeting', c('regular_agent', text='research three expense tools', new=True), 'new:agent',
      freq=2, seed=meeting_row, note='the model says the job is not the meeting\'s (`new`); code never decides that'),
    # ── about the rail itself ──
    Q('rail', 'why is this one at the top?', 'todo', [c('docs.search', query='work rail'), 'Rows sit in the order they arrived.'], 'read:docs.search', freq=2),
    Q('rail', 'what is the habits row', None, [c('docs.search', query='habits row'), 'One row for every habit the Advisor learned.'], 'read:docs.search', freq=1),
    Q('rail', 'my rail is empty, where did everything go?', None, [c('activity.list', days=1), 'You cleared them this morning.'], 'read:activity.list', freq=2),
    Q('rail', 'open the headcount report', None, find('headcount report'), 'link:#msg=9', freq=2),
    Q('rail', 'collapse the FYI section', None, 'The FYI heading folds with its own arrow - that press is yours.', 'words', tools=('words',), freq=1,
      note='folding a section is the page\'s own press; said honestly'),
]
CASES += AREA_RAIL

# THE CONNECTIONS PAGE, asked about while it is up (the audit, 2026-11-02): the catalogue's grid, a card being set up, a card connected -
# its boxes filled and its Test pressed on the page, a key never typed by the Assistant, a system with no card a request for one, a data
# card a report's (never the rail's), the AI and voice cards brought up, and the work that needs this computer an agent's
CONNGRID = {'area': 'connections', 'title': 'Connections', 'fields': [{'key': 'search_connectors', 'label': 'Search connectors', 'value': ''}],
            'buttons': [{'id': 'email', 'label': 'Email'}, {'id': 'messaging', 'label': 'Messaging'}, {'id': 'ai_agents_models', 'label': 'AI · agents & models'},
                        {'id': 'ai_voice', 'label': 'AI · voice'}, {'id': 'corporate_systems', 'label': 'Corporate systems'}, {'id': 'sync_now', 'label': 'Sync now'},
                        {'id': 'slack', 'label': 'Slack - channels and DMs through triage'}, {'id': 'gmail', 'label': 'Gmail - your Google mailbox'}]}
NOHIT = {**CONNGRID, 'fields': [{'key': 'search_connectors', 'label': 'Search connectors', 'value': 'Frobnitz'}],
         'buttons': CONNGRID['buttons'][:6] + [{'id': 'request_frobnitz', 'label': 'Request Frobnitz'}], 'text': 'Nothing matches Frobnitz in Connections.'}
SLACKCARD = {'area': 'connections', 'title': 'the Slack card (Connections)', 'item': {'kind': 'connector', 'id': 'slack', 'title': 'Slack'},
             'fields': [{'key': 'name', 'label': 'Name', 'value': 'Slack'}, {'key': 'Secret', 'label': 'Bot token (xoxb-…)', 'value': '', 'secret': True, 'state': 'empty'}],
             'buttons': [{'id': 'messaging', 'label': 'Messaging'}, {'id': 'save', 'label': 'Save'}, {'id': 'test', 'label': 'Test'}]}
FAILED = {**SLACKCARD, 'fields': [{**SLACKCARD['fields'][0]}, {**SLACKCARD['fields'][1], 'state': 'saved'}],
          'last': {'action': 'test', 'ok': False, 'detail': 'Slack answered invalid_auth'}}
WORKCARD = {'area': 'connections', 'title': 'the Work mail card (Connections)', 'item': {'kind': 'connector', 'id': 'outlook', 'title': 'Work mail'},
            'fields': [{'key': 'name', 'label': 'Name', 'value': 'Work mail'}, {'key': 'on', 'label': 'On', 'kind': 'switch', 'value': 'on'}],
            'buttons': [{'id': 'email', 'label': 'Email'}, {'id': 'rename', 'label': 'Rename'}, {'id': 'add_another_outlook', 'label': 'Add another Outlook'},
                        {'id': 'test', 'label': 'Test'}, {'id': 'sync_now', 'label': 'Sync now'}, {'id': 'remove_connection', 'label': 'Remove connection'}]}
def gen(text, title): return c('task.create_from_text', kind='general', text=text, title=title)
AREA_CONNECTIONS = [
    # ── the grid: what is here, what is on, finding a card ──
    Q('connections', 'what can I connect here?', None, ['Mail, chat, trackers, data for reports, and the AI and voice cards - pick a section above.'],
      'words', tools=('words',), view=CONNGRID, freq=3),
    Q('connections', 'which of these are connected?', None, [c('connections.list'), 'Work mail (Outlook) is on.'], 'read:connections.list', view=CONNGRID, freq=4),
    Q('connections', 'find zoho', None, [v(op='set', field='search_connectors', value='zoho')], 'view:set:search_connectors', tools=('words',), view=CONNGRID, freq=3),
    Q('connections', 'show me just the AI ones', None, [v(op='press', button='AI · agents & models')], 'view:press:ai_agents_models', tools=('words',),
      view=CONNGRID, freq=2),
    Q('connections', 'open the slack card', None, c('connection.create', type='slack'), 'open:#connector=slack&step=1', view=CONNGRID, freq=4),
    Q('connections', 'sync everything now', None, [v(op='press', button='Sync now')], 'view:press:sync_now', tools=('words',), view=CONNGRID, freq=2),
    # ── a card being set up: its boxes, its Save and Test - the key is the owner's to paste ──
    Q('connections', 'call it Team chat', None, ['Named it.\n' + v(op='set', field='Name', value='Team chat')], 'view:set:name', tools=('words',),
      view=SLACKCARD, freq=2),
    Q('connections', 'my bot token is xoxb-1111-2222-abcd, put it in', None, ['It goes in its box from you - I never type a key.\n'
      + v(op='set', field='Bot token (xoxb-…)', value='xoxb-1111-2222-abcd')], 'view:refused', tools=('words',), view=SLACKCARD, freq=3,
      note='the model reached for the secret box anyway: the server turns it down, and the token is never set'),
    Q('connections', 'save it and test it', None, [v(op='press', button='Save') + '\n' + v(op='press', button='Test')], 'view:press:test', tools=('words',),
      view=SLACKCARD, freq=4),
    Q('connections', 'why did the test fail', None, ['Slack turned the token down (invalid_auth) - paste a fresh Bot token and press Test.'], 'words',
      tools=('words',), view=FAILED, freq=4, note="the card's own Test answer rides the view (pageView.viewResult)"),
    Q('connections', 'walk me thru setting this up', None, ['Paste the Bot token from your Slack app into its box, then press Test.\n'
      + v(op='point', target='Bot token (xoxb-…)')], 'view:point:Secret', tools=('words',), view=SLACKCARD, freq=3,
      note="walked in words with its box lit - Get AI to set it up is the door into this chat, kept out of the view (ConnectorsView AiWalkButton)"),
    Q('connections', 'go back to all of them', None, [v(op='press', button='Messaging')], 'view:press:messaging', tools=('words',), view=SLACKCARD, freq=2,
      note="the card's back button says the section it came from"),
    Q('connections', 'list my slack channels', None, gen('list the Slack channels the bot token can see', 'Slack channels'), 'new:agent:general',
      view=SLACKCARD, freq=2, note='a token used on this computer is an agent job (pageview.GUIDE), never the chat'),
    # ── a card connected: on and off, rename, another of the kind, remove ──
    Q('connections', 'switch it off for now', None, [v(op='set', field='On', value='off')], 'view:set:on', tools=('words',), view=WORKCARD, freq=3),
    Q('connections', 'rename it to Office mail', None, [v(op='set', field='Name', value='Office mail') + '\n' + v(op='press', button='Rename')],
      'view:press:rename', tools=('words',), view=WORKCARD, freq=2),
    Q('connections', 'add a second outlook', None, [v(op='press', button='Add another Outlook')], 'view:press:add_another_outlook', tools=('words',),
      view=WORKCARD, freq=2),
    Q('connections', 'remove this connection', None, [v(op='press', button='Remove connection')], 'view:press:remove_connection', tools=('words',),
      view=WORKCARD, freq=2, note='the card keeps its Undo; nothing goes out'),
    # ── off the page: a card by name, its switch and its Test on its own page ──
    Q('connections', 'turn off work mail', None, c('connection.pause', name='Work mail'), 'open:#connector=outlook', freq=3),
    Q('connections', 'test my work mail', None, c('connection.test', name='Work mail'), 'open:#connector=outlook', freq=3),
    # ── troubleshooting a card ──
    Q('connections', 'gmial wont conect', None, [c('app.health', name='gmail'), 'Gmail is not set up yet - its card, under this, connects it.'],
      'read:app.health', freq=3, note='a misspelling: the model reads it'),
    Q('connections', 'is work mail syncing ok?', None, [c('app.health', name='Work mail'), 'Work mail synced a few minutes ago; nothing is failing.'],
      'read:app.health', view=WORKCARD, freq=3),
    # ── a system with no card: a request for one, the owner's to submit (the owner, 2026-11-01) ──
    Q('connections', 'connect Frobnitz', None, [c('connection.create', type='frobnitz'),
      c('issue.draft', kind='feature', trying='connect Frobnitz', happened='a card under Connections for Frobnitz'), 'There is no Frobnitz card - a request for one is drafted below for your Submit.'],
      'read:issue.draft', freq=2, note='the miss says a card the catalogue lacks is a feature request (concierge.call_turn, 2026-11-02)'),
    Q('connections', 'nothing for frobnitz - can you ask for it?', None, [v(op='press', button='Request Frobnitz')], 'view:press:request_frobnitz',
      tools=('words',), view=NOHIT, freq=2, note="the grid's own Request button, pressed: it opens the drafted request, nothing is filed"),
    # ── data cards feed reports, never the rail ──
    Q('connections', 'will quickbooks put bills on my task list?', None, [c('docs.search', section='help/connections > Data and report sources'),
      'No - a data card feeds reports, dashboards and agent look-ups; it never puts work on your list.'], 'read:docs.search', freq=2),
    Q('connections', 'make a report of my quickbooks bills over 30 days', None, c('setup', text='a report of QuickBooks bills over 30 days'), 'new:report',
      sort={'kind': 'report'}, freq=3),
    # ── the AI brains and voice ──
    Q('connections', 'set up claude as my ai', None, c('connection.create', type='anthropic'), 'open:#connector=anthropic&step=1', freq=3),
    Q('connections', 'use my chatgpt plan', None, c('connection.create', type='chatgpt'), 'open:#connector=chatgpt&step=1', freq=2),
    Q('connections', 'which ai answers you?', None, [c('agents.list'), 'The Assistant runs on the brain set under Settings.'], 'read:agents.list', freq=2),
    Q('connections', 'transcribe my voice notes on this computer', None, c('connection.create', type='local_whisper'), 'open:#connector=local_whisper&step=1',
      freq=2, note='the AI · voice cards: Local Whisper keeps audio on the machine'),
    Q('connections', 'how do voice notes get transcribed?', None, [c('docs.search', section='help/connections > Voice notes and dictation'),
      'A card under AI · voice does it; without one a voice note lands untranscribed with its audio.'], 'read:docs.search', freq=2),
]
CASES += AREA_CONNECTIONS

# REPORTS, DASHBOARDS AND ROUTINES, ON THEIR OWN PAGES (the everyday-asks audit, 2026-11-02): the shelf's rows wear Run now, Edit and a
# switch, each named for its report (ReportsView row); a routine's page and a dashboard's carry their own Run now - and since 2026-11-02 a
# report's builder too, its row's Run now and switch in its header (the owner): an act on the report whose page is up is pressed there
AP, HC, EOD = 'AP ageing over 30 days, weekly', 'Headcount by site, nightly', 'End of day checkup'
def _slug(t): return re.sub(r'[^a-z0-9]+', '_', t.lower()).strip('_')          # the page's own ids for what has no id (pageView.js slug)
def _row(t): return [{'id': f'run_now_{_slug(t)}', 'label': f'Run now: {t}'}, {'id': f'edit_{_slug(t)}', 'label': f'Edit: {t}'}]
REPORTSHELF = {'area': 'reports', 'title': 'Reports', 'fields': [{'key': 'describe', 'label': 'Describe the report you want', 'value': ''}]
               + [{'key': _slug(f'{t} on its clock'), 'label': f'{t} on its clock', 'kind': 'switch', 'value': 'on'} for t in (AP, HC, EOD)],
               'buttons': [{'id': 'run_due_now', 'label': 'Run due now'}, {'id': 'new_report', 'label': '+ New report'}] + _row(AP) + _row(HC) + _row(EOD)}
REPORTPAGE = {'area': 'reports', 'title': f'the report "{AP}" (Reports), its editor open', 'item': {'kind': 'report', 'id': 5},
              'fields': [{'key': 'title_the_headline_each_run_shows', 'label': 'title — the headline each run shows', 'value': AP},
                         {'key': 'describe', 'label': 'Describe the report you want', 'value': ''},
                         {'key': _slug(f'{AP} on its clock'), 'label': f'{AP} on its clock', 'kind': 'switch', 'value': 'on'}],
              'buttons': [{'id': 'run_now', 'label': 'Run now'}, {'id': 'remove_report', 'label': 'Remove report'}, {'id': 'pipeline', 'label': 'Pipeline'},
                          {'id': 'test_preview', 'label': 'Test & preview'}, {'id': 'test_source', 'label': 'Test source'},
                          {'id': 'preview_pipeline', 'label': 'Preview pipeline'}, {'id': 'continue', 'label': 'Continue'},
                          {'id': 'schedule_save', 'label': 'Schedule & save'}],
              'last': {'action': 'test', 'ok': False, 'detail': 'Login failed for user report_reader'}}
DASHPAGE = {'area': 'reports', 'title': 'the dashboard "Northwind desk" (Reports - Dashboards), drawn with its buttons',
            'fields': [{'key': 'describe', 'label': 'Describe the dashboard you want', 'value': ''}],
            'buttons': [{'id': 'save_dashboard', 'label': 'Save dashboard'}, {'id': 'run_now', 'label': 'Run now'}, {'id': 'remove', 'label': 'Remove'}]}
ROUTINEPAGE = {'area': 'reports', 'title': 'the routine "Month-end tie-out" (Routines), its steps open',
               'fields': [{'key': 'month_end_tie_out_on_its_clock', 'label': 'Month-end tie-out on its clock', 'kind': 'switch', 'value': 'on'}],
               'buttons': [{'id': 'run_now', 'label': 'Run now'}, {'id': 'save', 'label': 'Save'}, {'id': 'repair', 'label': 'Repair the failed step'}]}
AREA_REPORTS = [
    # ── the shelf: a row's own buttons, by its report's name ──
    Q('reports', 'run the AP ageing', None, [v(op='press', button=f'Run now: {AP}')], f'view:press:run_now_{_slug(AP)}', tools=('words',), view=REPORTSHELF, freq=4),
    Q('reports', 'switch off the headcount one', None, [v(op='set', field=f'{HC} on its clock', value='off')], f'view:set:{_slug(HC)}_on_its_clock',
      tools=('words',), view=REPORTSHELF, freq=3),
    Q('reports', "run whatever's due", None, [v(op='press', button='Run due now')], 'view:press:run_due_now', tools=('words',), view=REPORTSHELF, freq=2),
    Q('reports', 'a report of open helpdesk tickets by agent, every morning', None,
      ['Asked the builder for it.\n' + v(op='set', field='describe', value='open helpdesk tickets by agent, every morning at 8')], 'view:set:describe',
      tools=('words',), view=REPORTSHELF, freq=3, note="the describe-it is the composer's field: its draft lands in the builder, nothing saved"),
    Q('reports', 'which of my reports failed?', None, [c('reports.list'), 'None failed; three have never run.'], 'read:reports.list', view=REPORTSHELF, freq=3),
    Q('reports', 'edit the end of day one', None, [v(op='press', button=f'Edit: {EOD}')], f'view:press:edit_{_slug(EOD)}', tools=('words',), view=REPORTSHELF, freq=2),
    # ── one report's builder open: its header's Run now and switch (the owner, 2026-11-02) - the road presses them there, as the view would ──
    Q('reports', 'run it', None, c('report.run', source_id=5), 'view:press:run_now', view=REPORTPAGE, freq=4,
      note="the builder's own Run now, pressed - never the shelf a page away"),
    Q('reports', 'run this report now', None, [v(op='press', button='Run now')], 'view:press:run_now', tools=('words',), view=REPORTPAGE, freq=3),
    Q('reports', 'pasue this reprot', None, c('report.pause', title='AP ageing'), f'view:set:{_slug(AP)}_on_its_clock', view=REPORTPAGE, freq=2,
      note='typos; the switch in its header'),
    Q('reports', 'run the headcount report now', None, c('report.run', title='Headcount'), 'open:#report=reports', freq=3),
    Q('reports', 'test the source', None, [v(op='press', button='Test source')], 'view:press:test_source', tools=('words',), view=REPORTPAGE, freq=3),
    Q('reports', 'preview it', None, [v(op='press', button='Preview pipeline')], 'view:press:preview_pipeline', tools=('words',), view=REPORTPAGE, freq=3),
    Q('reports', 'why did the test fail?', None, ['The source refused the sign-in: report_reader cannot log in - its card under Connections holds the login.'],
      'words', tools=('words',), view=REPORTPAGE, freq=3, note="the page's own last Test answer rides in the view"),
    Q('reports', 'rename it AP over 30 days', None, [v(op='set', field='title — the headline each run shows', value='AP over 30 days')],
      'view:set:title_the_headline_each_run_shows', tools=('words',), view=REPORTPAGE, freq=2),
    Q('reports', 'remove this report', None, [v(op='press', button='Remove report')], 'view:press:remove_report', tools=('words',), view=REPORTPAGE, freq=2,
      note='kept 30 days under Recently deleted'),
    Q('reports', 'make it run every monday at 8', None, c('report.edit', title='AP ageing', config={'cron': '0 8 * * 1'}), 'open:#report=5', view=REPORTPAGE,
      freq=3, note='its schedule is step 3 of this page'),
    # ...and who gets it, in its route card's "to - who gets it" box for the owner's Save: an address as typed, a name one person answers to
    Q('reports', 'email it to gail@northwind.example every time it runs', None,
      c('report.route', title='AP ageing', line='send', how='always', to='gail@northwind.example'),
      'open:#report=5&line=send&to=gail@northwind.example&how=always', view=REPORTPAGE, freq=2, note="a send is never set up from the chat: its Save"),
    Q('reports', 'send this report to Gail every run', None, c('report.route', title='AP ageing', line='send', how='always', to='Gail'),
      'open:#report=5&line=send&to=gmoreno@northwind.example', view=REPORTPAGE, freq=2, note='one Gail has written: her address'),
    # ...and a name nobody answers to is one question back, never a guessed address
    Q('reports', 'send the AP ageing to Paula every run', None,
      [c('report.route', title='AP ageing', line='send', how='always', to='Paula'), "What is Paula's address? Nobody by that name has written here."],
      'words', view=REPORTPAGE, freq=1, note='the miss says ask one question; nothing is set'),
    Q('reports', 'what did it find last time?', None, [c('report.read', title='AP ageing'), 'It has never run.'], 'read:report.read', view=REPORTPAGE, freq=3),
    Q('reports', 'show me every run of the end of day checkup', None, [c('report.read', title='End of day'), 'It has not run yet.'], 'read:report.read', freq=2),
    # ── dashboards ──
    Q('reports', 'refresh this dashboard', None, [v(op='press', button='Run now')], 'view:press:run_now', tools=('words',), view=DASHPAGE, freq=3),
    Q('reports', 'what does the Northwind desk dashboard show', None, [c('report.read', title='Northwind desk'), 'Open tasks, mail in, who wrote most.'],
      'read:report.read', freq=2),
    Q('reports', 'put the dashboard back on its schedule', None, c('report.resume', title='Northwind desk'), 'open:#report=dashboards', freq=1,
      note="a dashboard's switch is on its row on the shelf"),
    # ── routines: their page carries Run now and a switch of its own ──
    Q('reports', 'run this routine', None, [v(op='press', button='Run now')], 'view:press:run_now', tools=('words',), view=ROUTINEPAGE, freq=3),
    Q('reports', 'turn this routine off', None, [v(op='set', field='Month-end tie-out on its clock', value='off')], 'view:set:month_end_tie_out_on_its_clock',
      tools=('words',), view=ROUTINEPAGE, freq=2),
    Q('reports', 'fix the failed step', None, [v(op='press', button='Repair the failed step')], 'view:press:repair', tools=('words',), view=ROUTINEPAGE, freq=2),
    Q('reports', 'every weekday at 9 run the month-end skill', None,
      c('task.create_from_text', kind='general', text='run the month-end skill', title='Month-end skill',
        recurs={'schedule': 'every weekday at 9', 'objective': 'run the month-end skill', 'repo': None, 'skill': 'month-end'}), 'new:workflow', freq=3,
      note='a job on a clock is a routine: New → Routine, filled in for its Save'),
    Q('reports', 'where is the file the routine made?', None, [c('outputs.find', query='routine'), 'No agent has made a file yet.'], 'read:outputs.find', freq=2),
    # ── the rest: what was removed, a report's trouble, and work that is an agent's ──
    Q('reports', 'bring back the report I deleted', None, [c('deleted.list'), 'Nothing was removed in the last 30 days.'], 'read:deleted.list', freq=2),
    Q('reports', 'the AP ageing keeps failing, whats wrong', None, [c('report.read', title='AP ageing'), 'It has never run, so nothing has failed yet.'],
      'read:report.read', freq=3),
    Q('reports', 'go through the last three AP ageing runs and write up the trend', None,
      c('task.create_from_text', kind='general', text='read the last three AP ageing runs and write up the trend', title='AP ageing trend'),
      'new:agent:general', freq=2, note="reading across runs and writing it up is an agent's job"),
]
CASES += AREA_REPORTS

# SETTINGS, ASKED WITH SETTINGS ON SCREEN (the overnight Assistant audit, 2026-11-02): a knob on screen is set where it stands, one off it
# is opened first, a doc is changed through the memory (never retyped whole), Updates installs only by the owner's press, and the
# pages' own buttons - Verify chain, Generate from history, Add rule - are pressed as the owner would
def _sv(title, fields=(), buttons=()):
    return {'area': 'settings', 'title': title, 'fields': list(fields), 'buttons': [{'id': i, 'label': l} for i, l in buttons]}
NOTIF = _sv('the settings group "Notifications" (Settings)', [{'key': 'hand_sound', 'label': 'Play a sound', 'kind': 'switch', 'value': 'on'},
                                                              {'key': 'hand_desktop', 'label': 'Desktop notification', 'kind': 'switch', 'value': 'on'}])
REPLIES = _sv('the settings group "Replies" (Settings)', [{'key': 'email_signature', 'label': 'Email signature', 'value': 'Alex'}])
DOCJOB = _sv('the document "JOB.md" (Settings - Docs)', buttons=[('generate_from_history', 'Generate from history'), ('saved', 'Saved')])
DOCSOUL = _sv('the document "SOUL.md" (Settings - Docs)', buttons=[('write_it_from_a_few_questions', 'Write it from a few questions'), ('saved', 'Saved')])
DOCLEARNED = _sv('the document "LEARNED.md" (Settings - Docs)', buttons=[('text', 'Text'), ('what_changed', 'What changed'), ('visualize', 'Visualize'),
                                                                         ('reflect_now', 'Reflect now'), ('saved', 'Saved')])
POLICIES = _sv('the settings group "Routing policies" (Settings)', buttons=[('add_rule', 'Add rule')])
AUDIT = _sv('the settings group "Audit integrity" (Settings)', buttons=[('verify_chain', 'Verify chain')])
UPDATES = _sv('the settings group "Updates" (Settings)', buttons=[('check_now', 'Check now'), ('update_to_v9_9_9', 'Update to v9.9.9')])
PROFILES = _sv('Profiles (Settings)', buttons=[('new_profile', 'New profile'), ('manage_profiles', 'Manage profiles'), ('set_up', 'Set up')])
AREA_SETTINGS = [
    # ── a knob on screen, set where it stands ──
    Q('settings', 'turn off the sound', None, ['Turned the sound off.\n' + v(op='set', field='hand_sound', value='off')], 'view:set:hand_sound',
      tools=('words',), view=NOTIF, freq=4),
    Q('settings', 'turn of the sond', None, [v(op='set', field='hand_sound', value='off')], 'view:set:hand_sound', tools=('words',), view=NOTIF, freq=2,
      note='a misspelling: the model reads it'),
    Q('settings', "make my signature 'Alex Doyle, Northwind Finance'", None, [v(op='set', field='email_signature', value='Alex Doyle, Northwind Finance')],
      'view:set:email_signature', tools=('words',), view=REPLIES, freq=3),
    # ...one that is not on screen: its group brought up first, then set - never refused for being off the page
    Q('settings', 'and turn off the desktop notifications too', None,
      [v(op='open', area='settings', section='config', open='Notifications', knob='hand_desktop') + '\n' + v(op='set', field='hand_desktop', value='off')],
      'view:set:hand_desktop', tools=('words',), view=REPLIES, freq=3),
    # ── what a setting is, read ──
    Q('settings', 'what does FYI read together do?', None, [c('setting.read', label='FYI read together'), 'It reads a run of FYI to you as one.'],
      'read:setting.read', freq=3),
    Q('settings', "what's in the Replies settings", None, [c('settings.list', group='Replies'), 'The signature, the calendar check and the channels.'],
      'read:settings.list', freq=2),
    Q('settings', 'make the assistant answer faster', None, c('setting.set', setting='concierge_fast', value='1'), 'open:#settings=config', freq=2),
    Q('settings', 'reset all my settings to default', None, 'There is no reset-all - each setting is changed on its own row under Settings.', 'words',
      tools=('words',), freq=1, note='no such button: said, nothing pressed'),
    # ── the docs: brought up, read, and changed through the memory - never retyped whole from the chat ──
    Q('settings', 'open my JOB.md', None, find('job'), 'link:#settings=docs&doc=job', freq=3),
    Q('settings', 'where do I tell it about me', None, find('about you'), 'link:#settings=about', freq=2),
    # ...SOUL, JOB, LEARNED and COUNSEL ride every turn (concierge._system), so they are answered in words; the other docs are read whole
    Q('settings', 'what does my SOUL.md say about me', None, 'That you run AP at Northwind and work in the ledger.', 'words', tools=('words',), freq=2),
    Q('settings', "what's in my STYLE.md", None, [c('docs.search', section='your doc style'), 'Short, plain, signed Alex.'], 'read:docs.search', freq=2),
    Q('settings', 'add that I also run vendor onboarding', None, c('memory.remember', note='I also run vendor onboarding', section='care'),
      'did:memory.remember', view=DOCJOB, freq=3, note="JOB.md is never the chat's to write: a fact about the job is LEARNED's (memoryedit)"),
    Q('settings', "update my JOB.md, I don't handle payroll any more", None,
      c('memory.remember', note="I don't handle payroll any more", section='care'), 'did:memory.remember', freq=3),
    Q('settings', "I'm the AP lead now", None, c('memory.remember', note="I'm the AP lead now", section='soul'), 'did:memory.remember', view=DOCSOUL, freq=2),
    Q('settings', 'be shorter with me from now on', None, c('memory.remember', note='be shorter with me', section='counsel'), 'did:memory.remember', freq=2),
    Q('settings', "always sign off 'Best, Alex'", None, c('memory.remember', note="sign off 'Best, Alex'", section='style'), 'did:memory.remember', freq=2),
    Q('settings', 'rewrite my JOB.md from my mail', None, [v(op='press', button='generate_from_history')], 'view:press:generate_from_history',
      tools=('words',), view=DOCJOB, freq=2),
    Q('settings', 'write my SOUL doc with me', None, [v(op='press', button='write_it_from_a_few_questions')], 'view:press:write_it_from_a_few_questions',
      tools=('words',), view=DOCSOUL, freq=2),
    Q('settings', 'tidy up what you learned', None, [v(op='press', button='reflect_now')], 'view:press:reflect_now', tools=('words',), view=DOCLEARNED, freq=1),
    # ── routing policies: read, and a new one filled in on the page's own form ──
    Q('settings', 'what rules filter my mail?', None, [c('rules.list'), 'No rules filter it yet.'], 'read:rules.list', freq=2),
    # ...the form comes up with Add rule: its boxes are not on the screen that was sent, and the fill after the press is the page's to check
    Q('settings', 'add a rule that skips mail from vendor.example', None,
      ['Filled in the rule - Save is below it.\n' + v(op='press', button='add_rule') + '\n' + v(op='set', field='Name', value='vendor.example')
       + '\n' + v(op='set', field='Reason', value='vendor mail, not mine')], 'view:set:Reason', tools=('words',), view=POLICIES, freq=2),
    # ── the audit log ──
    Q('settings', 'is my audit log intact?', None, [v(op='press', button='verify_chain')], 'view:press:verify_chain', tools=('words',), view=AUDIT, freq=1),
    Q('settings', 'what did you change in my settings this week?', None, [c('activity.list', days=7, who='all'), 'Nothing in the settings changed.'],
      'read:activity.list', freq=2),
    # ── Updates: checked from the page, installed only by the owner's own press (update.status_line: "Nothing installs unless the owner presses it") ──
    Q('settings', 'check for a new version', None, [v(op='press', button='check_now')], 'view:press:check_now', tools=('words',), view=UPDATES, freq=2),
    Q('settings', 'install the update', None, ['It is lit - press it when you are ready.\n' + v(op='press', button='update_to_v9_9_9')],
      'view:point:update_to_v9_9_9', tools=('words',), view=UPDATES, freq=3, note='installing reopens the app: lit for the owner, never pressed by the chat'),
    Q('settings', 'what version am I on', None, find('version'), 'link:#settings=updates&key=update', freq=2),
    # ── profiles ──
    Q('settings', 'make a new profile for vendor research', None, [v(op='press', button='new_profile')], 'view:press:new_profile', tools=('words',),
      view=PROFILES, freq=2),
    # ...and work that needs this computer is an agent's, never a setting (agentwork: the app's own asks never end at one, test_app_own_screens)
    Q('agentwork', 'write a script that backs up my docs folder every night', None,
      c('task.create_from_text', kind='general', text='a script that backs up the docs folder every night', title='Nightly docs backup'), 'new:agent:general',
      freq=1),
]
CASES += AREA_SETTINGS

# NEW, ASKED ABOUT WITH IT UP (the audit of every page, 2026-11-02): the card the sidebar's New posts (CanvasBrowse area "new", NewSheet.jsx),
# as pageView.js reads it - its tabs, its forks, the about box under the label it wears, the brain and model pickers, its own press. The
# Assistant fills it and presses its tabs; a job asked for in words is written into New on its tab - an agent's pressed for the owner (2026-11-02)
TABS = [{'id': i, 'label': l} for i, l in (('send_something', '✉️Send something'), ('give_an_agent_a_job', 'Give an agent a job'),
        ('note_to_self', '💡Note to self'), ('meeting', '📅Meeting'), ('set_a_goal', '🎯Set a goal'), ('report', '📊Report'),
        ('dashboard', '📈Dashboard'), ('routine', '🔁Routine'), ('playbook', '📖Playbook'), ('close_new_task', 'Close new task'))]
NEWAGENT = {'area': 'new', 'title': '', 'text': 'What are we starting? Give an agent a job WHO WORKS IT A live session A general agent',
            'fields': [{'key': 'about', 'label': 'What should it find out or write', 'kind': 'text', 'value': ''},
                       {'key': 'brain', 'label': 'Brain', 'kind': 'choice', 'value': 'the brain it runs on'},
                       {'key': 'model', 'label': 'Model', 'kind': 'choice', 'value': "the agent's default model"}],
            'buttons': TABS + [{'id': 'a_live_session_a_cli_agent_on_a_keyboard_in_a_checkout_it_edits_runs_and_reports',
                                'label': 'A live session a CLI agent on a keyboard, in a checkout — it edits, runs and reports back.'},
                               {'id': 'a_general_agent_a_researcher_analyst_or_writer_on_its_own_it_looks_things_up_dr',
                                'label': 'A general agent a researcher, analyst or writer on its own. It looks things up, drafts and r'},
                               {'id': 'cancel', 'label': 'Cancel'}, {'id': 'send_to_agent', 'label': 'Send to agent', 'enabled': False}]}
NEWCODING = {**NEWAGENT, 'fields': [{'key': 'about', 'label': 'What should it do', 'kind': 'text', 'value': 'fix the census sync'},
                                    {'key': 'repository_the_session_opens_in', 'label': 'Repository the session opens in', 'kind': 'choice',
                                     'value': 'Auto - picks from what you write', 'options': ['Auto - picks from what you write', 'northwind/ledger',
                                                                                             'northwind/portal', 'Another repository…']}],
             'text': 'Give an agent a job A live session No coding tool is connected - Connect one',
             'buttons': [b for b in NEWAGENT['buttons'] if b['id'] != 'send_to_agent']
                        + [{'id': 'connect_one', 'label': 'Connect one'}, {'id': 'send_to_coding_agent', 'label': 'Send to coding agent', 'enabled': False}]}
NEWFILLED = {**NEWAGENT, 'fields': [{**NEWAGENT['fields'][0], 'value': 'find out why invoice 88213 is past due'}, *NEWAGENT['fields'][1:]],
             'buttons': [b for b in NEWAGENT['buttons'] if b['id'] != 'send_to_agent'] + [{'id': 'send_to_agent', 'label': 'Send to agent'}]}
NEWCODEREADY = {**NEWCODING, 'text': 'Give an agent a job A live session',
                'buttons': [b for b in NEWCODING['buttons'] if b['id'] not in ('connect_one', 'send_to_coding_agent')]
                           + [{'id': 'send_to_coding_agent', 'label': 'Send to coding agent'}]}
NEWMEET = {'area': 'new', 'title': '', 'text': 'What are we starting? Meeting WITH ABOUT HOW LONG WHEN',
           'fields': [{'key': 'with', 'label': 'With', 'kind': 'text', 'value': ''}, {'key': 'about', 'label': 'About', 'kind': 'text', 'value': 'the budget'},
                      {'key': 'note', 'label': 'Note or agenda', 'kind': 'text', 'value': ''}],
           'buttons': TABS + [{'id': f'{m}_min', 'label': f'{m} min'} for m in (15, 30, 45, 60)]
                      + [{'id': 'soon', 'label': 'Soon'}, {'id': 'this_week', 'label': 'This week'}, {'id': 'next_week', 'label': 'Next week'},
                         {'id': 'find_times', 'label': 'Find times'}, {'id': 'tue_3_nov_10_00', 'label': 'Tue 3 Nov, 10:00'},
                         {'id': 'use_this_time', 'label': 'Use this time', 'enabled': False}, {'id': 'cancel', 'label': 'Cancel'}]}
NEWREPORT = {'area': 'new', 'title': '', 'text': 'What are we starting? Report Set up with AI Set it up by hand',
             'fields': [], 'buttons': TABS + [{'id': 'set_it_up_by_hand', 'label': 'Set it up by hand'},
                                               {'id': 'cancel', 'label': 'Cancel'}]}
NEWNOTE = {'area': 'new', 'title': '', 'text': 'What are we starting? Note to self COME BACK TO IT',
           'fields': [{'key': 'about', 'label': 'What do you want to remember', 'kind': 'text', 'value': 'call the bank'},
                      {'key': 'when', 'label': 'Come back to it', 'kind': 'text', 'value': ''}],
           'buttons': TABS + [{'id': 'cancel', 'label': 'Cancel'}, {'id': 'note_it', 'label': 'Note it'}]}
AREA_NEW = [
    # ── its form, filled and pressed through its own handlers ──
    Q('new', 'make it a general agent', None, [v(op='press', button='A general agent')], 'view:press:a_general_agent', tools=('words',), view=NEWAGENT, freq=4),
    Q('new', 'write in the box: find out why invoice 88213 is past due', None,
      ['Wrote it in.\n' + v(op='set', field='about', value='find out why invoice 88213 is past due')], 'view:set:about', tools=('words',), view=NEWAGENT, freq=4),
    Q('new', 'use claude code for it', None, [v(op='set', field='Brain', value='Claude Code')], 'view:set:brain', tools=('words',), view=NEWAGENT, freq=2,
      note='the brain picker reads as "Brain" on the page now (ui.jsx AgentPicker, 2026-11-02) - it had no name and was never sent'),
    Q('new', 'swich to the meeting tab', None, [v(op='press', button='Meeting')], 'view:press:meeting', tools=('words',), view=NEWAGENT, freq=3,
      note='a typo: the model reads it'),
    # ...a tab pressed reveals its boxes, and the box after it is the page's to find (pageview.take, 2026-11-02)
    Q('new', 'make it a goal due friday', None, [v(op='press', button='Set a goal') + '\n' + v(op='set', field='By', value='2026-11-06')], 'view:set:By',
      tools=('words',), view=NEWAGENT, freq=2, note='the By box is drawn by the press - it was dropped as a box the view never had'),
    Q('new', 'make it 45 minutes', None, [v(op='press', button='45 min')], 'view:press:45_min', tools=('words',), view=NEWMEET, freq=3),
    Q('new', 'add gail@northwind.example to it', None, [v(op='set', field='With', value='gail@northwind.example')], 'view:set:with', tools=('words',),
      view=NEWMEET, freq=3),
    Q('new', 'find us a time next week', None, [v(op='press', button='Next week') + '\n' + v(op='press', button='Find times')], 'view:press:find_times',
      tools=('words',), view=NEWMEET, freq=4),
    Q('new', 'take the tuesday 10am one', None, ['That drafts the invite on a task of its own, for your Send.\n' + v(op='press', button='Tue 3 Nov, 10:00')],
      'view:press:tue_3_nov_10_00', tools=('words',), view=NEWMEET, freq=3, note='a pick only drafts the invite - its Send is in Close out'),
    Q('new', 'send the invite', None, ['A pick drafts it on a task of its own - its Send waits in Close out there. Pick a time first.'], 'words',
      tools=('words',), view=NEWMEET, freq=3, note='New has no Send: nothing to light, said where it is'),
    Q('new', 'come back to it friday at 9', None, [v(op='set', field='Come back to it', value='2026-11-06T09:00')], 'view:set:when', tools=('words',),
      view=NEWNOTE, freq=3, note='the date box reads as "Come back to it" now (NewSheet.jsx, 2026-11-02) - it had no name and was never sent'),
    Q('new', 'set it up by hand', None, [v(op='press', button='Set it up by hand')], 'view:press:set_it_up_by_hand', tools=('words',), view=NEWREPORT, freq=2),
    Q('new', 'close this', None, [v(op='press', button='Close new task')], 'view:press:close_new_task', tools=('words',), view=NEWAGENT, freq=3),
    Q('new', 'put it in northwind/ledger', None, [v(op='set', field='Repository the session opens in', value='northwind/ledger')],
      'view:set:repository_the_session_opens_in', tools=('words',), view=NEWCODING, freq=2),
    # ── questions about it, answered from what is on it or from the help ──
    Q('new', "what's the difference between a live session and a general agent?", None,
      ['A live session is a coding tool working in a checkout; a general agent looks things up and writes, with no repository.'], 'words',
      tools=('words',), view=NEWAGENT, freq=3),
    Q('new', 'why is send to coding agent greyed out', None, ['No coding tool is connected - [connect one](#cli-agents), then it lights.'],
      'link:#cli-agents', tools=('pages',), view=NEWCODING, freq=3),
    Q('new', 'how do I start a coding agent?', None, [c('docs.search', query='start a coding agent'), 'New, then Give an agent a job, then A live session.'],
      'read:docs.search', freq=3),
    Q('new', 'can I attach a screenshot?', None, ['Paste it into the box or use its paperclip - it goes with the words.'], 'words', tools=('words',),
      view=NEWAGENT, freq=2),
    # ── New brought up, blank or on the builder its tab opens ──
    Q('new', 'I want to start something new', None, ['Here: [New](#new-task).'], 'link:#new-task', tools=('pages',), freq=3,
      note='New itself has an address (canvasLinks #new-task) - APP PAGES names it since 2026-11-02'),
    Q('new', 'open the new dashboard builder', None, ['Here: [New dashboard](#report=new-dashboard).'], 'link:#report=new-dashboard', tools=('pages',), freq=2,
      note='APP PAGES named a new report and a new routine but not a new dashboard (2026-11-02)'),
    Q('new', 'new routine', None, ['Here: [New routine](#report=new-agent).'], 'link:#report=new-agent', tools=('pages',), freq=2),
    # ── "start it" over a filled card: its own Send to agent / Send to coding agent pressed - never read as an outward send (2026-11-02) ──
    Q('new', 'start it', None, [v(op='press', button='Send to agent')], 'view:press:send_to_agent', tools=('words',), view=NEWFILLED, freq=4),
    Q('new', 'go ahead', None, [v(op='press', button='Send to coding agent')], 'view:press:send_to_coding_agent', tools=('words',), view=NEWCODEREADY,
      freq=3, note='"Send to coding agent" read as an outward send, and only lit'),
    # ── a job in words: written into New on its tab - an agent's Send to agent pressed for the owner (2026-11-02), every other tab's theirs ──
    Q('new', 'have an agent look into why the census moved in july', None,
      c('task.create_from_text', kind='general', text='why did the census move in July', title='Census move in July'), 'new:agent:general', freq=4),
    Q('new', 'get a coding agent to fix the nightly export', None,
      c('task.create_from_text', kind='coding', text='fix the nightly export', title='Nightly export fix'), 'new:agent:terminal', freq=4),
    Q('new', 'write to Erin about the Q3 numbers', None, c('task.create_from_text', kind='send', text='the Q3 numbers', to='Erin Blake'), 'new:send', freq=3),
    # ...and on the channel named, to the chat found by its name (the owner, 2026-11-02: it opened on email with To empty)
    Q('new', 'write to the Northwind team WhatsApp group that the installer is ready to go', None,
      c('task.create_from_text', kind='send', channel='whatsapp', to='Northwind team', text='I have updated everything and the installer is ready to go'),
      'new:send', freq=3, seed=wa_group),
    Q('new', 'send this on WhatsApp to the Northwind team: the ledger is closed for October', None,
      c('task.create_from_text', kind='send', channel='whatsapp', to='Northwind team', text='the ledger is closed for October'),
      f'to:whatsapp:{TEAM_GROUP}', freq=3, seed=wa_group, note='New, filled in, for their Send (2026-11-03) - nothing pasted, nothing sent'),
    Q('new', 'set a goal: books closed by the 5th', None, c('task.create_from_text', kind='goal', text='books closed by the 5th'), 'new:goal', freq=2),
    Q('new', 'note to self: call the bank', None, c('task.create_from_text', kind='task', text='call the bank'), 'new:note', freq=3),
    Q('new', 'new dashbaord of open tasks by person', None, c('task.create_from_text', kind='dashboard', text='open tasks by person'), 'new:dashboard', freq=2,
      note='a typo: the model reads it'),
    Q('new', 'every friday at 4 summarise the open AP into a task', None,
      c('task.create_from_text', kind='general', text='summarise the open AP', recurs={'schedule': 'every friday at 4', 'objective': 'summarise the open AP'}),
      'new:workflow', freq=3),
    Q('new', 'set up a report of AP over 30 days', None, c('setup', text='a report of AP over 30 days'), 'new:report', sort={'kind': 'report'}, freq=3),
    Q('new', 'make me a playbook for leave balance requests', None, c('setup', text='a playbook for leave balance requests'), 'new:playbook',
      sort={'kind': 'playbook'}, freq=2),
]
CASES += AREA_NEW

# THE HUB, THE BOARD, SEARCH AND THE OWNER'S PEOPLE (the audit of 2026-11-02: "it has the right tools ... to be able to help the user on
# every page"): the page as HubView / BoardView send it (pageView.js reads it off the DOM - a topic chip is "importers · 2", a post's arrows
# are their titles), and the tools that reach them from anywhere. The demo world's Hub: #1 the dry-run idea, #2 retries by elapsed time,
# #3 the pyodbc gotcha, #4 the bank feed, #5 the census VPN, #6 finance closes on the first Wednesday
HUB = {'area': 'hub', 'title': 'Hub',
       'fields': [{'key': 'search_hub', 'label': 'Search Hub', 'value': ''},
                  {'key': 'order', 'label': 'Order', 'kind': 'choice', 'value': 'top'}, {'key': 'tag', 'label': 'Tag', 'kind': 'choice', 'value': ''}],
       'buttons': [{'id': 'everything_6', 'label': 'everything · 6'}, {'id': 'importers_2', 'label': 'importers · 2'},
                   {'id': 'payroll_1', 'label': 'payroll · 1'}, {'id': 'removed', 'label': 'removed'}, {'id': 'write_one', 'label': 'Write one'}]}
# ...each post's buttons named by the post (HubView.jsx `named`, 2026-11-02): ten "remove"s on the list were one name to the Assistant
def _named(t): return f"“{t[:48]}{'…' if len(t) > 48 else ''}”"
def _btn(label): return {'id': _slug(label)[:60], 'label': label}
PYODBC = _named('The AP importer needs pyodbc on the box before its tests mean anything')
HUBPOST = {'area': 'hub', 'title': 'the Hub post "The AP importer needs pyodbc on the box before its tests mean anything" (importers)',
           'fields': [{'key': 'search_hub', 'label': 'Search Hub', 'value': ''},
                      {'key': 'correct_it_add_to_it_or_say_where_it_bit_you', 'label': 'correct it, add to it, or say where it bit you', 'value': ''}],
           'buttons': [{'id': 'importers', 'label': 'importers'}, _btn(f'Vote up {PYODBC}'), _btn(f'Vote down {PYODBC}'), _btn(f'1 comment on {PYODBC}'),
                       _btn(f'Remove {PYODBC}'), {'id': 'post', 'label': 'Post', 'enabled': False}]}
# THE DIALOGS OVER A PAGE (the owner, 2026-11-02): each is the page while it is open (pageView.currentRoot) - the Hub's Write one, Search
# everything with its hits, and the bell's list with each button named by its problem
HUBWRITE = {'area': 'hub_write', 'title': 'Write one - a new Hub post',
            'fields': [{'key': 'title', 'label': 'Title - what is true', 'value': ''}, {'key': 'topic', 'label': 'Topic', 'value': ''},
                       {'key': 'kind', 'label': 'Kind', 'kind': 'choice', 'value': '💡 new idea'},
                       {'key': 'body', 'label': 'Body - why, and what to do about it', 'value': ''}],
            'buttons': [{'id': 'close_hub_entry', 'label': 'Close Hub entry'}, {'id': 'cancel', 'label': 'Cancel'},
                        {'id': 'post_it', 'label': 'Post it', 'enabled': False, 'send': True}]}
SEARCHV = {'area': 'search', 'title': 'Search everything, for “invoice”', 'fields': [{'key': 'search_everything', 'label': 'Search everything', 'value': 'invoice'}],
           'buttons': [_btn('Invoice 88213 from Payworth (Task)'), {'id': 'tq_0004', 'label': 'TQ-0004'}, _btn('Re: Invoice 88213 - remittance (Email)'),
                       _btn('Vendor invoices over 30 days (Report)')]}
BELL = {'area': 'bell', 'title': 'The bell - what is failing right now', 'fields': [],
        'buttons': [_btn(f'{b}: {t}') for t in ('GitHub: the last poll failed', 'Work mail: the last poll failed')
                    for b in ('Open the card', 'Ask the assistant', 'Dismiss')]}


def _failing(s, typ, err):
    from datetime import datetime, timedelta
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Active': 1}, 't'); s.touch_connector(cid, err)
    s._exec('UPDATE connector SET LastErrorAt=? WHERE ConnectorId=?', ((datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'), cid))
def bell_one(s): _failing(s, 'github', 'the token expired')
def bell_two(s): _failing(s, 'github', 'the token expired'); _failing(s, 'outlook', 'the mailbox did not answer')
def hub_removed(s):
    from taskuary import recentlydeleted
    recentlydeleted.remove_hub(s, 3, 'owner')              # the owner's remove on the pyodbc gotcha
BOARD = {'area': 'board', 'title': 'Agent board', 'fields': [],
         'buttons': [{'id': 'columns', 'label': 'Columns'}, {'id': 'wall', 'label': 'Wall'}, {'id': 'live_handoffs', 'label': 'Live handoffs'},
                     {'id': 'feed_the_agent', 'label': '✎ Feed the agent'}, {'id': 'new_task', 'label': 'New task'}]}
AREA_HUB_BOARD_SEARCH = [
    # ── the Hub, on screen: its own box, its chips, its shelves - pressed as the owner would ──
    Q('hub-board-search', 'search the hub for retries', None, ['Searched the Hub for retries.\n' + v(op='set', field='search_hub', value='retries')],
      'view:set:search_hub', tools=('words',), view=HUB, freq=4),
    Q('hub-board-search', 'serch the hub for census', None, [v(op='set', field='Search Hub', value='census')], 'view:set:search_hub', tools=('words',), view=HUB,
      freq=2, note='a misspelling: the model reads it'),
    Q('hub-board-search', 'show me just the importers posts', None, [v(op='press', button='importers')], 'view:press:importers_2', tools=('words',), view=HUB, freq=3),
    Q('hub-board-search', 'sort by newest', None, [v(op='set', field='order', value='newest')], 'view:set:order', tools=('words',), view=HUB, freq=2,
      note="the order and tag menus carry their names now (HubView.jsx, 2026-11-02) - unnamed, the page never sent them"),
    Q('hub-board-search', 'only the gotchas', None, [v(op='set', field='Tag', value='gotcha')], 'view:set:tag', tools=('words',), view=HUB, freq=2),
    Q('hub-board-search', 'what got voted off?', None, [v(op='press', button='removed')], 'view:press:removed', tools=('words',), view=HUB, freq=2),
    Q('hub-board-search', 'open the pyodbc post', None, [v(op='open', area='hub', open='3')], 'view:open:hub', tools=('words',), view=HUB, freq=3,
      note="a post opens by its number - pageview.take hands the Hub a number, as a click on its card does"),
    # ...one post open: its arrows and remove are the owner's kind of press; its Post sends a comment others read, so it is lit
    Q('hub-board-search', 'vote it up', None, [v(op='press', button='Vote up')], f"view:press:{_slug('Vote up ' + PYODBC)[:60]}", tools=('words',),
      view=HUBPOST, freq=3),
    Q('hub-board-search', 'take this off the hub', None, [v(op='press', button='Remove')], f"view:press:{_slug('Remove ' + PYODBC)[:60]}", tools=('words',),
      view=HUBPOST, freq=2),
    Q('hub-board-search', 'comment that the driver is in the build image now', None,
      ['Wrote it in - Post is yours to press.\n' + v(op='set', field='correct it, add to it, or say where it bit you', value='The driver is in the build image now.')
       + '\n' + v(op='press', button='Post')], 'view:point:post', tools=('words',), view=HUBPOST, freq=3,
      note='a comment others read goes by the owner\'s press - Post is lit, never pressed'),
    # ── the Hub from anywhere ──
    Q('hub-board-search', 'what does the hub say about pyodbc?', None, [c('knowledge.search', query='pyodbc'), 'Install pyodbc before the importer tests (#3).'],
      'read:knowledge.search', freq=3),
    Q('hub-board-search', 'upvote the retries post', None, [c('knowledge.search', query='retries'), c('hub.vote', post='#2')], 'open:#hub=&post=2', freq=2),
    Q('hub-board-search', "downvote #3, it's stale", None, c('hub.vote', post='#3', up=False), 'open:#hub=&post=3', freq=2),
    Q('hub-board-search', 'comment on the dry-run idea: it worked for the May launch', None,
      c('hub.comment', post='#1', text='It worked for the May launch.'), 'open:#hub=&post=1', freq=2),
    Q('hub-board-search', 'put this on the hub: finance closes on the first Wednesday', None,
      c('hub.publish', title='Finance closes on the first Wednesday', body='The bank feed has settled by then.', topic='payroll', kind='decision'),
      'open:#hub', freq=2, note="the Hub comes up with the words for its Write one - others read it, so the post is the owner's press"),
    # ...and a Hub post the owner removed is under Recently deleted too (the owner, 2026-11-02): named by its kind, the Hub comes up with it
    Q('hub-board-search', 'bring back the hub post I removed', None, c('deleted.restore', what='hub post'), 'open:#hub', freq=2, seed=hub_removed,
      note='Recently deleted lists it by its kind - "hub post" names the one there'),
    Q('hub-board-search', 'bring back the post the vote took off', None,
      [c('deleted.restore', what='hub post'), "A post the vote took off is on the Hub's own removed shelf - press removed there, then restore beside it."], 'words',
      freq=1, note="the vote's removal is the Hub's own shelf alone - the miss says where it is (concierge.find_deleted)"),
    # ── the Hub's Write one, a dialog over the page: pressed, filled, and its Post it lit for the owner ──
    Q('hub-board-search', 'write one: the bank feed lags a day at month end', None,
      ['Wrote it in - Post it is yours to press.\n' + '\n'.join([v(op='press', button='Write one'), v(op='set', field='title', value='The bank feed lags a day at month end'),
                                                                   v(op='set', field='body', value='Reconcile on day two.'), v(op='press', button='Post it')])],
      'view:point:Post it', tools=('words',), view=HUB, freq=2, note="Write one's boxes are the dialog's to find; others read the Hub, so Post it is lit"),
    Q('hub-board-search', 'title it finance closes on the first Wednesday, topic payroll', None,
      [v(op='set', field='title', value='Finance closes on the first Wednesday') + '\n' + v(op='set', field='Topic', value='payroll')], 'view:set:title',
      tools=('words',), view=HUBWRITE, freq=2),
    Q('hub-board-search', 'post it', None, ['Post it is yours to press.\n' + v(op='press', button='Post it')], 'view:point:post_it', tools=('words',), view=HUBWRITE,
      freq=2, note="a Hub post is read by others: the owner's press, lit"),
    Q('hub-board-search', 'show me the hub', None, find('hub'), 'link:#hub', freq=3),
    # ── the Board, on screen ──
    Q('hub-board-search', 'switch to the wall', None, [v(op='press', button='Wall')], 'view:press:wall', tools=('words',), view=BOARD, freq=2),
    Q('hub-board-search', 'what are the agents telling each other?', None, [v(op='press', button='Live handoffs')], 'view:press:live_handoffs', tools=('words',),
      view=BOARD, freq=2),
    Q('hub-board-search', 'which of these are running right now', None, [c('agents.now'), 'One, on TQ-0006.'], 'read:agents.now', view=BOARD, freq=3),
    Q('hub-board-search', 'why is the census sync stuck?', None, [c('task.read', ref=T12), 'It is waiting on a repository.'], 'read:task.read', view=BOARD, freq=3),
    Q('hub-board-search', 'put an agent on tidying the vendor list', None,
      c('task.create_from_text', kind='general', text='tidy the vendor list', title='Tidy the vendor list'), 'new:agent:general', view=BOARD, freq=3),
    Q('hub-board-search', 'take me to the board', None, c('page.open', page='board'), 'open:#board', freq=3),
    # ── Search everything ──
    Q('hub-board-search', 'find anything mentioning pyodbc', None, c('page.open', page='search', query='pyodbc'), 'open:#search=pyodbc', freq=3),
    Q('hub-board-search', 'serach for invoice 88213', None, c('page.open', page='search', query='invoice 88213'), 'open:#search=invoice%2088213', freq=2),
    Q('hub-board-search', "what's Gail's email address?", None, [c('sender.read', who='Gail Moreno'), 'gail@northwind.example.'], 'read:sender.read', freq=3),
    # ...open, it is the page (pageView.currentRoot): its box typed, a hit opened by its title - and brought up with its words from any page
    Q('hub-board-search', 'search everything for pyodbc and open the first hit', None,
      [v(op='open', area='search', query='pyodbc') + '\n' + v(op='press', button='pyodbc')], 'view:open:search', tools=('words',), view=HUB, freq=3),
    Q('hub-board-search', 'open the payworth one', None, [v(op='press', button='Invoice 88213 from Payworth')],
      f"view:press:{_slug('Invoice 88213 from Payworth (Task)')}", tools=('words',), view=SEARCHV, freq=3),
    Q('hub-board-search', 'serch for remittance instead', None, [v(op='set', field='Search everything', value='remittance')], 'view:set:search_everything',
      tools=('words',), view=SEARCHV, freq=2),
    # ── the bell: its Dismiss by the words in the chat, open or shut; open, each button named by its problem ──
    Q('hub-board-search', 'clear the error on the bell', None, c('problems.dismiss'), 'did:problems.dismiss', freq=3, seed=bell_one),
    Q('hub-board-search', 'dismiss the work mail error', None, c('problems.dismiss', which='work mail'), 'did:problems.dismiss', freq=3, seed=bell_two),
    Q('hub-board-search', 'got it, clear them all', None, c('problems.dismiss', which='all'), 'did:problems.dismiss', freq=2, seed=bell_two, phone=True),
    Q('hub-board-search', 'clear the bell', None, [c('problems.dismiss'), 'There are two on the bell - which one?'], 'words', freq=2, seed=bell_two,
      note='several and none named: the miss lists them, nothing is put down'),
    Q('hub-board-search', 'dismiss the github one', None, [v(op='press', button='Dismiss: GitHub')], f"view:press:{_slug('Dismiss: GitHub: the last poll failed')}",
      tools=('words',), view=BELL, freq=2, note="the bell's list open is the page: each Dismiss named by its problem"),
    # ── the owner's people (orgchart.py): said and kept; read back from the memory ──
    Q('hub-board-search', 'Gail reports to me', None, c('people.relate', who='Gail Moreno', relation='report'), 'did:people.relate', freq=3),
    Q('hub-board-search', "Ray doesn't own payroll anymore", None, c('people.relate', who='Ray Colton', drops='payroll'), 'did:people.relate', freq=2),
    Q('hub-board-search', 'take Omar off my org chart', None, [c('people.relate', who='Omar Keller', forget=True), 'Omar is not on your org chart - nothing to take off.'],
      'words', freq=1, note='nobody by that name on the chart: the miss is said, nothing changed'),
    Q('hub-board-search', 'who is my manager?', None, [c('memory.list', about='manager'), 'Nobody is on your org chart as your manager yet.'], 'read:memory.list', freq=3),
    # ── what was removed ──
    Q('hub-board-search', 'did I delete a routine by mistake?', None, [c('deleted.list'), 'Nothing removed in the last 30 days.'], 'read:deleted.list', freq=1),
]
CASES += AREA_HUB_BOARD_SEARCH

# THE SAME ASKS BY PHONE (the phone audit, 2026-11-02): each row verb reach() names, typed in a phone chat - what goes out or closes asks
# yes or no, a put-down is done at once, so is a small change that sends and closes nothing (`now:`, the owner 2026-11-02), an act the row cannot do is said (never asked, so no yes runs into nothing), and what only
# a screen has is said in words, at the desk
AREA_PHONE = [
    Q('phone', 'next', 'todo', c('next'), 'next', freq=5, phone=True, note="the phone drops the bare Next. - the next card is its receipt"),
    Q('phone', 'make the draft shorter', 'review', c('redraft', text='shorter'), 'draft:redraft', freq=4, phone=True),
    Q('phone', 'aprove it', 'review', c('approve'), 'proposal:review.approve', freq=3, phone=True, note='a misspelling: the model reads it'),
    Q('phone', 'forward this to gail@northwind.example', 'todo', c('task.handoff', who='gail@northwind.example'), 'proposal:task.handoff', freq=3, phone=True),
    Q('phone', "this isn't a task", 'todo', c('task.not_a_task'), 'proposal:task.not_a_task', freq=3, phone=True, note='a put-down: done at once'),
    Q('phone', 'close it with a note: paid on the 3rd', 'todo', c('task.complete', note='paid on the 3rd'), 'proposal:task.complete', freq=3, phone=True),
    Q('phone', 'remnd me firday', 'todo', c('task.defer', until='friday 9am'), 'now:task.defer', freq=3, phone=True),
    Q('phone', 'accept it', 'invite', c('accept_invite'), 'proposal:calendar.answer', freq=3, phone=True),
    Q('phone', 'decline it', 'invite', c('decline_invite'), 'proposal:calendar.answer', freq=3, phone=True),
    Q('phone', 'can we do thursday instead', 'invite', c('propose_time', text='thursday'), 'proposal:calendar.answer', freq=3, phone=True),
    Q('phone', 'find a time with Gail', 'invite', c('find_time'), 'words', freq=2, phone=True, note='an invite is no ask for a time: said'),
    Q('phone', 'split this in two: the refund is its own job', 'todo', c('task.split', text='the refund is its own job'), 'proposal:task.split', freq=2, phone=True),
    Q('phone', f'reopen {T4}', None, [c('task.reopen', ref=T4), f'{T4} is still open - there is nothing to reopen.'], 'words', freq=2, phone=True,
      note='an open task has no Reopen: said, never asked (the phone audit, 2026-11-02)'),
    Q('phone', 'make it high priority', 'todo', c('task.update', priority='high'), 'now:task.update', freq=3, phone=True),
    Q('phone', 'this is a coding task', 'todo', c('task.set_kind', kind='coding'), 'now:task.set_kind', freq=2, phone=True),
    Q('phone', 'put it in northwind/importers', 'coding', c('task.set_repo', repo='northwind/importers'), 'now:task.set_repo', freq=1, phone=True),
    Q('phone', 'put an agent on it', 'todo', c('regular_agent'), 'proposal:task.create_from_message', freq=3, phone=True),
    Q('phone', 'stop the agent', 'agent', c('stop_agent'), 'proposal:agent.stop', freq=4, live=6, phone=True),
    Q('phone', 'keep going', 'agent', [c('agent.continue', ref=T6), 'It has no saved session to pick up.'], 'words', freq=3, phone=True,
      note='no saved session in the demo world: said, never asked (the phone audit, 2026-11-02)'),
    Q('phone', 'triage this again', 'fyi', [c('message.retriage'), 'Triage already sorted this one as an FYI.'], 'words', freq=1, phone=True,
      note="an FYI's row has no Sort it again: said, never asked (the phone audit, 2026-11-02)"),
    Q('phone', "watch this, it's Gail's problem", 'todo', c('task.watch'), 'now:task.watching', freq=3, phone=True,
      note="the row's Watch it, as its chip runs it - at once: it sends and closes nothing (the owner, 2026-11-02)"),
    Q('phone', 'tell me when Gail replies', 'todo', c('task.watch', what='reply'), 'now:task.watching', freq=3, phone=True,
      note='Watch it as on the desk, never a second kind of watch (the owner, 2026-11-02: "both should mean same thing")'),
    Q('phone', 'block this sender', 'fyi', c('block_sender'), 'proposal:preference.sender_rule', freq=2, phone=True),
    Q('phone', 'email what it found to gail@northwind.example', 'agent', c('task.share', who='gail@northwind.example'), 'proposal:task.share', freq=2, phone=True),
    Q('phone', 'clear all the fyi', 'fyi', c('pipe.clear', select={'kind': 'fyi'}), 'cleared', freq=3, phone=True),
    Q('phone', 'research what Payworth charges per seat', 'todo',
      c('task.create_from_text', kind='general', text='research what Payworth charges per seat', title='Payworth seat price'), 'proposal:task.create_from_text',
      freq=3, phone=True),
    Q('phone', "what's on my plate today?", None, [c('tasks.list'), 'Three tasks wait on you.'], 'read:tasks.list', freq=5, phone=True),
    Q('phone', 'Gail moved to Ops', None, c('memory.remember', note='Gail Moreno moved to Ops', about='gail@northwind.example'), 'did:memory.remember', freq=2, phone=True),
    Q('phone', 'turn on the morning message', None, [c('settings.list', group='Assistant on your phone'), c('setting.set', setting='phone_morning_line', value='1')],
      'proposal:setting.set', freq=2, phone=True),
    Q('phone', "whatsapp isn't working", None, [c('app.health', name='whatsapp'), 'WhatsApp is switched off - Open the connection on its card, at your desk.'],
      'read:app.health', freq=3, phone=True),
    Q('phone', 'how do I hook up telegram', None, [c('docs.search', query='telegram'), 'At your desk: its card under Connections takes the bot token.'],
      'read:docs.search', freq=2, phone=True),
    Q('phone', 'open settings', None, ['Settings is on your desk - no link opens on a phone.'], 'words', tools=('screens',), freq=2, phone=True),
    Q('phone', 'copy the draft', 'review', ['The draft is the text above - copy it from the chat.'], 'words', tools=('words',), freq=2, phone=True,
      note="Copy is the screen's clipboard (PHONE_UNREACHABLE)"),
    Q('phone', 'show me the diff', 'agent', ['The diff opens from the task page, at your desk.'], 'words', tools=('words',), freq=2, phone=True,
      note="Review changes is the screen's (PHONE_UNREACHABLE)"),
]
CASES += AREA_PHONE

# WHAT IT KNOWS ABOUT ITSELF AND THE OWNER (the owner, 2026-11-01: "it has the right tools, memories, and jobs/soul.md to be able to help the
# user on every page"): the memory and the owner's documents - kept, read and corrected - its help, its own trouble and its tracker. The
# docs pages (Settings → Docs) send their buttons; their document's own box has no label and goes as no field - a VIEW `set` would put a
# 200-character cut in place of the whole document, so a line is added with memory.remember, never typed into the box
def _doc(name, *b): return {'area': 'settings', 'title': f'the document "{name}" (Settings - Docs)', 'fields': [],
                            'buttons': [{'id': i, 'label': l} for i, l in b] + [{'id': 'saved', 'label': 'Saved', 'enabled': False}]}
LEARNEDDOC = _doc('LEARNED.md', ('text', 'Text'), ('what_changed', 'What changed'), ('visualize', 'Visualize'), ('reflect_now', 'Reflect now'))
STYLEDOC, SOULDOC = _doc('STYLE.md', ('generate_from_history', 'Generate from history')), _doc('SOUL.md', ('write_it_from_a_few_questions', 'Write it from a few questions'))
from taskuary import __version__
AREA_SELF_KNOWLEDGE = [
    # ── the memory, on its own page and off it ──
    Q('self-knowledge', 'what have you learned about how I work?', None, [c('memory.list'), 'Nothing kept yet - every section is still empty.'],
      'read:memory.list', view=LEARNEDDOC, freq=3),
    Q('self-knowledge', 'show me what changed in my memory this week', None, v(op='press', button='what_changed'), 'view:press:what_changed', tools=('words',),
      view=LEARNEDDOC, freq=2),
    Q('self-knowledge', 'reflect now', None, v(op='press', button='reflect_now'), 'view:press:reflect_now', tools=('words',), view=LEARNEDDOC, freq=1),
    Q('self-knowledge', 'remember I never want the payroll vendor newsletters as tasks', None,
      c('memory.remember', note='I never want the payroll vendor newsletters as tasks', section='care'), 'did:memory.remember', view=LEARNEDDOC, freq=3),
    Q('self-knowledge', 'do you read my LEARNED.md?', None, 'Yes - the lines in use, with SOUL.md and JOB.md, on every page.', 'words', tools=('words',), freq=1),
    # ── the owner's documents: each fact goes where its reader reads it (memory.remember's section), a document's own buttons pressed ──
    Q('self-knowledge', "from now on sign my emails 'Best, Alex'", None, c('memory.remember', note="sign every email 'Best, Alex'", section='style'),
      'did:memory.remember', view=STYLEDOC, freq=3),
    Q('self-knowledge', 'regenerate my style from my sent mail', None, v(op='press', button='generate_from_history'), 'view:press:generate_from_history',
      tools=('words',), view=STYLEDOC, freq=2),
    Q('self-knowledge', 'be shorter with me', None, c('memory.remember', note='be shorter with me', section='counsel'), 'did:memory.remember', freq=3),
    Q('self-knowledge', "add to this that I'm the AP lead now", None, c('memory.remember', note="I'm the AP lead now", section='soul'), 'did:memory.remember',
      view=SOULDOC, freq=2, note="the document's box is no field: the line is kept by memory.remember, never typed over the document"),
    Q('self-knowledge', 'what does my JOB.md say I am responsible for?', None,
      'The finance and census systems: the GL export, the AP importers, the census database and the helpdesk.', 'words', tools=('words',), freq=2,
      note="JOB.md rides the Assistant's own instructions, whole"),
    Q('self-knowledge', 'how do I usually sign off my emails?', None, [c('docs.search', section='your doc style'), 'Your STYLE.md has no sign-off line yet.'],
      'read:docs.search', freq=2),
    Q('self-knowledge', 'what rules do the agents work under', None, [c('docs.search', section='your doc agent'), 'AGENT.md: nothing sends without you.'],
      'read:docs.search', freq=1),
    Q('self-knowledge', 'open my soul doc', None, 'Here: [SOUL.md](#settings=docs&doc=soul).', 'link:#settings=docs&doc=soul', tools=('pages',), freq=2),
    # ── its help and what version this is ──
    Q('self-knowledge', 'how does the memory work?', None, [c('docs.search', query='memory'), 'It learns from what you do, never a button press.'],
      'read:docs.search', freq=2),
    Q('self-knowledge', "what's the diffrence between SOUL and JOB", None, [c('docs.search', query='JOB.md'), 'SOUL is the rules; JOB is what you protect.'],
      'read:docs.search', freq=2),
    Q('self-knowledge', 'where are the logs kept', None, [c('docs.search', section='help/troubleshooting > Where the logs are'), 'In taskuary.log, in your home.'],
      'read:docs.search', freq=2),
    Q('self-knowledge', 'what version am I on?', None, f'This is Taskuary {__version__}.', 'words', tools=('words',), freq=2,
      note='the version rides its instructions (concierge._system)'),
    # ── its own trouble, looked into here ──
    Q('self-knowledge', 'something is wrong with taskuary, it feels stuck', None, [c('app.health'), 'Nothing is failing right now.'], 'read:app.health', freq=3),
    Q('self-knowledge', "why didn't my AP ageing report run this morning", None, [c('errors.list', days=1), 'No report run failed in the last day.'],
      'read:errors.list', freq=3),
    Q('self-knowledge', 'is the outlook connection healthy', None, [c('app.health', name='outlook'), 'Work mail is on; nothing failing.'], 'read:app.health',
      view=IMAP, freq=2, note="the owner's Outlook card is named Work mail: the live card is read, never the catalogue's unused Outlook one"),
    Q('self-knowledge', 'dismiss whatever is on the bell', None, [c('problems.dismiss'), 'Nothing is failing - the bell is empty.'], 'words',
      freq=2, note="problems.dismiss over an empty bell: the miss says so, nothing changed (the bell's own cases are under hub-board-search)"),
    # ── its tracker: drafted here, submitted by the owner ──
    Q('self-knowledge', 'taskaury keeps freezing when I press Next', None,
      [c('issue.draft', kind='bug', trying='press Next on the walk', happened='the app froze'), 'A bug report is drafted below for your Submit.'],
      'read:issue.draft', freq=3),
    Q('self-knowledge', 'file a bug: the chat pill covers the Save button on settings', None,
      [c('issue.draft', kind='bug', trying='press Save on a settings page', happened='the chat pill covers the button'), 'Drafted below - Submit it on GitHub.'],
      'read:issue.draft', view=SETTINGSPAGE, freq=2),
    Q('self-knowledge', 'submit that bug report for me', None, 'Submit is yours to press on GitHub - nothing is filed from here.', 'words', tools=('words',), freq=1,
      note='nothing is filed from the chat: the owner submits'),
]
CASES += AREA_SELF_KNOWLEDGE

# WHAT A REAL MODEL WROTE (the live audit, 2026-11-02): the scripted brains above answer as the road expects; a real one, asked the same,
# picked a row's decision with the task's ref - or none - over a task page, guessed a report's parameter, and wrapped its CALL in its own
# tool markup or a code fence. Each answer here is the shape it wrote, and the road has to land it
AREA_LIVE = [
    Q('task', 'mark it done', None, c('close'), 'light:close', view=TASK4V, freq=5, note="no table, but the page sent its task: that is the one"),
    Q('task', 'mark it done', None, c('close', ref=T4), 'light:close', view=TASK4V, freq=4, note='a decision takes the ref HOW YOU ACT says a named task goes in'),
    Q('task', 'send it', None, c('approve'), 'light:approve', view=TASK4V, freq=4, note='lit, never sent'),
    Q('reports', 'run the end of day report', None, c('report.run', name='End of day checkup'), 'open:#report=', freq=4),
    Q('reports', 'delete the headcount report', None, c('report.delete', ref='Headcount by site, nightly'), 'open:#report=', freq=1),
    # ...the Advisor's job-ideas pass, NOW (lookout.start, the owner 2026-11-03): started off the chat's thread and said - here no AI, said so
    Q('reports', 'look for ideas for my job now', None, c('advisor.ideas'), 'did:advisor.ideas', freq=2),
    Q('reports', 'run the advisor ideas', None, c('advisor.ideas'), 'did:advisor.ideas', freq=2),
    Q('phone', 'any ideas for my job? run the advisor now', None, c('advisor.ideas'), 'did:advisor.ideas', freq=1, phone=True),
    Q('help', "what's new in this version?", None,
      ['<invoke name="docs.search">\n<parameter name="query">what changed</parameter>\n</invoke>', 'The newest release adds the Watch it button.'],
      'read:docs.search', tools=('docs.search',), freq=3, note="a CLI brain's own tool markup is its CALL, and never shown"),
    Q('people', 'who is Erin Blake', None, ['```\n' + c('sender.read', who='Erin Blake') + '\n```', 'Erin Blake writes most weeks.'], 'read:sender.read', tools=('sender.read',), freq=3,
      note='a stray fence after the CALL'),
    Q('people', 'who is Gail Moreno', None, ['One moment.\n' + c('sender.read', who='Gail') + '\n' + c('timeline.search', contains='Gail'), 'Gail Moreno writes now and then.'],
      'read:sender.read', tools=('sender.read',), freq=2, note='two CALL lines: the first runs'),
    Q('people', 'who is Paula Vance', None, ['Let me look. CALL: {"kind": "sender.read", "par', c('sender.read', who='Paula'), 'Paula Vance is on the finance team.'],
      'read:sender.read', tools=('sender.read',), freq=2, note='cut off, asked again: the retry runs its one look-up and answers'),
    Q('agentwork', 'what is the PO approval limit here', None,
      [c('knowledge.search', query='PO approval limit'), 'Nothing written here says.\n' + c('regular_agent', text='find the PO approval limit', new=True)],
      'new:', freq=2, note='what it did leads, what it found follows (said_what)'),
]
CASES += AREA_LIVE

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


_SEEDED = []   # run_all's demo world, built once: each of its turns gets a copy (_copy)


def _copy(t):
    """A new store over a copy of t's rows. Its own __init__ runs - every lock, cache and counter is its own - but over a database
    that already has the schema, so the ~700 schema statements a blank store runs find nothing to do (0.01 s, not 0.09 s)."""
    import sqlite3
    from taskuary import store as S
    cx = sqlite3.connect(':memory:', check_same_thread=False, timeout=5.0); t.cx.backup(cx)
    with mock.patch.object(S.sqlite3, 'connect', lambda *a, **k: cx): return S.MemoryStore()


def _world():
    from taskuary import demo, funnel, terminal
    from taskuary.store import MemoryStore
    funnel.invalidate(); funnel.forget_states(); funnel._SOURCES.update(at=0.0, by={})
    if _SEEDED: s = _copy(_SEEDED[0]); funnel.invalidate(); return s
    s = MemoryStore()
    with mock.patch.object(terminal, 'live_sessions', return_value=[]): demo.seed(s)
    for k in ('auto_draft_enabled',): s.set_setting(k, '0', 't')
    s.set_task_checklist(1, ['pull the bank feed', 'find the 4,180', 'send Marcus the answer'], 'owner')
    s.save_connector({'Type': 'outlook', 'Name': 'Work mail', 'Active': 1}, 't')
    funnel.invalidate()
    return s


def _guards(stack, sort=None, live=None, agenda=None):
    """No real model, ever: the CLI and API builders raise, and the set-up sorter answers from the case."""
    from taskuary import concierge, funnel, ingest, llm as llm_mod, terminal
    # ...and a calendar where a case's seed laid one (meeting_row): the demo world has none
    if agenda: stack.enter_context(mock.patch.object(funnel, '_agenda', lambda store, block=True: list(agenda)))
    # ...and THE INDEX NAMES EVERY TOOL, coding's too: the corpus measures what the prompt carries for its coding asks, while the world here
    # has no coding tool, so its hand-offs still go the regular road. The index without them is test_developer_mode's (toolcatalog.CODING_ONLY)
    from taskuary import toolcatalog
    stack.enter_context(mock.patch.object(toolcatalog, '_offered', lambda store, kind: True))
    # ...nor a general hand-off's chat session: no first turn is sent to an AI (concierge.handoff_task)
    from taskuary import general
    stack.enter_context(mock.patch.object(general, 'start_session', return_value=mock.Mock()))
    def never(*a, **k): raise AssertionError('a real model was asked for')
    stack.enter_context(mock.patch.object(llm_mod, 'make_cli_llm', never))
    stack.enter_context(mock.patch.object(llm_mod, 'build_llm', never))
    stack.enter_context(mock.patch.object(terminal, 'live_sessions', return_value=[{'taskId': int(live), 'sid': f's{live}'}] if live else []))
    # a running session on one task, where the case says so - what Stop and save is drawn by (concierge._agent_running)
    stack.enter_context(mock.patch.object(terminal, 'for_task', lambda tid, **k: {'sid': f's{tid}'} if live and int(tid) == int(live) else None))
    stack.enter_context(mock.patch.object(ingest, '_spawn'))
    stack.enter_context(mock.patch.object(ingest, 'ask_later'))     # ...nor the model reading a promoted mail's ask (a hand-off makes its task)
    # ...and no agent starts, nothing is typed into a session: the dispatch door answers as a start would (concierge._start_agent, 2026-11-02),
    # and the waiting room holds every note as for an agent at work (concierge._tell_now)
    from taskuary import server, waitroom
    stack.enter_context(mock.patch.object(server, '_dispatch_task_to_its_agent', lambda tid, body, bg: {'dispatch': 'session', 'started': True, 'existing': False,
                                                                                                        'taskId': tid, 'ref': f'TQ-{int(tid):04d}'}))
    # ...so the AI that would run it counts as connected (server._brainless): run_all runs in setUpClass, outside conftest's an_ai_is_connected
    stack.enter_context(mock.patch.object(server, '_brainless', lambda coding: ''))
    stack.enter_context(mock.patch.object(waitroom, 'state', lambda store, tid: ('working', None)))
    sorted_ = json.dumps(sort or {'kind': 'report', 'why': 'scripted'})
    stack.enter_context(mock.patch.object(concierge, '_compose_llm', return_value=lambda *a, **k: sorted_))


# THE ACT, SAID (the owner, 2026-10-20: "it should show what it chose to do"): an answer that acted or lit leads with what it did - never a
# bare word. A proposal on a phone is its question; a look-up's answer and a link are the model's own words.
ACTS = ('Opened ', 'Marked ', 'Wrote ', 'Put down ', 'Drafting ', 'Rewriting ', 'Snoozed ', 'Closed ', 'Added ', 'Set ', 'Noted ',
        'Ticked ', 'Unticked ', 'Took ', 'Renamed ', 'Brought up ', 'Remembered ', 'Filed ', 'Put on ', 'Blocked', 'Stopped ', 'Triage already ', 'Org chart: ',
        'Nothing went', 'Saved ', 'Adopted ', 'Kept ', 'Told ', 'Pressed ', 'Started ', 'Nothing started')
def said_what(say: str, got: list, q) -> bool:
    acted = [g for g in got if g.split(':')[0] in ('open', 'new', 'next', 'draft', 'cleared', 'did')]
    # ...and a lit button or a press speaks for itself - the filled button, the card's badge - and says no line (the owner, 2026-10-23)
    # ...and so does a press on the page itself: the chat shows each one as it runs (pageview.GUIDE)
    if any(g.split(':')[0] in ('light', 'pressed', 'view') for g in got): return not say.startswith('Lit ')
    # ...and Next on a phone: remote_assistant drops its bare "Next." and the next card is the receipt (the phone audit, 2026-11-02)
    if q.phone and got == ['next']: return True
    return not acted or say.startswith(ACTS) and len(say.split()) > 2


def outcomes(out: dict, reads: list) -> list:
    """What the turn did, as words a case can expect."""
    o = []
    if (l := out.get('light')) is not None: o.append(f"light:{l.get('verb') or ''}")
    if (l or {}).get('hand'): o.append(f"hand:{l['hand'].get('to') or ''}")      # ...Hand it to a person's To, filled in
    if (p := out.get('pressed')) is not None: o.append(f"pressed:{p.get('verb') or ''}")
    if out.get('open'): o.append(f"open:{out['open']}")
    if out.get('new'): o.append(f"new:{out['new'].get('kind')}" + (f":{out['new'].get('how')}" if out['new'].get('how') else ''))
    if (n := out.get('new') or {}).get('channel'): o.append(f"to:{n['channel']}:{n.get('to') or ''}")  # ...Send something's channel and To
    if (out.get('new') or {}).get('start'): o.append('press:new')               # ...and its own Send to agent pressed by the page (NewSheet `start`)
    d = (out.get('decision') or {}).get('verb')
    if d == 'next': o.append('next')
    elif d in ('reply', 'redraft'): o.append(f'draft:{d}')
    elif d: o.append(f'decision:{d}')
    if out.get('cleared') is not None: o.append('cleared')
    if out.get('did'): o.append(f"did:{out['did']}")
    if out.get('card') or out.get('opened') or out.get('item'): o.append('card')
    if out.get('proposal'): o.append(f"proposal:{out['proposal'].get('kind')}")
    # ...and one a phone runs at once, no yes asked (a put-down; a small change, the owner 2026-11-02)
    if (out.get('proposal') or {}).get('auto'): o.append(f"now:{out['proposal'].get('kind')}")
    o += [f"go:{ch.get('href') or ''}" for ch in out.get('chips') or [] if ch.get('verb') == 'go']
    o += [f"view:{v['op']}:{v.get('field') or v.get('button') or v.get('target') or v.get('area') or ''}" for v in out.get('view_ops') or []]
    o += [f'read:{k}' for k in reads]
    o += [f'link:{h}' for h in re.findall(r'\]\((#[^)]+)\)', out.get('say') or '')]
    return o or ['words']


MISSES = ('I could not find', 'I could not finish', 'I could not put that', 'could not line', 'Nothing is on the table')


def ideal_turn(q: Q) -> dict:
    from taskuary import concierge, server
    s, seen, reads = _world(), [], []
    key = (q.seed(s) if q.seed else None) or TABLES[q.table]
    real_read = concierge._read
    def read(store, item, call):
        found = real_read(store, item, call); reads.append(call['kind']); return found
    with ExitStack() as st:
        _guards(st, q.sort, q.live, getattr(s, 'agenda', None))
        st.enter_context(mock.patch.object(server, 'store', s))          # a typed put-down runs its operation (concierge._put_down)
        st.enter_context(mock.patch.object(concierge, '_read', read))
        err = None
        if q.phone: st.enter_context(concierge.delivering(concierge.PHONE))
        try: out = concierge.say(s, q.text, key=key, llm=_scripted(q.ideal, seen), view=q.view)
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
    return {'grade': grade, 'got': got, 'say': say, 'heard': heard, 'told': told, 'carried': carried, 'missing': [t for t in q.tools if t not in carried],
            'prompt': prompt}


def demo_line(said: str, out: dict | None = None) -> str:
    """'out' when the demo said its honest line with every suggestion under it and did nothing else; what it did instead, otherwise."""
    from taskuary import demo
    out = out or {}
    if out.get('light') or out.get('pressed') or out.get('decision') or out.get('proposal'): return 'acted'
    if said == demo.OUT_OF_SCRIPT and [c for c in out.get('chips') or [] if c.get('prompt')] == demo.prompt_chips(): return 'out'
    return 'other'


def demo_turn(q: Q) -> dict:
    from taskuary import concierge, demo, server
    s = _world()
    key = (q.seed(s) if q.seed else None) or TABLES[q.table]
    with ExitStack() as st:
        _guards(st, q.sort, q.live, getattr(s, 'agenda', None))
        st.enter_context(mock.patch.object(server, 'store', s))
        try: out = concierge.say(s, q.text, key=key, llm=demo.brain(store=s))
        except Exception as e: out = {'say': f'RAISED {type(e).__name__}: {e}'}
    said = str(out.get('say') or '')
    line = demo_line(said, out)
    return {'grade': 'right' if line == 'out' else 'bare-Next' if said.strip() == 'Next.' else 'wrong', 'line': line, 'say': said}


def run_all() -> list:
    # One seeding, not two a turn: seeding ~1,200 worlds was most of run_all's 3 minutes, and past pytest's faulthandler_timeout
    # (120 s) its watchdog dumps every thread's stack while the main thread runs - which on Windows CI crashed the run with an
    # access violation in whatever the main thread was doing (_strptime, a store read), or left it too slow for the job's 25 minutes
    _SEEDED[:] = [_world()]
    try: return [{'q': q, 'ideal': ideal_turn(q), 'demo': demo_turn(q)} for q in CASES]
    finally: _SEEDED.clear()


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
    if dbad: out += ['', 'DEMO WRONG:'] + [f"  [{r['q'].cat}] {r['q'].text!r} wants out got {r['demo']['line']} - {r['demo']['say'][:110]!r}" for r in dbad]
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
        # ...and Watch it, whose tool a phone's yes now runs as the row's own task.watching (concierge, the phone audit 2026-11-02)
        rows.append((v, tool or 'button.light', tool or {'watch': 'task.watch'}.get(v, '')))
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
