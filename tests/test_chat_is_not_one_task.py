"""Eleven messages, four problems, one task.

A chat room shares ONE conversation id - teams:<chat>, whatsapp:<jid> - and routing reads a
matching conversation id as the thread signal, which clears the attach bar on its own. So every
line a person ever typed joined whichever task their room opened first: a day of Tess's
messages, four unrelated problems and a screenshot among them, folded into one row carrying one
prompt, and the agent sent at it only ever saw the first ask (owner, 2026-09-02).

Nothing mechanical splits that - "Also..." opens a new ask and a continuation equally often -
so the reader decides, holding the exchange, ours and theirs. What is decided WITHOUT a model
here is only what is a fact rather than a judgement: a line typed seconds later, and an answer
arriving while an agent is live on the task. Since PW-031 (2026-09-06) the reader is the ONE
triage verdict - `relationship` among the room's same-day lines - not a second classifier, and
the room id alone never joins: without a brain, nothing but the facts does (PW-018/PW-033).
"""
import json, unittest
from unittest import mock

from taskuary.ingest import ingest_message
from taskuary.store import MemoryStore

CONV = 'whatsapp:120363@g.us'


def ago(minutes: int) -> str:
    from datetime import datetime, timedelta
    return (datetime.now() - timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


def brain(same=False, seen=None):
    """The one triage call per chat line: intent, kind and `relationship` together. `same` makes it
    say the line continues every same-day line it was shown; otherwise it is a new subject."""
    def llm(system, user, **kw):
        u = json.loads(user)
        if seen is not None: seen.append(u)
        rel = {'relationship': 'continues', 'related_message_ids': [c['id'] for c in u.get('same_day_lines', [])]} if same else {'relationship': 'new'}
        return json.dumps({'intent': 'task', 'kind': 'coding', 'why': 'an ask', **rel})
    return llm


def line(s, body, at, llm=None, ext=None, name='Tess'):
    return ingest_message(s, {'external_id': ext or f'wa:{at}', 'channel': 'whatsapp',
                              'subject': 'WhatsApp with Tess', 'body': body, 'from_name': name,
                              'from_email': None, 'conversation_id': CONV, 'sent_at': at,
                              'source_name': 'Tess'}, llm=llm)


class OneRoomManyJobs(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.first = line(self.s, 'the agent isnt working on my dashboard', '2026-09-02 16:35:00', brain())

    def test_the_first_ask_opens_a_task(self):
        self.assertEqual(self.first['status'], 'created')
        self.assertEqual(len(self.s.list_tasks()), 1)

    def test_a_line_typed_seconds_later_is_judged_like_any_other(self):
        """People type in fragments - and they also send a second bug 37 seconds after the first (the owner,
        2026-09-24: "someone sent 3 bugs in whatsapp but triage combined them"). How soon a line follows is
        evidence triage reads, never a join: a fragment it calls `continues` stays on the task, and one it calls
        `new` opens its own."""
        seen = []
        out = line(self.s, 'i mean the new one', '2026-09-02 16:35:40', brain(same=True, seen=seen))
        self.assertEqual((out['status'], out['task_id']), ('attached', self.first['task_id']))
        self.assertEqual(len(seen), 1)                    # triage was asked
        out = line(self.s, 'and the setup page says AI is not set up', '2026-09-02 16:35:55', brain(same=False))
        self.assertEqual(out['status'], 'created'); self.assertNotEqual(out['task_id'], self.first['task_id'])

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
                            'TaskId': self.first['task_id'], 'Subject': 'WhatsApp with Tess',
                            'FromName': 'You', 'SentAt': '2026-09-02 16:40:00',
                            'BodyText': 'fixed - try it now', 'Status': 'context'})
        seen = []
        line(self.s, 'nope. new', '2026-09-02 17:30:00', brain(same=False, seen=seen))
        asked = seen[0]['exchange']
        self.assertTrue(any(l.startswith('you ') and 'fixed - try it now' in l for l in asked))
        self.assertTrue(any(l.startswith('Tess ') and 'dashboard' in l for l in asked))
        self.assertEqual(seen[0]['body'], 'nope. new')
        self.assertEqual(len(seen), 1)                    # one call: intent, kind and relationship together

    def test_the_reader_is_never_shown_the_lines_that_came_after(self):
        """A whole poll lands on the timeline as 'triaging' before any of it is judged. Reading
        the rest of the conversation as context for its own beginning is reading the future."""
        from taskuary.ingest import deferred, drain
        with deferred():
            line(self.s, 'first of the burst', '2026-09-02 17:00:00')
            line(self.s, 'the one after it', '2026-09-02 17:20:00', ext='wa:later')
        seen = []
        drain(self.s, brain(same=False, seen=seen))
        first = next(a for a in seen if a.get('body') == 'first of the burst')
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

    def test_triage_switched_off_means_nothing_is_read_and_nothing_joins_on_the_room(self):
        """Switching the classifier off is a statement about the brain reading your messages - and
        the room id alone never joins (PW-018/PW-033), so the line opens its own work."""
        self.s.set_setting('intent_classify_enabled', '0', 'owner')
        seen = []
        out = line(self.s, 'Also, a completely different thing', '2026-09-02 17:20:00', brain(same=False, seen=seen))
        self.assertNotEqual(out['task_id'], self.first['task_id'])
        self.assertEqual(seen, [])

    def test_with_no_brain_nothing_joins_but_the_facts(self):
        """Undecidable no longer falls to attaching (PW-033: uncertain must not cause an automatic
        join); the owner can still merge two rows by hand."""
        out = line(self.s, 'Also, a completely different thing', '2026-09-02 17:20:00')
        self.assertNotEqual(out['task_id'], self.first['task_id'])


class MailIsStillAThread(unittest.TestCase):
    """A mail thread IS a topic - References says so - and nothing here may touch that."""

    def test_a_reply_on_an_email_thread_attaches_and_is_still_judged(self):
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
        # the thread keeps the reply, and triage still says what the reply IS - a verdict of fyi
        # files it onto the task for the chain instead of leaving it on the owner's pile
        self.assertEqual(len(seen), 1)


class NothingGoesBackByItself(unittest.TestCase):
    """A chat ask is an input to a task, not a conversation Taskuary holds: nothing is sent back into Teams, WhatsApp or
    Telegram without the owner's yes - not even "On it", which used to go the moment an agent started (the owner, 2026-09-30)."""
    def setUp(self):
        from taskuary import ingest
        self.sent = []
        self.inline = mock.patch.object(ingest, '_spawn', lambda fn, *a: fn(*a) if fn.__name__ != '_auto_code' else None)
        self.send = mock.patch('taskuary.outbound.reply_to_message',
                               lambda store, row, text, **kw: self.sent.append((row['ConversationId'], text)) or {'ok': True})
        self.inline.start(); self.send.start()
        self.addCleanup(self.inline.stop); self.addCleanup(self.send.stop)
        self.s = MemoryStore()

    def test_an_ask_that_starts_an_agent_sends_nothing_into_the_chat(self):
        out = line(self.s, 'the agent isnt working on my dashboard', ago(0), brain())
        self.assertEqual(self.sent, [])
        self.assertFalse(any('Acknowledged in' in c['Body'] for c in self.s.list_comments(out['task_id'])))
        self.assertFalse([m for m in self.s.thread_messages(CONV) if m.get('Direction') == 'out'])

    def test_the_old_switches_are_gone(self):
        from taskuary import doorway_browse
        knobs = doorway_browse._schema()['knobs']
        self.assertNotIn('chat_ack_enabled', knobs); self.assertNotIn('chat_ack_text', knobs)


class TheBrainsReadEachOther(unittest.TestCase):
    """Triage, the assistant and the digest read the same threads with different prompts and
    never saw each other's conclusions - so the owner watched three brains disagree."""
    def test_triage_is_shown_what_the_assistant_raised_about_the_thread(self):
        s = MemoryStore()
        s.upsert_idea({'key': f'followup:{CONV}', 'kind': 'followup', 'text': 'No answer from Tess in 2 days - follow up?'},
                      '2026-09-01 08:00:00')
        seen = []
        line(s, 'sorry, yes - it works now', '2026-09-02 16:35:00', brain(seen=seen))
        self.assertIn('assistant_said', seen[0])
        self.assertIn('followup raised 2026-09-01, now open', seen[0]['assistant_said'][0])

    def test_a_thread_nobody_raised_costs_no_words(self):
        seen = []
        line(MemoryStore(), 'hello there, quick one', '2026-09-02 16:35:00', brain(seen=seen))
        self.assertNotIn('assistant_said', seen[0])

    def test_the_assistant_is_shown_what_triage_decided(self):
        from taskuary import assistant
        s = MemoryStore()
        line(s, 'the agent isnt working on my dashboard', ago(0), brain())
        head = assistant._people_context(s)[0].splitlines()[0]
        self.assertIn('triage said: "triage: task', head)


if __name__ == '__main__':
    unittest.main()
