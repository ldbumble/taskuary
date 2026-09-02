"""Eleven messages, four problems, one task.

A chat room shares ONE conversation id - teams:<chat>, whatsapp:<jid> - and routing reads a
matching conversation id as the thread signal, which clears the attach bar on its own. So every
line a person ever typed joined whichever task their room opened first: a day of Gabi's
messages, four unrelated problems and a screenshot among them, folded into one row carrying one
prompt, and the agent sent at it only ever saw the first ask (owner, 2026-09-02).

Nothing mechanical splits that - "Also..." opens a new ask and a continuation equally often -
so the reader decides, holding the exchange, ours and theirs. What is decided WITHOUT a model
here is only what is a fact rather than a judgement: a line typed seconds later, and an answer
arriving while an agent is live on the task.
"""
import json, unittest

from taskuary.ingest import ingest_message
from taskuary.store import MemoryStore

CONV = 'whatsapp:120363@g.us'


def brain(same=False, seen=None):
    """One callable for both prompts, told apart by the contract each asks for - which is how
    the funnel calls them: triage.same_ask and triage.classify_intent share the ingest llm."""
    def llm(system, user, **kw):
        if 'is NEW part of the ask already open' in system:
            if seen is not None: seen.append(json.loads(user))
            return json.dumps({'same': same, 'why': 'a different subject'})
        if seen is not None: seen.append(json.loads(user))
        return json.dumps({'intent': 'task', 'kind': 'coding', 'why': 'an ask'})
    return llm


def line(s, body, at, llm=None, ext=None, name='Gabi'):
    return ingest_message(s, {'external_id': ext or f'wa:{at}', 'channel': 'whatsapp',
                              'subject': 'WhatsApp with Gabi', 'body': body, 'from_name': name,
                              'from_email': None, 'conversation_id': CONV, 'sent_at': at,
                              'source_name': 'Gabi'}, llm=llm)


class OneRoomManyJobs(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.first = line(self.s, 'the agent isnt working on my dashboard', '2026-09-02 16:35:00', brain())

    def test_the_first_ask_opens_a_task(self):
        self.assertEqual(self.first['status'], 'created')
        self.assertEqual(len(self.s.list_tasks()), 1)

    def test_a_line_typed_seconds_later_is_the_same_thought(self):
        """People type in fragments. No model is asked, because this is not a judgement."""
        seen = []
        out = line(self.s, 'i mean the new one', '2026-09-02 16:35:40', brain(same=False, seen=seen))
        self.assertEqual(out['status'], 'attached')
        self.assertEqual(out['task_id'], self.first['task_id'])
        self.assertEqual(seen, [])                        # nothing was asked of the brain

    def test_a_separate_ask_gets_its_own_task(self):
        seen = []
        out = line(self.s, 'Also, copilot did this in my email. would be nice to have',
                   '2026-09-02 16:52:00', brain(same=False, seen=seen))
        self.assertEqual(out['status'], 'created')
        self.assertNotEqual(out['task_id'], self.first['task_id'])
        self.assertEqual(len(self.s.list_tasks()), 2)
        route = self.s.message_routes(out['message_id'])[-1]
        self.assertIn('a separate ask in the same chat', route['Reason'])

    def test_the_same_ask_continued_stays_on_its_task(self):
        out = line(self.s, 'still broken by the way', '2026-09-02 16:52:00', brain(same=True))
        self.assertEqual((out['status'], out['task_id']), ('attached', self.first['task_id']))

    def test_the_reader_is_shown_both_halves_of_the_conversation(self):
        """Our own replies are the clearest boundary in a chat, and nothing ever showed them."""
        self.s.add_message({'ExternalId': 'mine', 'ConversationId': CONV, 'Channel': 'whatsapp',
                            'TaskId': self.first['task_id'], 'Subject': 'WhatsApp with Gabi',
                            'FromName': 'You', 'SentAt': '2026-09-02 16:40:00',
                            'BodyText': 'fixed - try it now', 'Status': 'context'})
        seen = []
        line(self.s, 'nope. new', '2026-09-02 17:30:00', brain(same=False, seen=seen))
        asked = seen[0]['exchange']
        self.assertTrue(any(l.startswith('you ') and 'fixed - try it now' in l for l in asked))
        self.assertTrue(any(l.startswith('Gabi ') and 'dashboard' in l for l in asked))
        self.assertEqual(seen[0]['new'], 'nope. new')
        # ...and triage got it too: a bare "nope. new" means nothing without what it answers
        self.assertIn('exchange', seen[1])

    def test_the_reader_is_never_shown_the_lines_that_came_after(self):
        """A whole poll lands on the timeline as 'triaging' before any of it is judged. Reading
        the rest of the conversation as context for its own beginning is reading the future."""
        from taskuary.ingest import deferred, drain
        with deferred():
            line(self.s, 'first of the burst', '2026-09-02 17:00:00')
            line(self.s, 'the one after it', '2026-09-02 17:20:00', ext='wa:later')
        seen = []
        drain(self.s, brain(same=False, seen=seen))
        first = next(a for a in seen if a.get('new') == 'first of the burst')
        self.assertFalse([l for l in first['exchange'] if 'the one after it' in l])
        self.assertFalse([l for l in first['exchange'] if 'first of the burst' in l])

    def test_a_new_task_is_titled_by_the_ask_not_by_the_room(self):
        """Every line shares the room's name, so titling with it made a board of identical rows."""
        out = line(self.s, 'Give me an executive and concise evening summary of the day',
                   '2026-09-02 17:38:00', brain(same=False))
        self.assertEqual(self.s.get_task(out['task_id'])['Title'],
                         'Give me an executive and concise evening summary of the day')

    def test_an_answer_to_a_live_agent_is_never_split_off(self):
        """The agent asked them something on this chat; their answer is that round trip."""
        seen = []
        rid = self.s.start_run(self.first['task_id'], 'coder', 'have a look', 'owner')
        self.s.update_run(rid, {'Status': 'running'})
        out = line(self.s, 'yes, the production one', '2026-09-02 17:10:00', brain(same=False, seen=seen))
        self.assertEqual((out['status'], out['task_id']), ('attached', self.first['task_id']))
        self.assertEqual(seen, [])

    def test_with_no_brain_the_conversation_is_kept_whole(self):
        """Undecidable falls to attaching: the owner splits it in one click, and the opposite
        mistake - a task per line - is one nobody can undo."""
        out = line(self.s, 'Also, a completely different thing', '2026-09-02 17:20:00')
        self.assertEqual(out['task_id'], self.first['task_id'])


class MailIsStillAThread(unittest.TestCase):
    """A mail thread IS a topic - References says so - and nothing here may touch that."""

    def test_a_reply_on_an_email_thread_attaches_with_nothing_asked(self):
        s = MemoryStore()
        seen = []
        msg = {'external_id': 'm1', 'channel': 'email', 'subject': 'Financial request',
               'body': 'please send March thru June', 'from_name': 'Client',
               'from_email': 'client@y.com', 'conversation_id': 'c9', 'sent_at': '2026-09-02 10:00:00'}
        first = ingest_message(s, msg, llm=brain())
        out = ingest_message(s, {**msg, 'external_id': 'm2', 'subject': 'RE: Financial request',
                                 'body': 'Also, a completely different thing', 'sent_at': '2026-09-02 15:00:00'},
                             llm=brain(same=False, seen=seen))
        self.assertEqual((out['status'], out['task_id']), ('attached', first['task_id']))
        self.assertEqual(seen, [])


if __name__ == '__main__':
    unittest.main()
