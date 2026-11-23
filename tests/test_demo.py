"""The demo: the whole app, none of the world.

A product whose point is connectors cannot be shown by screenshots, and cannot be shown by a
real instance either - a public Taskuary with a mailbox behind it is somebody's mailbox on the
internet. So it is the real application over invented data, with every door out nailed shut at
the API layer.

These tests are the lock. They check what is REFUSED, not what is hidden: a button that does
nothing is a design, a deny list is a control - and the list is written so that an endpoint
added next month is refused until somebody decides otherwise.
"""
import os, re
import tempfile, time, unittest
from pathlib import Path
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
            for path in ('/api/reviews/3/send', '/api/review/3/send', '/api/tasks/7/handoff'):
                self.assertIn('nothing is sent', demo.refuse('POST', path), path)
            # ...a card's verdict is judged by its verb: approving one sends it, and putting it down sends nothing - Dismiss on a post
            # answered "nothing is sent" and the card stayed (the walk, 2026-11-15)
            self.assertEqual(demo.refuse('POST', '/api/reviews/3/decide'), '')
            for verb in ('approve', 'edit', 'merge_anyway', 'close_pr'): self.assertIn('nothing is sent', demo.refuse_verdict(verb), verb)
            # ...a LETTER's Send is played, not refused (the owner, 2026-11-15); a push or a merge is never a letter
            for verb in ('approve', 'edit'): self.assertEqual(demo.refuse_verdict(verb, 'draft_reply'), '', verb)
            for verb in ('merge_anyway', 'close_pr'): self.assertIn('nothing is sent', demo.refuse_verdict(verb, 'draft_reply'), verb)
            for verb in ('reject', 'no_reply', 'close_unsent'): self.assertEqual(demo.refuse_verdict(verb), '', verb)
        self.assertEqual(demo.refuse_verdict('approve'), '', 'outside the demo nothing is refused here')

    def test_dismiss_puts_a_card_down_and_send_is_still_refused_as_the_demo(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); demo.seed(s)
        rid = s._one("SELECT ReviewId FROM review WHERE Kind='action' AND Status='pending' ORDER BY ReviewId LIMIT 1")['ReviewId']
        with on(), mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            r = c.post(f'/api/reviews/{rid}/decide', json={'verb': 'approve'})
            self.assertEqual((r.status_code, r.json().get('demo')), (403, True)); self.assertIn('nothing is sent', r.json()['detail'])
            self.assertEqual(s.get_review(rid)['Status'], 'pending')
            r = c.post(f'/api/reviews/{rid}/decide', json={'verb': 'reject'})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(s.get_review(rid)['Status'], 'rejected')

    def test_send_on_a_letter_is_played_the_card_settles_and_a_recorded_line_follows(self):
        # the owner, 2026-11-15: the tour says "press Send - nothing leaves the demo", and the press drew a red refusal on the card
        from fastapi.testclient import TestClient
        from taskuary import outbound, server
        s = MemoryStore(); demo.seed(s)
        rv = s._one("SELECT r.* FROM review r JOIN message m ON m.MessageId=r.MessageId WHERE r.Kind='draft' AND r.Status='pending' AND r.TaskId IS NOT NULL "
                    "AND IFNULL(r.DraftText,'')<>'' AND m.Channel='email' ORDER BY r.ReviewId LIMIT 1")
        gone = mock.Mock(side_effect=AssertionError('nothing leaves the demo'))
        with on(), mock.patch.object(server, 'store', s), mock.patch.object(outbound, 'send_out', gone), mock.patch.object(outbound, 'reply_to_message', gone):
            r = TestClient(server.app).post(f"/api/reviews/{rv['ReviewId']}/decide", json={'verb': 'approve'})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual((r.json()['ok'], (r.json()['sent'] or {}).get('demo')), (True, True), r.text)
        self.assertIn(s.get_review(rv['ReviewId'])['Status'], ('approved', 'sent'))
        said = [c['Body'] for c in s.list_comments(rv['TaskId'])]
        self.assertEqual(said.count(demo.AFTER_SEND), 1, 'the recorded agent says what would happen next, once')
        self.assertIsNone(s.last_worker_event(rv['TaskId'], kinds=('failed',)), 'and no agent is woken to fail on "No AI is connected"')
        gone.assert_not_called()


    def test_the_draft_the_tour_points_at_can_be_sent(self):
        # ...its redraft stayed pinned to the first mail, so it read as stale: Redraft alone, and no AI in the demo to redraft with
        from taskuary import verdicts
        s = MemoryStore(); demo.seed(s)
        rv = s._one("SELECT r.* FROM review r JOIN task t ON t.TaskId=r.TaskId WHERE t.Title='September overtime by site' AND r.Status='pending'")
        self.assertFalse(verdicts.context_moved(s, rv)[0], 'the reply answers her newest mail')

    def test_no_connector_can_be_made_edited_or_given_a_secret(self):
        with on():
            for path in ('/api/connectors', '/api/connectors/3', '/api/connectors/3/test',
                         '/api/connectors/3/ai-setup', '/api/connectors/3/wa/bridge/start'):
                self.assertTrue(demo.refuse('POST', path), path)

    def test_no_tool_runs_against_anything(self):
        with on():
            self.assertTrue(demo.refuse('POST', '/api/tools/run'))

    def test_no_cli_starts_on_the_machine_this_is_hosted_on(self):
        with on():
            self.assertTrue(demo.refuse('POST', '/api/terminals'))
            self.assertTrue(demo.refuse('DELETE', '/api/terminals/abc'))

    def test_nothing_is_fetched_or_received(self):
        with on():
            for path in ('/api/sync', '/api/ingest/push', '/api/hooks/claude', '/api/msauth/start'):
                self.assertTrue(demo.refuse('POST', path), path)

    def test_the_greeting_when_a_visitor_sits_down_is_the_demo_itself(self):
        # refused, the demo never said good morning: the arrive ping only writes the demo's own chat
        with on(): self.assertFalse(demo.refuse('POST', '/api/concierge/arrive'))

    def test_link_opens_the_running_demo_signed_in(self):
        # `taskuary --demo --link` asks the running demo for a one-time key: refused, it printed a bare address whose page
        # said "Open Taskuary from its app" - the demo could only be opened by the process that started it
        with on(): self.assertFalse(demo.refuse('POST', '/api/launch-key'))

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
        self.assertEqual(demo.brain()('you are an assistant', 'CONVERSATION\nUSER: what should I do first?'), demo.OUT_OF_SCRIPT)

    def test_it_never_quotes_the_prompt_back(self):
        said = demo.brain()('sys', 'TASK TQ-1\nSOUL.md: secrets and documents\nUSER: hello there')
        self.assertNotIn('SOUL.md', said)

    def test_triage_still_gets_the_json_it_expects(self):
        import json
        out = json.loads(demo.brain()('Answer ONLY with JSON: {"intent": ...}', 'a message'))
        self.assertIn(out['intent'], ('fyi', 'task', 'reply_only'))


    def test_a_json_ask_without_a_script_never_gets_triages_answer(self):
        """The walk, 2026-11-18: Change > Split or merge read "The AI reads this as one job - the demo files everything it is not sure
        about": every JSON ask was answered with triage's verdict, and its reason was quoted wherever a `why` is drawn. An ask the
        script has no answer for finds nothing; triage still gets its verdict."""
        from taskuary import reshape
        s = MemoryStore(); demo.seed(s)
        tid = next(t['TaskId'] for t in s.list_tasks() if t['Title'] == 'Trainly renewal - how many seats?')
        out = reshape.propose_split(s, tid, demo.brain(store=s))
        self.assertFalse(out['two'])
        self.assertNotIn('files everything', out['why'])
        self.assertNotIn('intent', demo.brain()(reshape.SPLIT_SYSTEM, '{}'))

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


class TheDemoChatAnswersItsSuggestionsTests(unittest.TestCase):
    """The owner, 2026-10-28: the demo chat never decides what typed words mean. Each suggestion is a chip that sends its own words and
    gets the answer recorded for them - by string equality, nothing looser; anything else typed is told so, the suggestions under it."""
    @classmethod
    def setUpClass(cls):
        cls.s = MemoryStore()
        with mock.patch('taskuary.terminal.live_sessions', lambda tail=0: []): demo.seed(cls.s)

    def ask(self, q):
        from taskuary import concierge
        return demo.brain(store=self.s)('You are the assistant.', f'THE RAIL\n\n{concierge.OWNER_SAYS}{q}\nAnswer them, briefly.')

    def test_each_suggestion_gets_its_recorded_answer(self):
        said = {pid: self.ask(ask) for pid, ask, _ in demo.PROMPTS}
        self.assertTrue(said['list'].startswith('I looked at your list.'), said['list'])
        self.assertEqual(said['month_end'], 'Here: [TQ-0001](#task=1).')
        self.assertEqual(said['reports'], 'Here: [Reports](#report=reports).')
        self.assertIn('Reply', said['reply'])
        self.assertEqual(len(set(said.values())), len(demo.PROMPTS), 'each suggestion its own answer')
        self.assertNotIn(demo.OUT_OF_SCRIPT, said.values())

    def test_anything_else_typed_is_the_honest_line_whatever_words_it_shares(self):
        for q in ('mark this done', 'remind me tomorrow', 'open TQ-0004', 'show me the reports', "what's on me right now",
                  'Open the month-end close please', 'hand this to Priya Shah', 'chase them', "what's the weather"):
            self.assertEqual(self.ask(q), demo.OUT_OF_SCRIPT, q)

    def test_a_recording_handed_in_answers_its_own_words_and_no_others(self):
        """The browser tests' stand-in model (demo.ANSWERS_ENV): the same string equality as the suggestions, and never a chip."""
        import json, tempfile
        with tempfile.TemporaryDirectory() as d:
            fn = os.path.join(d, 'answers.json')
            with open(fn, 'w', encoding='utf-8') as f: json.dump({'mark this done': 'CALL: {"kind": "close", "params": {}}'}, f)
            with mock.patch.dict(os.environ, {demo.ANSWERS_ENV: fn}):
                self.assertEqual(self.ask('mark this done'), 'CALL: {"kind": "close", "params": {}}')
                self.assertEqual(self.ask('mark this done please'), demo.OUT_OF_SCRIPT)
                self.assertNotIn('mark this done', [c['ask'] for c in demo.prompt_chips()])

    def test_the_honest_line_carries_the_suggestions_and_a_suggestion_does_not(self):
        from taskuary import concierge
        with mock.patch('taskuary.terminal.live_sessions', lambda tail=0: []):
            out = concierge.say(self.s, 'close all the tasks from Priya', llm=demo.brain(store=self.s))
            # ...the questions in the line's own words too: the Assistant's window draws no chips, and "the suggested questions" named
            # questions nobody could see (the walk, 2026-11-15)
            self.assertEqual(out['say'], demo.OUT_OF_SCRIPT)
            for _, ask, _ in demo.PROMPTS: self.assertIn(f'“{ask}”', out['say'])
            self.assertEqual([c for c in out['chips'] if c.get('prompt')], demo.prompt_chips())
            self.assertTrue(all(c['ask'] == c['label'] for c in demo.prompt_chips()), 'a chip sends exactly the words it shows')
            out = concierge.say(self.s, demo.PROMPTS[2][1], llm=demo.brain(store=self.s))
            self.assertFalse([c for c in out.get('chips') or [] if c.get('prompt')])

    def test_the_honest_line_is_kept_as_it_was_said(self):
        """The walk, 2026-11-18: a visitor typed something off the script, then a suggestion; the chat read its thread again and the
        first answer came back a second time, shorter - the line was kept without the questions the answer had carried, so the page
        could not tell it was the one it had drawn. What is kept is what was said."""
        from taskuary import concierge, general
        s = MemoryStore()
        with mock.patch('taskuary.terminal.live_sessions', lambda tail=0: []):
            demo.seed(s)
            out = concierge.say(s, 'tell me a joke', llm=demo.brain(store=s))
        dock = general.dock_task(s, 'owner')[0]['TaskId']
        kept = [t['text'] for t in concierge.history(s, dock) if t['role'] == 'assistant' and demo.ONLY_SUGGESTED in t['text']]
        self.assertEqual(kept, [out['say']])


class TheAdvisorSpeaksInTheDemoTests(unittest.TestCase):
    def test_an_item_on_the_table_gets_a_verb(self):
        """An item on the table is decided at once, never pending - and NO DEFAULT VERB (the owner, 2026-10-28): a button is lit only
        beside its fact or as the move its state names."""
        from taskuary import funnel, rulebook
        s = MemoryStore(); demo.seed(s)
        with on(), mock.patch('taskuary.terminal.live_sessions', lambda tail=0: []):
            funnel.invalidate()
            keys = [i['key'] for i in funnel.pile(s, force=True)['items'] if i.get('lane') == 'approve' or i.get('kind') in ('asked', 'todo')]
            self.assertTrue(keys)
            got = rulebook.status(s, keys[0])
        funnel.invalidate()
        self.assertTrue(got.get('state'), got); self.assertNotIn('pending', got)
        # ...or the move the state's own fact names (rulebook.MOVES: an ask no agent took lights Send to agent - the owner, 2026-11-10)
        self.assertTrue(not got.get('verb') or got['verb'] == 'next' or got.get('line') or got['state'] in rulebook.MOVES, got)


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

    def test_the_owners_address_is_the_owners(self):
        # About you read "alex@northwind.example · Dana Whitfield": one person under two names (the walk, 2026-11-15)
        first, last = demo.OWNER.lower().split()
        self.assertEqual(demo.OWNER_EMAIL, f'{first[0]}{last}@northwind.example')

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

    def test_a_replays_chat_shows_its_run_and_the_question_its_row_waits_on(self):
        """The walk audit, 2026-11-10: the coding issue's row read "agent waiting on you" over a chat that showed nothing - the replay typed only
        to its screen. It records its run as an ACP session does and ends on its question, so the chat shows what the row says."""
        from taskuary import codingchat, session_artifacts, terminal
        s = MemoryStore()
        tid = s.create_task({'Title': 'the export', 'Kind': 'coding', 'Status': 'open'}, 'o')
        with tempfile.TemporaryDirectory() as d, mock.patch.object(session_artifacts, 'root', lambda: Path(d)), mock.patch.object(terminal, 'SESSIONS', {}):
            r = demo.Replay(s, tid, lines=[(t, 0.001) for t, _ in demo.TRANSCRIPT]); terminal.SESSIONS[r.sid] = r
            for _ in range(500):
                if not r.busy: break
                time.sleep(0.01)
            chat = codingchat.chat(s, tid)
            kinds = [u['sessionUpdate'] for u in chat['sessions'][-1]['updates']]
            self.assertIn('tool_call', kinds); self.assertIn('agent_message_chunk', kinds)
            self.assertEqual((chat['asking'] or {}).get('text'), demo.TRANSCRIPT[-1][0])
            r.close()

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
                # a row's own key is minted when its home starts; the names it answers to are the same in every home
                seen[f'{h:02d}:{mi:02d}'] = sorted((i['kind'], sorted(a for a in i['aliases'] if not a.startswith('processing:'))) for i in funnel.build(s)['items'])
        funnel.invalidate()
        first = next(iter(seen.values()))
        self.assertEqual(sum(k == 'fyi' for k, _ in first), 12, first)
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
        self.assertNotEqual(vendor, colleague)          # ...the vendor is hers to trust by her press (demo.seed vouches for it), never by her domain


class TheDemoOpensOnItsTourTests(unittest.TestCase):
    """The owner, 2026-10-30: "when you open it it first opens on a task list todo to get sense of what it can do"."""
    def seeded(self):
        from taskuary import funnel, terminal
        s = MemoryStore()
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            demo.seed(s); funnel.invalidate()
            items = funnel.pile(s, force=True)['items']
        funnel.invalidate()
        return s, items

    def test_the_tour_leads_the_rail_and_the_walk(self):
        from taskuary import railwalk
        s, items = self.seeded()
        self.assertEqual(items[0]['title'], demo.TOUR, [i['title'] for i in items[:3]])
        self.assertEqual(railwalk.line(items)[0]['title'], demo.TOUR, 'the walk starts at the top of the rail (2026-10-30)')

    def test_it_is_made_last_so_every_other_number_stands(self):
        s, _ = self.seeded()
        tour = next(t for t in s.list_tasks() if t['Title'] == demo.TOUR)
        self.assertEqual(tour['TaskId'], max(t['TaskId'] for t in s.list_tasks() if t.get('SourceRef') != 'assistant:dock'))
        self.assertEqual(s.get_task(1)['Title'], 'Month-end close is short by 4,180')

    def test_it_is_the_owners_own_to_do_that_nobody_waits_on(self):
        from taskuary import origin
        s, _ = self.seeded()
        tour = next(t for t in s.list_tasks() if t['Title'] == demo.TOUR)
        self.assertEqual((tour['Kind'], origin.of_task(s, tour['TaskId'])[0]), ('task', 'owner'))
        self.assertEqual({m['Channel'] for m in s.list_messages(tour['TaskId'])}, {'own'}, 'an own note: no Reply to anyone')

    def test_its_steps_read_top_down_and_name_only_what_the_demo_has(self):
        """The to-do draws newest first (TaskPage), so the steps are stored the other way round. Every row a step names is on the
        rail, and every button it names is a button (buttons.json) - the words the owner sees on the page."""
        import json, re
        from pathlib import Path
        s, items = self.seeded()
        tour = next(t for t in s.list_tasks() if t['Title'] == demo.TOUR)
        self.assertEqual([i['text'] for i in reversed(s.task_checklist(tour['TaskId']))], list(demo.TOUR_STEPS))
        titles = [i['title'] for i in items]
        for step in demo.TOUR_STEPS:
            for named in re.findall(r'"([^"]+)"', step):
                if named.endswith('?'): continue                      # the chat's own suggestion, not a row
                self.assertTrue(any(t.startswith(named) for t in titles), (named, titles))
        labels = {v['label'] for v in json.loads((Path(demo.__file__).with_name('buttons.json')).read_text(encoding='utf-8'))['verbs'].values()}
        for b in ('Next', 'Back', 'Send', 'Remind me', 'Not for me'): self.assertIn(b, labels)
        self.assertIn("What's on me right now?", [ask for _, ask, _ in demo.PROMPTS], 'the chat answers the question the tour asks')

    def test_the_tour_says_what_ticking_its_last_step_does(self):
        """The walk, 2026-11-18: the tour said "ticking the last one closes this task"; every step ticked through the checklist's own road
        (task.check), and the task stayed open on the rail, Mark done lit - the last tick closes nothing (slots.py, 2026-10-18). What it
        says is what a tick does."""
        from taskuary import concierge
        s, _ = self.seeded()
        tour = next(t for t in s.list_tasks() if t['Title'] == demo.TOUR)
        for n in range(len(s.task_checklist(tour['TaskId'])), 0, -1):
            concierge._task_writes(s, tour['TaskId'], 'task.check', tour['TaskId'], {'item': str(n), 'done': True}, 'it', 'owner')
        self.assertTrue(all(i.get('done') for i in s.task_checklist(tour['TaskId'])))
        still_open = s.get_task(tour['TaskId'])['Status'] not in ('done', 'dropped')
        self.assertEqual(still_open, 'Mark done' in demo.TOUR_BODY, demo.TOUR_BODY)
        if still_open: self.assertNotIn('closes this task', demo.TOUR_BODY)

    def test_a_step_that_shows_an_agents_turns_names_a_task_that_has_them(self):
        """The first step sent the visitor to "Month-end close is short by 4,180" to see "Agent is one chat - its turns and what it set
        up": that task has no agent and its chat is the one email. The turns are on the reconciliation's task. And "the draft under Next
        steps" named a heading the chat no longer draws."""
        from taskuary import general
        s, _ = self.seeded()
        step = next(x for x in demo.TOUR_STEPS if 'its turns' in x)
        named, = re.findall(r'"([^"]+)"', step)
        tid = next(t['TaskId'] for t in s.list_tasks() if t['Title'].startswith(named))
        self.assertTrue([c for c in s.list_comments(tid) if c.get('ActorType') == general.ASSISTANT_TYPE], (named, 'has no agent turn'))
        self.assertFalse([x for x in demo.TOUR_STEPS if 'Next steps' in x])

    def test_no_agent_answers_before_the_message_it_answers(self):
        """The invite's agent turn read 11:28 PM under Ruth's invitation stamped 11:46 PM: the seed moved the message's CreatedAt to before
        its turn, and the chat draws its SentAt. On every task the first turn comes after the first message that came in."""
        from taskuary import general
        s, _ = self.seeded()
        late = []
        for t in s.list_tasks():
            got = sorted(str(m.get('SentAt') or '') for m in s.list_messages(t['TaskId']) if m.get('SentAt'))
            said = sorted(str(c['CreatedAt']) for c in s.list_comments(t['TaskId']) if c.get('ActorType') == general.ASSISTANT_TYPE)
            if got and said and said[0] < got[0]: late.append((t['Title'], got[0], said[0]))
        self.assertEqual(late, [])

    def test_the_first_view_opens_on_an_agents_finished_work_never_the_greeting(self):
        s, _ = self.seeded()
        post = next(t for t in s.list_tasks() if t['Title'] == demo.SHOWCASE)
        with on(): self.assertEqual(demo.opens(s), {'tid': post['TaskId']})
        with on(), mock.patch.dict(os.environ, {demo.OPENS_ENV: '0'}): self.assertIsNone(demo.opens(s))
        self.assertIsNone(demo.opens(s), 'never outside the demo')
        s.update_task(post['TaskId'], {'Status': 'done'}, 'owner')
        with on(): got = demo.opens(s)
        self.assertIsNotNone(got, 'a closed showcase opens another open task, not the empty greeting')
        self.assertNotIn(s.get_task(got['tid'])['Status'], ('done', 'dropped'))

    def test_where_do_i_start_brings_up_the_tour(self):
        from taskuary import concierge
        s, _ = self.seeded()
        tid = next(t['TaskId'] for t in s.list_tasks() if t['Title'] == demo.TOUR)
        said = demo.brain(store=s)('You are the assistant.', f'{concierge.OWNER_SAYS}Where do I start?')
        self.assertIn(f'(#task={tid})', said)


class TheGeneralAgentsDayTests(unittest.TestCase):
    """The owner, 2026-11-05: "make the general agent fake data showing results like LinkedIn posts". The demo has no AI, so its chats
    are written out: every turn answered, each ending in its summary, and what it set up waiting for one press."""
    def seeded(self):
        from taskuary import terminal
        s = MemoryStore()
        with mock.patch.object(terminal, 'live_sessions', return_value=[]): demo.seed(s)
        return s, {t['Title']: t['TaskId'] for t in s.list_tasks() if t.get('Assignee') == 'agent:general'}

    def test_every_chat_opens_on_what_came_in_and_every_answer_has_its_summary(self):
        from taskuary import general
        s, tids = self.seeded()
        self.assertEqual(len(tids), len(demo.AGENT_DAY) + 1, 'and the invite the agent answered (seed_calendar)')
        for title, tid in tids.items():
            h = general.shown_history(s, tid)
            self.assertTrue(h[0].get('brief') and h[0].get('mail'), title)
            self.assertTrue(all(m.get('summary') for m in h if m['role'] == 'assistant'), title)
            self.assertEqual(s.get_task(tid)['Status'], 'in_progress', 'the agent never closes a task')

    def test_the_post_carries_its_chart_and_the_overtime_reply_its_workbook(self):
        import json
        from taskuary import outputs, proposals
        s, tids = self.seeded()
        post = next(t for n, t in tids.items() if 'LinkedIn' in n)
        p = json.loads(next(r for r in s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (post,)))['DraftText'])
        self.assertTrue(proposals.is_post(p) and (outputs.folder(post) / p['image']).is_file())
        ot = next(t for n, t in tids.items() if 'overtime' in n)
        self.assertEqual(len([m for m in s.list_messages(ot) if m.get('Direction') != 'out']), 2, 'a second mail joined the thread')
        self.assertEqual(len(s.draft_snapshots(ot)), 2, 'each turn keeps the draft it wrote')
        # ...and the redraft answers that second mail, so it is the one to press: it read "set aside when you moved on" over "waiting to start"
        self.assertEqual(proposals.written_past(s, ot), set(), 'the draft written after her second mail is not one the thread moved past')

    def test_the_owners_own_answer_ends_in_a_recommendation_never_a_close(self):
        from taskuary import general
        s, tids = self.seeded()
        tid = next(t for n, t in tids.items() if 'Trainly' in n)
        self.assertIn('recommend closing', general.shown_history(s, tid)[-1]['summary']['did'])


class DemoChatTurnTests(unittest.TestCase):
    """agent-flow audit 2026-11-07: a task the visitor just made was told "the turns above were written in advance" - with none above."""
    def test_the_answer_points_at_turns_above_only_when_there_are_some(self):
        from taskuary import general, server
        s = MemoryStore()
        tid = s.create_task({'Title': 'Plan the team lunch', 'Kind': 'general', 'Status': 'open', 'Source': 'assistant'}, 'owner')
        with mock.patch.object(server, 'store', s), mock.patch.object(demo, 'enabled', return_value=True):
            self.assertEqual(server._demo_turn(tid, 'book it'), demo.NEW_CHAT_TURN)
            self.assertEqual(server._demo_turn(tid, 'and invite Erin'), demo.NEW_CHAT_TURN)       # its own answer is not a turn above
            s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'I found three places near the office.')
            self.assertEqual(server._demo_turn(tid, 'the second one'), demo.CHAT_TURN)
        self.assertNotIn('above', demo.NEW_CHAT_TURN)


class TheDemoWorldIsConnectedTests(unittest.TestCase):
    """F31 + F47 (2026-11-08): Connections said "0 connected" while the demo's tasks posted to LinkedIn and read Teams, and the AI tool
    cards read the VISITOR'S machine through GET routes the deny list lets by. The world is connected now, and its machine invented."""
    HOST_READS = ('/api/cli/detect', '/api/cli/connections', '/api/deps', '/api/update', '/api/connectors/3/wa/status',
                  '/api/connectors/3/wa/chats', '/api/connectors/3/linkedin/status', '/api/connectors/3/mail/folders')

    def test_every_host_read_is_answered_from_the_demo_and_never_looks(self):
        import shutil, subprocess
        boom = mock.Mock(side_effect=AssertionError('the demo looked at the host'))
        with on(), mock.patch.object(shutil, 'which', boom), mock.patch.object(subprocess, 'run', boom), mock.patch.object(subprocess, 'Popen', boom):
            for path in self.HOST_READS: self.assertIsNotNone(demo.answer('GET', path), path)
            from taskuary import agents, clis
            self.assertTrue(agents.runs_here({'cmd': 'claude'})); self.assertFalse(agents.runs_here({'cmd': 'gemini'}))
            self.assertEqual({r['name'] for r in clis.detect() if r['installed']}, set(demo.CLIS_HERE))
            self.assertEqual({t['name'] for t in clis.tools() if t['installed']}, set(demo.TOOLS_HERE))
        self.assertEqual(demo.answer('GET', '/api/tasks'), None, 'the demo world itself is read as it is')

    def test_outside_the_demo_nothing_is_answered_for_it(self):
        os.environ.pop(demo.FLAG, None)
        for path in self.HOST_READS: self.assertIsNone(demo.answer('GET', path), path)

    def test_settings_asks_for_no_signature_out_of_sent_mail_that_does_not_exist(self):
        from taskuary import signatures
        s = MemoryStore(); demo.seed(s)
        self.assertFalse(signatures.overview(s)['offer'])

    def test_a_press_that_reaches_nothing_real_is_never_answered_as_if_it_did(self):
        # each of these answered "that would reach something real, so it is switched off" (the walk, 2026-11-15)
        with on():
            self.assertEqual(demo.refuse('PATCH', '/api/tasks/36/checklist/c1/note'), '', 'a note on a to-do step is the demo own database')
            self.assertEqual(demo.refuse('POST', '/api/tasks/7/steps/s2/start'), demo.STARTS)
            self.assertEqual(demo.refuse('POST', '/api/tasks/7/read-ask'), demo.NO_AI)
            for path in ('/api/reports/7/rerun', '/api/reports/7/run', '/api/reports/due', '/api/sources', '/api/sources/7'):
                self.assertIn('reports are fixed', demo.refuse('POST', path), path)
            for path in ('/api/tasks/7/steps/s2/start', '/api/tasks/7/read-ask', '/api/reports/due', '/api/sources'):
                self.assertNotEqual(demo.refuse('POST', path), demo.OFF, path)

    def test_quit_says_why_the_demo_stays_up_never_that_it_would_reach_something_real(self):
        """The walk, 2026-11-18: the top bar's Quit answered "that would reach something real" - quitting reaches nothing; the demo is
        kept up for whoever opens it next (the website's /demo is one server for every visitor)."""
        with on():
            why = demo.refuse('POST', '/api/quit')
            self.assertTrue(why.startswith('This is the demo - '), why)
            self.assertNotEqual(why, demo.OFF)
            self.assertIn('close', why.lower())

    def test_a_file_put_on_a_draft_can_be_taken_off_again(self):
        """The walk, 2026-11-18: a file could be attached to a draft (copied into the demo's own home) but its Remove answered "that
        would reach something real" - nothing could take it back off. Taking it off is the same local write as putting it on."""
        with on():
            self.assertEqual(demo.refuse('POST', '/api/reviews/12/attachment'), '')
            self.assertEqual(demo.refuse('DELETE', '/api/reviews/12/attachment'), '')
            for path in ('/api/reviews/12', '/api/tasks/3', '/api/connectors/2', '/api/policies/1'):
                self.assertTrue(demo.refuse('DELETE', path), f'only the attachment is let by: {path}')

    def test_a_press_through_a_card_answers_as_its_own_path_does(self):
        """The walk, 2026-11-18: Change who does it > reply, a report's Pause this report, and every act whose own path the demo lets by
        answered "that would reach something real" when pressed through a card (/api/operations/<id>/execute): two roads for one act."""
        op = lambda k, **p: demo.refuse_op({'kind': k, 'params': p})
        with on():
            self.assertEqual(op('task.set_kind', kind='reply'), '')
            self.assertEqual(op('task.set_kind', kind='task'), '')
            self.assertEqual(op('task.set_kind', kind='general'), demo.STARTS)
            for k in ('report.pause', 'report.resume', 'report.run', 'report.edit'): self.assertEqual(op(k), demo.REPORTS_FIXED, k)
            for k in ('connection.test', 'connection.pause'): self.assertEqual(op(k), demo.CONNECTIONS_FIXED, k)
            self.assertEqual(op('task.trust'), demo.STARTS)
            self.assertEqual(op('message.retriage'), demo.NO_AI)
            # ...and each act its path already lets by is let by here too
            for k, path in (('deleted.restore', '/api/deleted/3/restore'), ('hub.comment', '/api/hub/posts/3/comments'),
                            ('meeting.new', '/api/meetings')):
                self.assertEqual(demo.refuse('POST', path), '', path)
                self.assertEqual(op(k), '', k)

    def test_stopping_a_recorded_agent_says_it_is_a_recording(self):
        """The walk, 2026-11-18: Stop and save on the replayed coding session read "that would reach something real"."""
        with on():
            for path in ('/api/tasks/12/wrap', '/api/tasks/12/pause', '/api/tasks/12/agent/stop', '/api/tasks/12/agent/cancel'):
                self.assertEqual(demo.refuse('POST', path), demo.RECORDED, path)
            self.assertEqual(demo.refuse_op({'kind': 'agent.stop', 'params': {}}), demo.RECORDED)

    def test_about_you_says_the_owner_is_invented(self):
        """The walk, 2026-11-18: About you > a picture's Keep answered "that would reach something real"."""
        with on():
            for m, path in (('PATCH', '/api/whoami'), ('PUT', '/api/owner'), ('PUT', '/api/hand-signature')):
                why = demo.refuse(m, path)
                self.assertNotEqual(why, demo.OFF, path)
                self.assertIn('owner is invented', why)

    def test_the_catch_all_claims_nothing_it_cannot_know(self):
        """The walk, 2026-11-18: whatever the deny list does not name answered "that would reach something real" - most of it reached
        nothing. The catch-all says only what is true of all of it."""
        self.assertNotIn('real', demo.OFF)
        self.assertTrue(demo.OFF.startswith('This is the demo - '))

    def test_trust_says_no_agent_starts_here_never_that_it_would_reach_something_real(self):
        with on(): self.assertEqual(demo.refuse('POST', '/api/tasks/4/trust'), demo.STARTS)

    def test_the_tool_cards_buttons_say_it_is_the_demo(self):
        with on():
            for path in ('/api/cli/install', '/api/cli/update', '/api/cli/setup', '/api/cli/connections/claude', '/api/deps/install', '/api/update'):
                self.assertTrue(demo.refuse('POST', path).startswith('This is the demo - nothing happens'), path)

    def test_its_tasks_channels_are_connected(self):
        from taskuary import connectorcatalog, outbound
        s = MemoryStore(); demo.seed(s)
        # ...every card the demo connects reads connected, and the count is those and its CLIs (a keyless card switched on, the Hub, counts too)
        on = {c['Type'] for c in connectorcatalog.connected(s)}
        self.assertLessEqual({c[0] for c in demo.CONNECTIONS}, on)
        self.assertEqual(connectorcatalog.connected_count(s, demo.cli_connections()), len(on) + len(demo.CLIS_ON))
        for kind in ('email', 'linkedin', 'teams', 'whatsapp', 'github'): self.assertIsNone(outbound.connect_fix(s, kind), kind)


    def test_the_system_its_reports_read_is_connected(self):
        """The walk, 2026-11-18: Connections > Databases read "Microsoft SQL Server - not set up · 3 reports" beside the demo's three
        reports, each "SQL Server · ran 3m ago" - a world whose reports run off a system it says is not there."""
        import json
        from taskuary import connectorcatalog
        s = MemoryStore(); demo.seed(s)
        read = {t for src in s.list_sources() if src['Channel'] == 'report'
                for t in [json.loads(src.get('ConfigJson') or '{}').get('type')] if connectorcatalog.by_type(t)}
        self.assertTrue(read, 'the demo has reports that read a system')
        self.assertLessEqual(read, {c['Type'] for c in s.list_connectors() if connectorcatalog.is_connected(c)})

class DemoDashboardTests(unittest.TestCase):
    def test_a_report_named_nightly_or_weekly_has_that_schedule(self):
        # with none, the Reports page framed each in red: "No schedule - it only runs when you press Run now" (the walk, 2026-11-15)
        import json
        s = MemoryStore(); demo.seed(s)
        crons = {x['Address']: json.loads(x['ConfigJson']).get('cron') for x in s.list_sources(active_only=False) if x.get('Channel') == 'report'}
        for title, _, _ in demo.REPORTS: self.assertTrue(crons.get(title), title)
        self.assertEqual(len(demo.REPORT_CRONS), len(demo.REPORTS))

    def test_a_report_of_the_last_fourteen_days_ends_yesterday(self):
        from datetime import date, timedelta
        days = [r['day'] for r in next(rows for title, _, rows in demo.REPORTS if 'last 14' in title)]
        # ...as of when the demo was read: a run that crosses midnight between the import and this line (CI, 23:55 UTC) is a day on
        d = [date.fromisoformat(x) for x in days]
        self.assertEqual((len(d), [b - a for a, b in zip(d, d[1:])]), (14, [timedelta(days=1)] * 13))
        self.assertIn(date.today() - d[-1], (timedelta(days=1), timedelta(days=2)))

    def test_the_dashboards_count_the_whole_morning_not_the_half_seeded_before_them(self):
        # they ran before the agents' day and the tour were seeded: the rail read "Open now 12" beside nineteen open tasks (the walk, 2026-11-15)
        from taskuary import dashboards
        s = MemoryStore(); demo.seed(s)
        n = sum(r['state'] == 'open' for r in dashboards._tasks(s, 90))
        heads = [m['Subject'] for m in s._rows("SELECT Subject FROM message WHERE Channel='report' AND Status NOT IN ('skipped','expired') ORDER BY MessageId")]
        self.assertTrue(any(h.startswith('Taskuary at a glance') and f'Open now {n}' in h for h in heads), (n, heads))
        self.assertTrue(any(h.startswith('Northwind desk') and f'Open tasks {n}' in h for h in heads), (n, heads))
        # ...and nothing made after the dashboards changed its number: the walks and the static demo know the morning's messages by them
        self.assertEqual(s.get_message(45)['TaskId'], next(t['TaskId'] for t in s.list_tasks() if 'LinkedIn' in (t.get('Title') or '')))
        # ...and they stand on the rail in the order they always did
        order = [h.split(' — ')[0] for h in heads if ' — ' in h]
        self.assertEqual(order[-3:], ['Northwind desk', 'Taskuary at a glance', 'Vendor spend, weekly'])


class DemoNeverPollsTests(unittest.TestCase):
    def test_opening_a_chat_task_reads_no_channel_and_leaves_its_card_connected(self):
        # opening a Teams or WhatsApp task refreshed its channel: the prop card then read "last test failed", and the WhatsApp read went to
        # whatever bridge was listening on this computer (the walk, 2026-11-15)
        from taskuary import channels
        s = MemoryStore(); demo.seed(s)
        with on(), mock.patch.object(channels, '_poll_jobs', side_effect=AssertionError('the demo read a channel')):
            self.assertEqual(channels.poll_channels(s, only=['teams', 'whatsapp']), 0)
        self.assertFalse([c['Type'] for c in s.list_connectors() if c.get('LastError')])


class DemoCalendarTests(unittest.TestCase):
    def test_the_demo_reads_its_own_week_and_never_reaches_microsoft(self):
        # the demo's Outlook card is a prop: read, it went to Microsoft and drew a real sign-in refusal on the day card (2026-11-12)
        from taskuary import calendar
        s = MemoryStore()
        cid = s.get_connector_by_type('outlook')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'Secret': 'x'}, 'o')
        s.save_source({'Channel': 'email', 'Address': 'alex@northwind.example', 'ConnectorId': cid, 'Name': 'Mail', 'Active': 1}, 'o')
        with mock.patch.object(demo, 'enabled', return_value=True), mock.patch.object(calendar, 'outlook_events', side_effect=AssertionError('went to Microsoft')):
            got = calendar.agenda(s)
        self.assertEqual((got['errors'], got['sources']), ([], ['demo']))
        self.assertEqual([e['subject'] for e in got['events']], [e['subject'] for e in demo.agenda()])


class DemoSealedTests(unittest.TestCase):
    def test_the_demo_reaches_nothing_outside_this_computer(self):
        # its prop cards sent an invented tenant to Microsoft and filled the bell with real refusals (the overnight audit, 2026-11-12)
        import requests
        before = requests.sessions.Session.request
        try:
            self.assertTrue(demo.seal()); demo.seal()                                  # once is enough, twice changes nothing
            self.assertIs(requests.sessions.Session.request.real, before)
            with self.assertRaisesRegex(requests.ConnectionError, 'reaches nothing outside'):
                requests.get('https://login.microsoftonline.example/token')
            with mock.patch.object(requests.sessions.Session.request, 'real', side_effect=lambda *a, **k: 'local'):
                self.assertEqual(requests.sessions.Session().request('GET', 'http://127.0.0.1:7803/api/health'), 'local')
        finally: requests.sessions.Session.request = before
