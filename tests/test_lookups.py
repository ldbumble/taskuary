"""The assistant's look-ups over the whole store: body search, open work, one message, one sender, the docs."""
import unittest
from unittest import mock
from taskuary import concierge, ingest, lookups, toolcatalog
import tests.test_assistant_reactions as T


def world():
    s = T.store()
    with mock.patch.object(ingest, '_spawn'):
        T.arrive(s, subject='Can you fix the export?', body='The nightly export drops inter-company rows.', llm=T.brain('task', 'coding'))
        T.arrive(s, subject='Quarterly numbers', body='Attached are the figures; the freight line looks off.', who='Gail Moreno',
                 email='gail@northwind.example', hours=3, llm=T.brain('task', 'general'))
    return s

def read(s, kind, **p): return concierge.read_op(s, kind, p)


class LookupTests(unittest.TestCase):
    def test_every_new_read_is_offered_and_validated(self):
        b = toolcatalog.block()
        for k in lookups.READ:
            self.assertIn(k, b); self.assertTrue(toolcatalog.is_read(k))
        self.assertTrue(toolcatalog.valid('message.read', {}))
        self.assertEqual(toolcatalog.valid('tasks.list', {}), '')

    def test_timeline_search_reaches_the_body_and_prints_the_message_number(self):
        s = world()
        out = read(s, 'timeline.search', contains='freight')
        self.assertIn('Quarterly numbers', out); self.assertRegex(out, r'^m\d+ ')
        self.assertNotIn('export', out)
        self.assertIn('Nothing in the history', read(s, 'timeline.search', contains='zzzz'))

    def test_the_index_follows_edits_and_deletes(self):
        s = world()
        mid = s.message_search(['freight'])[0]
        s._exec('UPDATE message SET BodyText=? WHERE MessageId=?', ('now about pallets', mid))
        self.assertEqual(s.message_search(['freight']), [])
        self.assertEqual(s.message_search(['pallets']), [mid])
        s._exec('DELETE FROM message WHERE MessageId=?', (mid,))
        self.assertEqual(s.message_search(['pallets']), [])

    def test_message_read_opens_one_in_full(self):
        s = world()
        mid = s.message_search(['freight'])[0]
        out = read(s, 'message.read', mid=f'm{mid}')
        self.assertIn('gail@northwind.example', out); self.assertIn('freight line looks off', out)
        self.assertIn('There is no message', read(s, 'message.read', mid='m99999'))

    def test_tasks_list_shows_open_work_and_narrows_by_words(self):
        s = world()
        out = read(s, 'tasks.list')
        self.assertIn('TQ-0001', out); self.assertIn('TQ-0002', out)
        self.assertNotIn('TQ-0001', read(s, 'tasks.list', contains='quarterly'))
        s.update_task(1, {'Status': 'done'}, 't')
        self.assertNotIn('TQ-0001', read(s, 'tasks.list'))
        self.assertIn('TQ-0001', read(s, 'tasks.list', status='done'))

    def test_sender_read_gathers_one_person(self):
        s = world()
        s.add_memory({'Scope': 'sender', 'ScopeKey': 'gail@northwind.example', 'Note': 'She owns the freight budget.', 'Active': 1})
        out = read(s, 'sender.read', who='gail')
        for want in ('Gail Moreno', '1 messages', 'Quarterly numbers', 'TQ-0002', 'freight budget'):
            self.assertIn(want, out)
        self.assertIn('Nobody by', read(s, 'sender.read', who='nobody-at-all'))

    def test_docs_search_finds_the_help_pages_and_the_owners_docs(self):
        s = world()
        s.save_doc('COUNSEL.md', '# Counsel\n\n## Tone\n\nKeep replies to two sentences.\n', 't')
        self.assertIn('your doc COUNSEL.md > Tone', read(s, 'docs.search', query='what tone should replies take'))
        if lookups.SITE_DOCS.is_dir():
            self.assertIn('help/', read(s, 'docs.search', query='connect whatsapp phone'))
        self.assertIn('Nothing in the help', read(s, 'docs.search', query='zzzqqq'))


if __name__ == '__main__': unittest.main()
