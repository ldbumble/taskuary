"""The 2026-09-30 phone pass (tools/wa_walk.py drives the real doorway against the demo world): an act inside a walked
section stays in the section, no browse list offers more than a WhatsApp poll can hold, report rows that arrive as JSON read
as rows, and Reports and the Hub are browsed like Connections and Settings."""
import unittest
from unittest import mock

from taskuary import chatformat, concierge, doorway_browse as db, funnel, remote_assistant as ra
from taskuary.store import MemoryStore

PILE = [{'key': 'msg:1', 'lane': 'asked', 'order_band': 2, 'title': 'Approve the Q3 invoice', 'who': 'Paula Vance'},
        {'key': 'rep:1', 'lane': 'report', 'order_band': 4, 'kind': 'report', 'title': 'Headcount by site'},
        {'key': 'rep:2', 'lane': 'report', 'order_band': 4, 'kind': 'report', 'title': 'AP ageing'}]


class ActInASectionTests(unittest.TestCase):
    def setUp(self):
        self.s, self.shown = MemoryStore(), []
        def surface(store, key=None, **kw):
            self.shown.append(key)
            return {'say': f'shown {key}', 'item': {'key': key} if key else None}
        self.patches = [mock.patch.object(funnel, 'pile', return_value={'items': PILE}),
                        mock.patch.object(db, 'next_in', side_effect=lambda store, sec, seen: next(
                            (i for i in PILE if funnel.level_of(i) == sec and i['key'] not in seen), None)),
                        mock.patch.object(concierge, 'surface', side_effect=surface),
                        mock.patch.object(ra, 'turn_text', side_effect=lambda out, lead='', store=None, extra=None, full=False: (lead + ' ' + (out.get('say') or '')).strip()),
                        mock.patch.object(ra, 'asking', return_value={'channel': 'whatsapp', 'chat': 'c1'})]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in self.patches: p.stop()

    def test_an_act_moves_on_inside_the_section_not_to_the_top_of_the_walk(self):
        """Make a task on the first report put TQ-0001 (On you) up in the middle of Walk Reports."""
        sec = funnel.level_of(PILE[1])
        db.hold(self.s, ra.asking(), sec, ['rep:1'])
        text = ra._on(self.s, 'owner', ['Done - Put it on my list · TQ-0021.'], done_with='rep:1')
        self.assertEqual(self.shown[-1], 'rep:2')
        self.assertIn('shown rep:2', text)

    def test_when_the_section_runs_out_it_says_so_and_the_walk_goes_on(self):
        sec = funnel.level_of(PILE[1])
        db.hold(self.s, ra.asking(), sec, ['rep:1', 'rep:2'])
        text = ra._on(self.s, 'owner', ['Done.'], done_with='rep:2')
        self.assertIsNone(self.shown[-1])                       # the whole walk's own next
        self.assertIn(funnel.section_done(sec), text)
        self.assertIsNone(db.held(self.s, ra.asking()))

    def test_outside_a_section_an_act_moves_on_as_it_always_did(self):
        ra._on(self.s, 'owner', ['Done.'], done_with='msg:1')
        self.assertEqual(self.shown, [None])


class PollFitsTests(unittest.TestCase):
    def test_no_page_offers_more_than_a_poll_holds_and_back_always_fits(self):
        rows = [(f'row {i}', {'t': 'browse', 'n': i}) for i in range(17)]
        up = [('Back', {'t': 'browse'})]
        first = db.paged(rows, up, {'t': 'browse', 'area': 'x'})
        self.assertLessEqual(len(first), db.POLL_MAX)
        self.assertEqual(first[-1][0], 'Back')
        self.assertEqual(first[-2][1]['page'], 1)
        second = db.paged(rows, up, {'t': 'browse', 'area': 'x'}, 1)
        self.assertEqual([r[0] for r in second[:7]], [f'row {i}' for i in range(10, 17)])
        self.assertEqual(second[-2][0], 'From the top')

    def test_a_short_list_is_left_whole(self):
        rows = [(f'row {i}', {}) for i in range(11)]
        self.assertEqual(db.paged(rows, [('Back', {})], {}), rows + [('Back', {})])

    def test_every_real_browse_step_fits(self):
        s = MemoryStore()
        text, picks = db.browse(s, 'connections')
        self.assertLessEqual(len(picks), db.POLL_MAX)
        for label, act in picks:
            if act.get('section'):
                _, sub = db.browse(s, 'connections', act['section'])
                self.assertLessEqual(len(sub), db.POLL_MAX, act['section'])
        _, sets = db.browse(s, 'settings')
        for _, act in sets:
            self.assertLessEqual(len(db.browse(s, 'settings', act['section'])[1]), db.POLL_MAX, act['section'])

    def test_the_morning_menu_fits_with_every_section_on_the_rail(self):
        self.assertLessEqual(3 + len(db.WALKED) + len(ra.SCRIPT_LINES) - 3, db.POLL_MAX)


class ReportRowsTests(unittest.TestCase):
    def test_json_lines_become_a_table(self):
        body = '{"site": "Lakeview", "headcount": 112}\n{"site": "Riverside", "headcount": 98}'
        out = chatformat.render(chatformat.blocks(body)[0], 'whatsapp')
        self.assertNotIn('{', out)
        self.assertIn('Lakeview · 112', out)

    def test_anything_else_is_left_as_it_was(self):
        for body in ('The month closed clean.\nNothing to chase.', '{"a": {"nested": 1}}\n{"a": 2}', '{"only": "one"}'):
            self.assertEqual(chatformat.json_rows(body), body)


class ReportsAndHubTests(unittest.TestCase):
    def test_reports_and_the_hub_are_on_the_menu(self):
        self.assertIn(('Reports', {'t': 'browse', 'area': 'reports'}), ra.SCRIPT_LINES)
        self.assertIn(('Hub', {'t': 'browse', 'area': 'hub'}), ra.SCRIPT_LINES)

    def test_an_empty_install_says_how_to_start(self):
        from taskuary import appfacts
        with mock.patch.object(appfacts, 'reports', return_value=[]):
            self.assertIn('set up a report', db.browse(MemoryStore(), 'reports')[0])



class PipeListSaysForLaterTests(unittest.TestCase):
    def test_the_rail_is_read_by_its_own_sections_for_later_included(self):
        """"what tasks are waiting in later" was answered "nothing is parked in Later" - pipe.list grouped by LANE, and For
        later is a section (funnel.level_of), so the model never saw the heading the owner was looking at (2026-09-30)."""
        from taskuary import lookups
        items = [{'key': 'a', 'lane': 'asked', 'order_band': 2, 'title': 'Invoice', 'who': 'Paula Vance', 'tid': 3},
                 {'key': 'b', 'lane': 'yours', 'order_band': 2, 'surfaced': True, 'put_down': True, 'back_at': '2099-01-01 09:00:00', 'title': 'Lease', 'tid': 4}]
        with mock.patch.object(funnel, 'pile', return_value={'items': items}):
            out = lookups.pipe_list(MemoryStore(), {})
        self.assertIn('FOR LATER (1):', out)
        self.assertLess(out.index('ON YOU (1):'), out.index('FOR LATER (1):'))
        self.assertIn('Lease', out.split('FOR LATER')[1])
        self.assertIn('back in', out.split('FOR LATER')[1])



class CardSaysItOnceTests(unittest.TestCase):
    def test_a_task_written_from_one_pasted_paragraph_prints_it_once(self):
        """TQ-0887 shape: the New box made the paragraph the title, the message's subject and the summary - the phone card
        printed it three times (the owner, 2026-09-30)."""
        para = 'why do I get thirty of these a day? One or more errors were encountered while editing user x. Alert E09.'
        self.assertTrue(ra._repeats(para, ['Why do I get thirty of these a day?']))
        self.assertTrue(ra._repeats('One or more errors were encountered while editing user x. Alert E09.', ['Why…', para]))
        self.assertFalse(ra._repeats('#113 · keep inter-company rows in the export', ['Kai wants the export fixed']))


class OpenSaysWhatItIsTests(unittest.TestCase):
    def test_each_open_choice_names_its_task(self):
        """"Open TQ-0800 / Open TQ-0876 / Open TQ-0887" said nothing about what they were (the owner, 2026-09-30)."""
        import inspect
        src = inspect.getsource(concierge)
        self.assertIn("f\"Open {i.get('ref') or ''}\".strip(), _title_cut(", src)



class HeldMessagesKeepTheirPicturesTests(unittest.TestCase):
    def test_a_message_triaged_later_is_judged_with_its_picture(self):
        """A photo with no words, triaged after it landed, was rebuilt from its row WITHOUT the photo - and judged on the chat
        around it: a personal picture became a coding task and an agent (the owner, 2026-09-30)."""
        import base64, os, tempfile
        from taskuary import ingest
        s = MemoryStore()
        mid = s.add_message({'ExternalId': 'wa:1', 'Channel': 'whatsapp', 'FromName': 'Gail Moreno', 'BodyText': '(no text - see the attachment)',
                             'SentAt': '2026-09-30 17:43:52', 'Status': 'pending', 'ConversationId': 'whatsapp:g'})
        f = os.path.join(tempfile.mkdtemp(), 'photo.jpg')
        with open(f, 'wb') as h: h.write(b'\xff\xd8\xff' + b'0' * 64)
        with mock.patch.object(s, 'list_attachments', return_value=[{'ContentType': 'image/jpeg', 'Path': f}]):
            msg = ingest._from_row(s.get_message(mid), s)
        self.assertEqual(len(msg['images']), 1)
        self.assertEqual(msg['images'][0][0], 'image/jpeg')
        self.assertEqual(base64.b64decode(msg['images'][0][1])[:3], b'\xff\xd8\xff')

    def test_no_picture_adds_nothing(self):
        from taskuary import ingest
        s = MemoryStore()
        mid = s.add_message({'ExternalId': 'e1', 'Channel': 'email', 'BodyText': 'hello', 'Status': 'pending'})
        self.assertNotIn('images', ingest._from_row(s.get_message(mid), s))



class TheAiFailedTests(unittest.TestCase):
    """An AI that failed was logged and answered with the pipe's facts - it read as the Assistant ignoring the question or
    stuck. It says what went wrong and what to do, with Try again and the way on (the owner, 2026-09-30)."""
    def _say(self, err):
        def llm(*a, **k): raise Exception(err)
        return concierge.say(MemoryStore(), 'what is waiting on me?', llm=llm)

    def test_a_rate_limit_says_wait_and_offers_try_again_with_the_same_words(self):
        out = self._say('Error code: 429 - rate limit reached')
        self.assertTrue(out.get('error'))
        self.assertIn('wait a few minutes', out['say'])
        self.assertEqual(out['chips'][0], {'label': 'Try again', 'ask': 'what is waiting on me?'})

    def test_a_conversation_too_long_says_start_a_new_chat(self):
        self.assertIn('Start a new chat', concierge.brain_trouble(Exception("This model's maximum context length is 128000 tokens")))

    def test_a_refused_key_points_at_the_connection(self):
        self.assertIn('Connections', concierge.brain_trouble(Exception('401 Unauthorized: invalid api key')))

    def test_anything_else_still_says_what_to_do(self):
        said = concierge.brain_trouble(Exception('something odd'))
        self.assertIn('something odd', said); self.assertIn('new chat', said)

    def test_on_the_phone_try_again_is_a_pick_that_sends_the_words_again(self):
        ra._ASKING.chat = {'channel': 'whatsapp', 'chat': 'c1', 'connector_id': None}
        try:
            text = ra.turn_text({'say': 'My AI is out of room.', 'item': None,
                                 'chips': [{'label': 'Try again', 'ask': 'what is waiting?'}, {'verb': 'next', 'label': 'Next'}]},
                                store=MemoryStore())
            rows = dict(ra._ACTS.rows or [])
        finally: ra._ASKING.chat = None
        self.assertIn('Try again', text)
        self.assertEqual(rows.get('Try again'), {'t': 'ask', 'text': 'what is waiting?'})


class NeverADeadEndTests(unittest.TestCase):
    def test_the_newest_line_with_nothing_to_press_offers_next(self):
        from pathlib import Path
        src = Path(__file__).resolve().parents[1].joinpath('website', 'src', 'AssistantView.jsx').read_text(encoding='utf-8')
        self.assertIn('NEVER A DEAD END', src)
        self.assertIn('? said : idle ? IDLE_CHIPS : [{ verb: "next", label: "Next" }]', src)   # an empty rail offers ways to start something


if __name__ == '__main__':
    unittest.main()
