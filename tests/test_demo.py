"""The demo: the whole app, none of the world.

A product whose point is connectors cannot be shown by screenshots, and cannot be shown by a
real instance either - a public Taskuary with a mailbox behind it is somebody's mailbox on the
internet. So it is the real application over invented data, with every door out nailed shut at
the API layer.

These tests are the lock. They check what is REFUSED, not what is hidden: a button that does
nothing is a design, a deny list is a control - and the list is written so that an endpoint
added next month is refused until somebody decides otherwise.
"""
import os
import time, unittest
from unittest import mock

from taskuary import demo
from taskuary.store import MemoryStore


def on():
    return mock.patch.dict(os.environ, {demo.FLAG: '1'})


class OffByDefaultTests(unittest.TestCase):
    def test_a_normal_install_is_not_a_demo(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(demo.FLAG, None)
            self.assertFalse(demo.enabled())
            self.assertEqual(demo.refuse('POST', '/api/connectors'), '')   # refuses nothing at all

    def test_the_flag_is_read_the_way_people_write_it(self):
        for value, want in (('1', True), ('true', True), ('YES', True), ('on', True),
                            ('0', False), ('', False), ('no', False)):
            with mock.patch.dict(os.environ, {demo.FLAG: value}):
                self.assertEqual(demo.enabled(), want, value)


class TheDoorsAreShutTests(unittest.TestCase):
    def test_nothing_sends(self):
        with on():
            for path in ('/api/reviews/3/send', '/api/review/3/send', '/api/tasks/7/handoff', '/api/reviews/3/decide'):
                self.assertIn('nothing is sent', demo.refuse('POST', path), path)

    def test_no_connector_can_be_made_edited_or_given_a_secret(self):
        with on():
            for path in ('/api/connectors', '/api/connectors/3', '/api/connectors/3/test',
                         '/api/connectors/3/ai-setup', '/api/connectors/3/wa/bridge/start'):
                self.assertTrue(demo.refuse('POST', path), path)

    def test_no_tool_runs_against_anything(self):
        with on():
            self.assertTrue(demo.refuse('POST', '/api/tools/run'))
            self.assertTrue(demo.refuse('POST', '/api/agents/coding/test'))

    def test_no_cli_starts_on_the_machine_this_is_hosted_on(self):
        with on():
            self.assertTrue(demo.refuse('POST', '/api/terminals'))
            self.assertTrue(demo.refuse('DELETE', '/api/terminals/abc'))
            self.assertTrue(demo.refuse('PUT', '/api/agents/coding'))

    def test_nothing_is_fetched_or_received(self):
        with on():
            for path in ('/api/sync', '/api/ingest/push', '/api/hooks/claude', '/api/msauth/start'):
                self.assertTrue(demo.refuse('POST', path), path)

    def test_the_greeting_when_a_visitor_sits_down_is_the_demo_itself(self):
        # refused, the demo never said good morning: the arrive ping only writes the demo's own chat
        with on(): self.assertFalse(demo.refuse('POST', '/api/concierge/arrive'))

    def test_an_endpoint_nobody_thought_about_is_refused_by_default(self):
        """The list says what MAY happen. Anything else - including something added next month -
        is refused until somebody decides it is safe."""
        with on():
            self.assertTrue(demo.refuse('POST', '/api/something/invented/tomorrow'))
            self.assertTrue(demo.refuse('DELETE', '/api/tasks/3'))

    def test_reading_is_always_allowed(self):
        with on():
            for path in ('/api/feed', '/api/connectors', '/api/tools/run', '/api/terminals'):
                self.assertEqual(demo.refuse('GET', path), '', path)


class TheDemoStillWorksTests(unittest.TestCase):
    """A demo that cannot be used is a screenshot. Everything the visitor is there to try has
    to work - the triage verdicts, the chat, the board's wall, making a task."""
    def test_the_funnel_and_the_chat_are_usable(self):
        with on():
            for path in ('/api/tasks', '/api/tasks/3', '/api/messages/9/file',
                         '/api/tasks/3/assistant/messages', '/api/tasks/3/assistant/stream',
                         '/api/board/notes', '/api/tasks/3/comments'):
                self.assertEqual(demo.refuse('POST', path), '', path)

    def test_the_walk_is_something_a_visitor_can_actually_take(self):
        """It is a tour of the app that touches nothing real - which is the entire demo. The
        checklist stays hidden there (TaskHubPage hides SetupChip), because a list of connections
        nobody can make is not a demo of anything."""
        with on():
            for path in ('/api/setup/walk', '/api/setup/walk/reset', '/api/setup/seen'):
                self.assertEqual(demo.refuse('POST', path), '', path)

    def test_the_walk_being_open_does_not_open_the_connectors(self):
        with on():
            self.assertNotEqual(demo.refuse('POST', '/api/connectors'), '')


class TheCardsOwnButtonsTests(unittest.TestCase):
    """U8 (2026-10-17): Mark done, Remind me and a draft were refused with "Report this bug" under them. They write the demo's own
    database and nothing else, so they work; Start and Send stay shut, and every refusal is said as the demo, in plain words."""
    def test_done_remind_and_a_draft_are_allowed(self):
        with on():
            for path in ('/api/concierge/propose', '/api/operations', '/api/tasks/3/remind', '/api/messages/9/reply', '/api/reviews/4/draft'):
                self.assertEqual(demo.refuse('POST', path), '', path)
            self.assertEqual(demo.refuse('PATCH', '/api/operations/abc'), '')

    def test_the_task_views_road_reaches_the_kind_check(self):
        """The task view and the cards propose through /api/operations (taskOps.runOperation), not the chat's
        /api/concierge/propose: only the chat's door was allowed, so Mark done from a card was refused (2026-10-18)."""
        import pathlib, re
        src = (pathlib.Path(__file__).parents[1] / 'website/src/taskOps.js').read_text(encoding='utf-8')
        posted = {re.sub(r'\$\{[^}]+\}', 'x', p) for p in re.findall(r'api\.post\(`?"?(/api/[^"`,]+)', src)}
        assert posted, 'taskOps.js posts nowhere?'
        with on(), mock.patch.object(demo, '_store', lambda: None):
            for path in posted:
                if path.endswith('/execute'): continue                      # judged by the proposal's kind (above)
                self.assertEqual(demo.refuse('POST', path), '', path)

    def test_a_confirmed_proposal_runs_by_its_kind(self):
        from taskuary import operations
        s = MemoryStore(); t = s.create_task({'Title': 'Order new badges', 'Status': 'open'}, 'owner')
        m = s.add_message({'ConversationId': 'c1', 'Channel': 'email', 'Subject': 'Badges', 'FromEmail': 'erin@northwind.example',
                           'BodyText': 'can you order them?', 'Status': 'routed', 'TaskId': t})
        done = operations.propose(s, 'task.complete', t, {}, 'owner')['id']
        later = operations.propose(s, 'task.defer', t, {'until': '2026-12-01'}, 'owner')['id']
        start = operations.propose(s, 'dispatch.prepare', t, {'kind': 'coding'}, 'owner')['id']
        agent = operations.propose(s, 'task.create_from_message', m, {'kind': 'coding'}, 'owner')['id']
        mine = operations.propose(s, 'task.create_from_message', m, {'kind': 'task'}, 'owner')['id']
        run = lambda oid: demo.refuse('POST', f'/api/operations/{oid}/execute', store=s)
        with on():
            self.assertEqual((run(done), run(later), run(mine)), ('', '', ''))
            self.assertEqual((run(start), run(agent)), (demo.STARTS, demo.STARTS))
            self.assertEqual(run('no-such-proposal'), '')                    # the handler's own 404 says so

    def test_without_a_store_to_read_the_kind_it_stays_shut(self):
        with on(), mock.patch.object(demo, '_store', lambda: None):
            self.assertEqual(demo.refuse('POST', '/api/operations/abc/execute'), demo.OFF)

    def test_every_refusal_is_said_as_the_demo_in_plain_words(self):
        with on():
            for path in ('/api/connectors', '/api/tools/run', '/api/reviews/3/send', '/api/terminals', '/api/tasks/3/dispatch',
                         '/api/sync', '/api/doc/soul', '/api/something/invented'):
                why = demo.refuse('POST', path)
                self.assertTrue(why.startswith('This is the demo - '), (path, why))
                for word in ('CLI', 'triage', 'session', 'timeline', 'operator'): self.assertNotIn(word, why, (path, why))


class TheScriptedBrainTests(unittest.TestCase):
    def test_it_answers_without_a_key_a_cli_or_a_network(self):
        said = demo.brain()('you are an assistant', 'CONVERSATION\nUSER: what should I do first?')
        self.assertIn('You asked', said)
        self.assertIn('what should I do first?', said)

    def test_it_quotes_only_what_the_person_typed(self):
        said = demo.brain()('sys', 'TASK TQ-1\nSOUL.md: secrets and documents\nUSER: hello there')
        self.assertNotIn('SOUL.md', said)
        self.assertIn('hello there', said)

    def test_triage_still_gets_the_json_it_expects(self):
        import json
        out = json.loads(demo.brain()('Answer ONLY with JSON: {"intent": ...}', 'a message'))
        self.assertIn(out['intent'], ('fyi', 'task', 'reply_only'))

    def test_the_advisor_gets_one_offered_verb_and_a_plain_line(self):
        """B17 (2026-10-17): the Advisor's prompt says JSON, so it got triage's {"intent": "fyi"} and the demo never showed one
        suggestion. It names an offered verb someone waiting makes right - and on a newsletter, like the real one, nothing."""
        import json
        ask = lambda verbs: json.loads(demo.brain()('Answer with JSON only', f'EVENT: item.shown\n\nVERBS OFFERED: {verbs}'))
        out = ask('close (Mark done), reply (Reply), defer (Remind me)')
        self.assertEqual(out['verb'], 'reply'); self.assertLessEqual(len(out['line']), 80); self.assertTrue(out['line'])
        self.assertEqual(ask('mine (Make a task), regular_agent (Send to agent), not_ours (Not ours)')['verb'], None)

    def test_the_canned_count_is_the_rails_own(self):
        """B23: "Three things are waiting on you" stood beside a rail of nine - and "25 things are on it, and 5 are waiting" beside an
        ON YOU of 9 (2026-10-19 UI walk): the count is the ON YOU band's, the greeting's own (lanes.on_you)."""
        from taskuary import funnel, lanes
        s = MemoryStore(); demo.seed(s)
        with mock.patch('taskuary.terminal.live_sessions', lambda tail=0: []):
            funnel.invalidate(); n = sum(map(lanes.on_you, funnel.pile(s, force=True)['items']))
            self.assertTrue(demo._list_line(s).startswith(f'{n} things are on you'), demo._list_line(s))
        funnel.invalidate()
        self.assertNotIn('Three', ' '.join(demo.CANNED))

    def test_the_answer_fits_the_ask_read_by_the_concierges_own_words(self):
        """2026-10-19 UI walk: it grepped for "USER: " while the concierge writes concierge.OWNER_SAYS, so every ask got one random line."""
        from taskuary import concierge
        ask = lambda q: demo.brain(store=MemoryStore())('You are the assistant.', f'THE RAIL\n\n{concierge.OWNER_SAYS}{q}\nAnswer them, briefly.')
        plate, draft, weather = ask('what is on my plate today'), ask('draft a reply to the invoice'), ask("what's the weather")
        self.assertEqual(len({plate, draft, weather}), 3, (plate, draft, weather))
        self.assertTrue(plate.startswith('I looked at your list.'), plate)
        self.assertIn('Reply', draft)
        self.assertTrue(weather.startswith(demo.OUT_OF_SCRIPT) and "what's the weather" in weather, weather)

    def test_a_line_fires_on_its_ask_never_on_a_word_it_shares(self):
        """The 2026-10-20 query walk: "run the end of day report" was asked for a schedule, and a meeting, a list entry and a task by name
        were all answered with the rail's count."""
        from taskuary import concierge
        ask = lambda q: demo.brain(store=MemoryStore())('You are the assistant.', f'{concierge.OWNER_SAYS}{q}\nAnswer them, briefly.')
        for q in ('when is my next meeting?', 'put it on my list', 'show me the new starter task', 'next'):
            self.assertTrue(ask(q).startswith(demo.OUT_OF_SCRIPT), (q, ask(q)))
        # ...a report is brought up, never the schedule line it shares "day" with
        self.assertRegex(ask('run the end of day report'), r'^Here: \[End of day[^\]]*\]\(#report=\d+\)\.$')
        for q in ("what's waiting on me", 'summarize my day', 'how many open tasks do I have'):
            self.assertTrue(ask(q).startswith('I looked at your list.'), (q, ask(q)))
        self.assertEqual(ask('every monday send me the overdue invoices'), demo.CANNED[2])

    def test_a_draft_is_a_reply_never_a_canned_chat_line(self):
        """2026-10-19 UI walk: TQ-0001's demo draft read "I looked at your list. 25 things are on it..." - the responder's prompt
        was answered from CANNED."""
        from taskuary import responder
        write = lambda subject, frm: demo.brain()(responder.SYSTEM.format(owner='Dana'), f'Subject: {subject}\nFrom: {frm}\n\nthe thread')
        self.assertEqual(write('Invoice 88213 - past due', 'Tom Alvarez <talvarez@vendor.example>'), demo.DRAFTS['Invoice 88213 - past due'])
        other = write('Month-end close is short by 4,180', 'Marcus Reed <mreed@northwind.example>')
        self.assertTrue(other.startswith('Thanks Marcus'), other)
        canned = {c.split('{')[0] for c in demo.CANNED}
        for d in (other, *demo.DRAFTS.values()): self.assertFalse(any(d.startswith(c) for c in canned), d)


class TheScriptedBrainRoutesTests(unittest.TestCase):
    """The UX walk, 2026-10-22: the demo chat was a dead end for anything but two phrases, so a visitor never saw the Assistant's
    routing - it brings up the item, the report or the lit button, the way a good model's CALL or link would (demo._route)."""
    @classmethod
    def setUpClass(cls):
        cls.s = MemoryStore()
        with mock.patch('taskuary.terminal.live_sessions', lambda tail=0: []): demo.seed(cls.s)

    def ask(self, q):
        from taskuary import concierge
        return demo.brain(store=self.s)('You are the assistant.', f'THE RAIL\n\n{concierge.OWNER_SAYS}{q}\nAnswer them, briefly.')

    def test_mark_done_and_remind_me_call_the_real_buttons(self):
        import json
        call = lambda q: json.loads(self.ask(q).removeprefix('CALL: '))
        self.assertEqual(call('mark this done'), {'kind': 'close', 'params': {}})
        self.assertEqual(call('done.'), {'kind': 'close', 'params': {}})
        self.assertEqual(call('remind me about this on friday at 2pm'), {'kind': 'task.defer', 'params': {'until': 'friday at 2pm'}})
        self.assertEqual(call('remind me later'), {'kind': 'task.defer', 'params': {}})

    def test_not_a_task_a_note_a_hand_off_and_a_chase_call_the_real_tools(self):
        """F5: the visitor's other put-downs and hand-offs reach the same road the real Assistant's CALL takes."""
        import json
        call = lambda q: json.loads(self.ask(q).removeprefix('CALL: '))
        self.assertEqual(call('this is not a task'), {'kind': 'task.not_a_task', 'params': {}})
        self.assertEqual(call('close this with a note: called Marcus, sorted'), {'kind': 'task.complete', 'params': {'note': 'called Marcus, sorted'}})
        self.assertEqual(call('hand this to Priya Shah'), {'kind': 'task.handoff', 'params': {'who': 'Priya Shah'}})
        self.assertEqual(call('pass it to Marcus'), {'kind': 'task.handoff', 'params': {'who': 'Marcus'}})
        self.assertEqual(call('chase them'), {'kind': 'chase', 'params': {}})

    def test_a_ref_a_subject_or_a_name_brings_the_item_up(self):
        self.assertEqual(self.ask('open TQ-0004'), 'Here: [TQ-0004](#task=4).')
        self.assertEqual(self.ask('open the invoice 88213 task'), 'Here: [TQ-0004](#task=4).')
        self.assertEqual(self.ask("pull up Marcus's month-end close"), 'Here: [TQ-0001](#task=1).')
        self.assertTrue(self.ask('open TQ-9999').startswith(demo.OUT_OF_SCRIPT))              # no such task: never a dead link

    def test_a_report_brings_up_that_report_or_reports(self):
        self.assertEqual(self.ask('what did the helpdesk report say?'), 'Here: [Helpdesk tickets by day, last 14](#report=6).')
        self.assertEqual(self.ask('list my reports'), 'Here: [Reports](#report=reports).')

    def test_a_set_a_person_to_act_toward_and_a_shared_word_bring_nothing_up(self):
        for q in ('close all the tasks from Priya', 'clear all the reports', 'forward this to Priya', 'tell Marcus I will look at it',
                  'the sync interval', 'mark all the approvals as done'):
            self.assertFalse(self.ask(q).startswith(('Here:', 'CALL:')), (q, self.ask(q)))


class TheAdvisorSpeaksInTheDemoTests(unittest.TestCase):
    def test_an_item_on_the_table_gets_a_verb(self):
        """The demo is where newcomers first meet the Advisor: an ask has its button lit - and, its move plain, nothing said (the owner,
        2026-10-23: an obvious move is an empty strip and one lit button)."""
        from taskuary import advisor, funnel
        s = MemoryStore(); demo.seed(s)
        with on(), mock.patch('taskuary.terminal.live_sessions', lambda tail=0: []):
            funnel.invalidate()
            keys = [i['key'] for i in funnel.pile(s, force=True)['items'] if i.get('lane') == 'approve' or i.get('kind') in ('asked', 'todo')]
            self.assertTrue(keys)
            tgt = advisor.target_of(s, keys[0])
            advisor.judge(s, advisor.SHOWN, *tgt, advisor.revision(s, *tgt), tier=2, key=keys[0])
            got = advisor.for_key(s, keys[0])
        funnel.invalidate()
        self.assertTrue(got.get('verb'), got); self.assertNotIn('pending', got)


class TheWorldTests(unittest.TestCase):
    def test_the_seed_builds_a_morning_worth_looking_at(self):
        s = MemoryStore()
        self.assertGreaterEqual(demo.seed(s), 5)
        rows = s.feed(limit=50)
        self.assertGreaterEqual(len(rows), 5)
        self.assertTrue(any(r.get('RouteReason') for r in rows))        # verdicts with their reasons
        self.assertIn('Dana Whitfield', s.get_doc('soul') or '')
        self.assertGreaterEqual(len(s.notes()), 3)                      # ...and a wall to read

    def test_every_item_reads_like_a_person_wrote_it(self):
        """The public demo showed a task titled "the badge printer" over a mail about the Q3 numbers, a body
        of "x", and "and one more thing 1" - the regression desk's placeholders, and subjects renamed in scan
        order onto the wrong rows (2026-09-23). Every message has a sender and real words, and an open task's
        first message is about the task."""
        s = MemoryStore()
        demo.seed(s)
        for m in s.scan_messages(100):
            m = s.get_message(m['MessageId'])
            self.assertNotIn(m.get('Subject'), ('please look', None, ''), m)
            self.assertGreater(len(m.get('BodyText') or ''), 8, m)
            self.assertNotIn('one more thing', m.get('BodyText') or '')
            self.assertTrue(m.get('FromName') or m.get('FromEmail'), m)
        for t in s.list_tasks():
            first = (s.list_messages(t['TaskId']) or [None])[0]
            if first and t['Status'] not in ('done', 'dropped'):
                words = lambda x: set(x.lower().replace('#', ' ').split()) - {'-', 'the', 'a', 'on', 're:'}
                self.assertTrue(words(t['Title']) & words(first['Subject'] or ''), (t['Title'], first['Subject']))

    def test_it_refuses_to_write_over_a_home_that_has_work_in_it(self):
        s = MemoryStore()
        s.create_task({'Title': 'a real task'}, 'o')
        self.assertEqual(demo.seed(s), 0)

    def test_nobody_real_is_in_it(self):
        """Every address in the demo world is on a RESERVED domain. This used to name the one real
        domain it was guarding against, which put that domain in the repository the guard exists to
        keep it out of; the invariant catches any real domain, including the ones nobody thought of."""
        import re
        s = MemoryStore()
        demo.seed(s)
        blob = ' '.join(str(r) for r in s.feed(limit=50)) + (s.get_doc('soul') or '') + (s.get_doc('job') or '')
        found = set(re.findall(r'[\w.+-]+@([\w.-]+)', blob))
        self.assertTrue(found, 'the demo world has addresses in it')
        # RFC 2606's reserved names, and anything under one of them (vendor.example.com)
        ok = ('.example', '.test', '.invalid', '.localhost', 'example.com', 'example.net', 'example.org')
        for domain in found:
            self.assertTrue(domain.endswith(ok) or '.example.' in domain,
                            f'{domain} is not a reserved domain - the demo may only invent people')

    def test_the_accounting_task_is_a_general_agents_conversation(self):
        """B23: the GL reconciliation was seeded as coding, so an accountant's task opened as a terminal."""
        from taskuary import general
        s = MemoryStore(); demo.seed(s)
        gl = next(t for t in s.list_tasks() if t['Title'] == 'Reconcile the August GL export')
        self.assertEqual(gl['Kind'], 'general')
        said = [c['Body'] for c in s.list_comments(gl['TaskId']) if c.get('ActorType') == general.ASSISTANT_TYPE]
        self.assertTrue(any('4,180' in b for b in said), said)

    def test_a_reply_that_asked_something_is_not_filed_as_fyi(self):
        """B23: history replies were seeded routed with no task, so "can you approve the Fairhaven PO?" sat under the fyi as
        "Nothing to decide". Each is answered on a closed task of its own, like triage makes it."""
        s = MemoryStore(); demo.seed(s)
        for days, hour, channel, who, subject, body, verdict, why in demo.HISTORY:
            if verdict != 'reply': continue
            m = next(x for x in (s.get_message(r['MessageId']) for r in s.scan_messages(200)) if x.get('BodyText') == body)
            self.assertTrue(m.get('TaskId'), body)
            self.assertEqual((s.get_task(m['TaskId']) or {}).get('Status'), 'done', body)

    def test_each_agent_replays_its_own_work(self):
        """B23: every agent task replayed the month-end transcript, whatever it was about."""
        from taskuary import terminal
        s = MemoryStore(); demo.seed(s)
        with mock.patch.object(terminal, 'SESSIONS', {}), mock.patch.object(demo, 'Replay', lambda st, tid, lines=None: mock.Mock(task_id=tid, sid=str(tid), lines=lines)):
            demo.start_sessions(s)
            shown = {s.get_task(r.task_id)['Title']: r.lines for r in terminal.SESSIONS.values()}
        self.assertTrue(shown)
        self.assertEqual(len({str(v) for v in shown.values()}), len(shown))
        for title, lines in shown.items():
            self.assertNotIn('4,180', ' '.join(t for t, _ in lines), title)   # the month-end difference belongs to the GL task

    def test_a_replayed_session_looks_like_a_session(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'the export', 'Kind': 'coding'}, 'o')
        r = demo.Replay(s, tid, lines=[('working…', 0.01), ('done', 0.01)])
        info = r.info(tail=2)
        self.assertEqual((info['taskId'], info['mode'], info['alive']), (tid, 'demo', True))
        self.assertIn('phase', info)
        r.close()
        self.assertFalse(r.alive)

    def test_a_replay_asking_carries_its_question_like_a_real_session(self):
        """The run's word outranks the screen for a replay too (terminal.worker_fields): a question recorded on it is the request the
        rail shows and an answer binds to - it read "waiting" with no request, so nothing could show or answer the question (G7)."""
        from taskuary import workerstate
        s = MemoryStore()
        tid = s.create_task({'Title': 'the export', 'Kind': 'coding'}, 'o')
        with mock.patch.object(demo.Replay, '_play'): r = demo.Replay(s, tid)
        try:
            workerstate.record(s, tid, r.sid, 'working')
            self.assertEqual((r.info()['waiting'], r.info()['state']), (False, None))
            workerstate.record(s, tid, r.sid, 'input_needed', text='Keep the inter-company rows?')
            i = r.info()
            self.assertEqual((i['waiting'], i['state'], i['request']['text']), (True, 'asking', 'Keep the inter-company rows?'))
            self.assertIn('Keep the inter-company rows?', i['line'])
        finally: r.close()

    def test_a_replay_says_when_it_moves(self):
        """Stopping to wait, and being closed, are session transitions: each wakes the views as a real run's events do (G7)."""
        from taskuary import live
        s = MemoryStore()
        tid = s.create_task({'Title': 'the export', 'Kind': 'coding'}, 'o')
        with mock.patch.object(live, 'emit') as emit:
            r = demo.Replay(s, tid, lines=[('working…', 0.01)])
            for _ in range(200):
                if not r.busy: break
                time.sleep(0.01)
            self.assertFalse(r.busy)
            self.assertIn(mock.call('task-changed', task_id=tid), emit.call_args_list)
            emit.reset_mock(); r.close()
            emit.assert_any_call('task-changed', task_id=tid)

    def test_the_replay_takes_no_dictation(self):
        """It is a recording. Typing at it must not pretend to reach an agent."""
        s = MemoryStore()
        r = demo.Replay(s, 1, lines=[('x', 0.01)])
        r.write('rm -rf /\\n')                                            # goes nowhere, by design
        self.assertNotIn('rm -rf', r.scrollback())



class TheSameWorldAtEveryHourTests(unittest.TestCase):
    def test_the_pile_is_the_same_whenever_the_demo_is_opened(self):
        """Before mid-afternoon the fyi seeded 14 and 17 hours back kept stamps across midnight, outside the pipe's twelve hours, and
        the demo held two fyi at 08:00 and four at 18:00 (tests/assistant_queries.py, 2026-10-21). The morning is spread from now."""
        from datetime import datetime, timedelta
        from taskuary import funnel, terminal
        from tests.fake_clock import fake_clock
        day = (datetime.now() - timedelta(days=1)).replace(second=0, microsecond=0)     # in the past: SQLite's 'now' is the real one
        seen = {}
        with mock.patch.object(terminal, 'live_sessions', return_value=[]): demo.seed(MemoryStore())     # its lazy imports, loaded
        for h, mi in ((1, 0), (8, 0), (13, 0), (23, 30)):
            with fake_clock(day.replace(hour=h, minute=mi)), mock.patch.object(terminal, 'live_sessions', return_value=[]):
                funnel.invalidate(); funnel.forget_states(); funnel._SOURCES.update(at=0.0, by={})
                s = MemoryStore(); demo.seed(s); funnel.invalidate()
                seen[f'{h:02d}:{mi:02d}'] = sorted((i['kind'], i['key']) for i in funnel.build(s)['items'])
        funnel.invalidate()
        first = next(iter(seen.values()))
        self.assertEqual(sum(k == 'fyi' for k, _ in first), 4, first)
        for at, pile in seen.items(): self.assertEqual(pile, first, at)


if __name__ == '__main__':
    unittest.main()


class TheOwnerIsAtNorthwindTests(unittest.TestCase):
    def test_a_colleague_is_not_a_stranger(self):
        """The demo owner had no address, so no domain of their own, and every colleague at Northwind was a stranger (the UX walk,
        2026-10-22). The owner's mailbox is at the colleagues' company; a vendor stays outside it."""
        from taskuary import senders
        s = MemoryStore()
        with mock.patch('taskuary.terminal.live_sessions', lambda tail=0: []): demo.seed(s)
        self.assertEqual(s.owner()['owner_email'], demo.OWNER_EMAIL)
        self.assertTrue(demo.OWNER_EMAIL.endswith('@northwind.example'))
        self.assertIn('northwind.example', senders.own_domains(s))
        self.assertNotIn('vendor.example', senders.own_domains(s))
        from taskuary import origin
        by = {t['TaskId']: (s.last_inbound_on_task(t['TaskId']) or {}).get('FromEmail') or '' for t in s.list_tasks()}
        colleague = next(t for t, e in by.items() if e.endswith('@northwind.example'))
        vendor = next(t for t, e in by.items() if e.endswith('@vendor.example'))
        self.assertEqual(origin.of_task(s, colleague)[0], 'trusted')
        self.assertEqual(origin.of_task(s, vendor)[0], 'stranger')
