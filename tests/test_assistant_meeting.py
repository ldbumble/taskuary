"""A meeting asked for in the chat is the calendar's, never an agent's job (the owner, 2026-10-28: "schedule a meeting" brought up Give an
agent a job - "is that what we want?"). The model is given the road - meeting.new - and the route is code's: the one scheduling move the app
has is a task's Find a time, so on a task whose thread asks for a time that button is lit; with no such task the line says so and the
meeting is written into New as the owner's to-do; with no calendar, one line and the card that connects one. No agent, nothing drafted."""
import json, unittest
from unittest import mock

from taskuary import concierge, operations, server, terminal, toolcatalog
from tests.test_calendar_write import D, ERIN, outlook_store
from tests.test_assistant_router import say
from taskuary.store import MemoryStore

ASK = 'schedule a meeting with Gail about the Q3 budget'


def call(**p): return 'CALL: ' + json.dumps({'kind': 'meeting.new', 'params': p})


def asking_thread(s):
    """A task whose thread triage read as asking for a time - the one place Find a time is drawn."""
    t = s.create_task({'Title': 'Audit list', 'Kind': 'reply'}, 'owner')
    mid = s.add_message({'TaskId': t, 'ExternalId': 'graph:m2', 'Channel': 'email', 'Subject': 'Audit list - 30 minutes?', 'FromEmail': ERIN,
                         'FromName': 'Erin Blake', 'SourceName': 'alex@northwind.example', 'BodyText': 'Can we find 30 minutes?', 'Status': 'routed',
                         'MeetJson': json.dumps({'minutes': 30, 'from': D, 'to': D})})
    return {'kind': 'asked', 'key': f'msg:{mid}', 'mid': mid, 'tid': t, 'title': 'Audit list'}


def turn(s, item, **p):
    with mock.patch.object(terminal, 'live_sessions', return_value=[]):
        return concierge.call_turn(s, concierge.general.dock_task(s, 'owner')[0]['TaskId'], {'kind': 'meeting.new', 'params': p}, item, 'x')


class TheRoadIsOffered(unittest.TestCase):
    def test_the_index_names_meeting_new_where_new_work_is_and_its_description_is_one_the_model_would_pick(self):
        b = toolcatalog.block()
        self.assertIn('meeting.new(who?, about?, when?)', b)
        self.assertIn('meeting.new', dict((n, ks) for n, _, ks in toolcatalog.BUCKETS)['new'])
        self.assertIn('a meeting meeting.new', b, 'WHICH ONE names it beside the to-do, so the model reaches it without a look-up')
        self.assertLess(len(b), 7950)
        d = toolcatalog.describe('meeting.new')
        for w in ('set up a meeting', 'Find a time', 'no calendar', "Never an agent's job", "Send"):
            self.assertIn(w, d)
        # ...and the agent hand-off says it is not the road for one
        self.assertIn('meeting.new', toolcatalog.describe('regular_agent'))
        self.assertIn('meeting.new', operations.KINDS)
        self.assertEqual(toolcatalog.valid('meeting.new', {}), '')


class OnTheDesk(unittest.TestCase):
    def setUp(self): mock.patch.object(server, 'store', None).start()      # never the live home
    def tearDown(self): mock.patch.stopall()

    def test_a_task_whose_thread_asks_for_a_time_lights_its_find_a_time(self):
        s = outlook_store(); item = asking_thread(s)
        out = turn(s, item, who=ERIN)
        self.assertEqual(out['light']['verb'], 'find_time')
        self.assertNotIn('new', out)
        self.assertEqual([r for r in s._rows('SELECT * FROM review')], [], 'lit, nothing drafted')

    def test_the_task_the_ask_names_is_brought_up_with_its_find_a_time(self):
        s = outlook_store(); item = asking_thread(s)
        with mock.patch.object(concierge.funnel, 'item_for_key', return_value=item) as find:
            out = turn(s, None, ref=f"TQ-{item['tid']:04d}")
        find.assert_called_with(s, f"task:{item['tid']}")
        self.assertEqual((out['light']['verb'], out['light']['tid']), ('find_time', item['tid']))

    def test_with_no_such_task_it_says_where_scheduling_lives_and_writes_a_to_do_never_an_agent(self):
        s = outlook_store()
        out, spawn = say(s, ASK, None, call(who='Gail', about='the Q3 budget'))
        self.assertTrue(out['say'].startswith(concierge.NO_THREAD), out['say'])
        self.assertEqual((out['new']['kind'], out['new']['text']), ('note', 'Meeting with Gail about the Q3 budget'))
        spawn.assert_not_called()
        self.assertEqual([r for r in s._rows('SELECT * FROM review')], [])
        # ...the chat's line is the one said, so a reload draws the same words
        self.assertIn(out['say'], [str(c.get('Body') or '') for c in s.list_comments(int(s.get_setting('assistant_dock_task_id')))][-1])

    def test_no_calendar_is_one_line_with_the_card_that_connects_one(self):
        s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
        out, spawn = say(s, ASK, None, call(who='Gail'))
        self.assertEqual(out['say'], concierge.NO_CALENDAR)
        self.assertNotIn('new', out)
        self.assertEqual(out['chips'][0], {'verb': 'go', 'label': 'Connect a calendar', 'href': '#connector=outlook'})
        spawn.assert_not_called()


class OnThePhone(unittest.TestCase):
    def test_no_task_is_the_same_line_and_nothing_made(self):
        s = outlook_store()
        with concierge.delivering(concierge.PHONE):
            out, spawn = say(s, ASK, None, call(who='Gail', about='the Q3 budget'))
        self.assertTrue(out['say'].startswith(concierge.NO_THREAD), out['say'])
        self.assertNotIn('new', out); spawn.assert_not_called()


if __name__ == '__main__': unittest.main()
