"""Every way the owner's name is saved converts the docs: the template's John Smith never reaches triage or an agent beside it."""
import unittest
from unittest import mock
from taskuary.store import MemoryStore, set_owner, docs_hold_template_owner
from taskuary import firstrun


def _clean(s, test):
    for d in ('soul', 'agent', 'coding', 'triage'): test.assertNotIn('John', s.doc(d) or '', d)


class OwnerOneDoorTests(unittest.TestCase):
    def test_agent_md_names_the_owner_not_john(self):
        s = MemoryStore()
        self.assertNotIn('John', s.doc('agent'))
        self.assertIn('the owner decides', s.doc('agent'))         # nobody named yet: "the owner", never "the"
        set_owner(s, 'Alex Doyle', 'alex@northwind.example')
        self.assertIn('Alex decides', s.doc('agent'))
        _clean(s, self)

    def test_with_no_name_set_the_template_never_reaches_triage_as_the_owner(self):
        # agent-flow audit 2026-11-07: "Written to Alex, not John" - real asks filed as FYI before the owner's name was set
        from taskuary.store import NO_NAME_YET, TEMPLATE_OWNER
        s = MemoryStore()
        self.assertIn(TEMPLATE_OWNER[0], s.get_doc('soul'))                    # the doc as written keeps its readable example
        soul = s.doc('soul')
        for d in ('soul', 'agent', 'coding', 'triage'): self.assertNotIn('John', s.doc(d) or '', d)
        self.assertNotIn(TEMPLATE_OWNER[1], soul); self.assertNotIn('()', soul)
        self.assertIn('You work for **the owner**', soul); self.assertIn(NO_NAME_YET, soul)
        set_owner(s, 'Alex Doyle', 'alex@northwind.example')
        self.assertNotIn(NO_NAME_YET, s.doc('soul')); self.assertIn('**Alex Doyle** (alex@northwind.example)', s.doc('soul'))

    def test_the_mailbox_guess_goes_through_set_owner(self):
        s = MemoryStore()
        def claims(store, c):
            store.save_source({'Channel': 'email', 'Address': 'alex.doyle@northwind.example', 'ConnectorId': c, 'Active': 0}, 't')
            return {'ok': True, 'detail': 'logged in'}
        with mock.patch('taskuary.channels.test_connector', side_effect=claims):
            self.assertTrue(firstrun.connect_mail(s, 'gmail', 'alex.doyle@northwind.example', 'abcd efgh ijkl mnop')['ok'])
        self.assertEqual(s.owner()['owner'], 'Alex Doyle')
        self.assertFalse(docs_hold_template_owner(s))
        _clean(s, self)
        self.assertIn('alex.doyle@northwind.example', s.doc('soul'))

    def test_about_your_work_heals_docs_a_plain_setting_left_behind(self):
        s = MemoryStore()
        s.set_setting('owner_name', 'Alex Doyle', 'owner')            # an older install: the name saved beside the docs
        self.assertTrue(docs_hold_template_owner(s))
        firstrun._who(s, {'name': 'Alex Doyle'})                     # same name typed again - still converts
        self.assertFalse(docs_hold_template_owner(s))
        _clean(s, self)

    def test_a_tokenized_template_doc_keeps_tracking_the_template(self):
        s = MemoryStore()
        set_owner(s, 'Alex Doyle', 'alex@northwind.example')
        self.assertEqual(s.doc_owner('coding'), 'template')

    def test_settings_patch_of_the_name_converts_the_docs(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        c = TestClient(server.app)
        try:
            self.assertEqual(c.patch('/api/settings', json={'name': 'owner_name', 'value': 'Alex Doyle'}).json(), {'ok': True})
            self.assertEqual(server.store.owner()['owner'], 'Alex Doyle')
            self.assertFalse(docs_hold_template_owner(server.store))
            self.assertNotIn('John', server.store.doc('agent'))
        finally: set_owner(server.store, '', None)


if __name__ == '__main__': unittest.main()
