"""A WhatsApp group "connected but not showing up" - the Assistant names the actual cause.

2026-10-28: a group was switched on and its messages came in, every one joined to the open task about that group - but they were
stored under "group chat", never the group's name, so the Assistant searched by the name, found nothing, said "its group selection
needs checking" and brought up the whole Connections page. Now a group's messages carry its name, and app.health with `chat` reads
the card's own switch and the messages kept: not switched on (and the Chats step opened on that name), or coming in and where.
"""
import unittest
from unittest import mock

from taskuary import messengers, troubleshoot, wanames
from taskuary.store import MemoryStore

TEAM, OTHER, LONE = '120363000000000101@g.us', '120363000000000102@g.us', '120363000000000103@g.us'
ROSTER = [{'jid': TEAM, 'group': True, 'name': 'The Northwind Team', 'n': 0, 'last': '', 'snippet': '', 'people': 3},
          {'jid': OTHER, 'group': True, 'name': 'The Northwind - Ledger', 'n': 0, 'last': '', 'snippet': '', 'people': 3},
          {'jid': LONE, 'group': True, 'name': 'Book club', 'n': 0, 'last': '', 'snippet': '', 'people': 9}]


def _store(*on):
    s = MemoryStore()
    cid = s.get_connector_by_type('whatsapp')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Active': 1}, 'o')
    for jid in on: s.save_source({'Channel': 'whatsapp', 'Address': jid, 'ConnectorId': cid, 'Active': 1}, 'o')
    wanames.remember(s, ROSTER)
    return s, s.get_connector_by_type('whatsapp', with_secret=True)


def _poll(s, c, *msgs):
    feed = {'seq': len(msgs), 'messages': [{'seq': i + 1, 'jid': TEAM, 'group': True, 'sender': '15550100100@s.whatsapp.net',
                                            'ts': 1793200000 + i, **m} for i, m in enumerate(msgs)]}
    with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: feed):
        return messengers.poll_whatsapp(s, c, s.list_sources(), llm=None)


def _health(s, chat, name='whatsapp', admits=None):
    st = {'line': 'Connected · 1 chat', 'fix': '', 'filter': {'jids': admits if admits is not None else [TEAM]}}
    with mock.patch.object(messengers, 'wa_status', lambda c: st), mock.patch.object(messengers, 'wa_chats', lambda c, store=None: [dict(r) for r in ROSTER]):
        return troubleshoot.health(s, name, chat=chat)


class AGroupsMessagesCarryItsName(unittest.TestCase):
    def setUp(self): messengers._RENAMED.clear()

    def test_a_group_message_is_stored_under_the_groups_name_and_found_by_it(self):
        s, c = _store(TEAM)
        _poll(s, c, {'id': 'a1', 'name': 'Erin', 'text': 'the export is late again'})
        self.assertEqual([r['SourceName'] for r in s._rows("SELECT SourceName FROM message WHERE Channel='whatsapp'")], ['The Northwind Team'])

    def test_the_older_messages_filed_as_group_chat_get_the_name_too(self):
        s, c = _store(TEAM)
        s._exec("INSERT INTO message (ConversationId, Channel, SourceName, BodyText, SentAt) VALUES (?, 'whatsapp', 'group chat', 'old', '2026-10-01 09:00:00')",
                (f'whatsapp:{TEAM}',))
        _poll(s, c, {'id': 'a2', 'name': 'Erin', 'text': 'and again today'})
        self.assertEqual({r['SourceName'] for r in s._rows("SELECT SourceName FROM message WHERE Channel='whatsapp'")}, {'The Northwind Team'})

    def test_a_group_nobody_has_named_yet_still_says_group_chat(self):
        s, c = _store(TEAM)
        s.set_setting(wanames.KEY, '{}', 't')
        _poll(s, c, {'id': 'a3', 'name': 'Erin', 'text': 'hello'})
        self.assertEqual(s._rows("SELECT SourceName FROM message WHERE Channel='whatsapp'")[0]['SourceName'], 'group chat')


class TheAssistantNamesTheCause(unittest.TestCase):
    def setUp(self):
        messengers._RENAMED.clear()
        from taskuary import wabridge
        for k, v in (('managed', lambda c: True), ('node', lambda: 'node'), ('state', lambda: {'phase': 'running'}),
                     ('log', lambda: __import__('pathlib').Path('no-such.log'))):
            p = mock.patch.object(wabridge, k, v); p.start(); self.addCleanup(p.stop)

    def test_a_group_not_switched_on_says_so_and_opens_the_chats_step_on_its_name(self):
        s, _ = _store()
        h = _health(s, 'Northwind Team')
        self.assertFalse(h['ok'])
        self.assertIn('"The Northwind Team" is not switched on under WhatsApp\'s Chats', h['why'])
        self.assertEqual(h['fix'], {'label': troubleshoot.CHATS, 'href': '#connector=whatsapp&chats=Northwind%20Team'})
        self.assertEqual(troubleshoot.chips(h), [{'verb': 'go', 'href': '#connector=whatsapp&chats=Northwind%20Team', 'label': troubleshoot.CHATS}])
        self.assertIn("Open WhatsApp's Chats", troubleshoot.words(h))

    def test_a_group_coming_in_says_where_its_messages_went(self):
        s, c = _store(TEAM)
        _poll(s, c, {'id': 'b1', 'name': 'Erin', 'text': 'can we move the export to Friday?'})
        self.assertIn('the newest is on no task', _health(s, 'northwind team')['why'], 'no AI here: it waits for triage')
        tid = s.create_task({'Title': 'Move the export to Friday', 'Source': 'whatsapp'}, 't')
        s._exec("UPDATE message SET TaskId=? WHERE Channel='whatsapp'", (tid,))
        h = _health(s, 'northwind team')
        self.assertTrue(h['ok'], h['why'])
        self.assertIn('"The Northwind Team" is switched on and coming in: 1 message kept', h['why'])
        self.assertIn(f'the newest is on TQ-{tid:04d} "Move the export to Friday" (open)', h['why'])
        self.assertEqual(troubleshoot.chips(h), [{'verb': 'go', 'href': f'#task={tid}', 'label': f'Open TQ-{tid:04d}'}])
        self.assertIn('That chat is coming in', troubleshoot.words(h))

    def test_two_groups_by_that_name_say_which_one_comes_in(self):
        s, c = _store(TEAM)
        h = _health(s, 'The Northwind')
        self.assertIn('"The Northwind Team" is switched on', h['why'])
        self.assertIn('also by that name, not switched on: "The Northwind - Ledger"', h['why'])

    def test_switched_on_but_the_bridge_not_told_offers_a_sync(self):
        s, _ = _store(TEAM)
        h = _health(s, 'Northwind Team', admits=[])
        self.assertEqual((h['ok'], h['repair']), (False, 'sync'))

    def test_no_chat_by_that_name_says_so(self):
        s, _ = _store(TEAM)
        h = _health(s, 'Southwind')
        self.assertFalse(h['ok'])
        self.assertIn('no chat on this WhatsApp account is called "Southwind"', h['why'])
        self.assertEqual(h['fix']['href'], '#connector=whatsapp&chats=')

    def test_the_chat_named_as_the_connection_is_read_as_the_chat(self):
        """The model passing the group's name as `name` reads that chat, not "Checked what is failing: nothing"."""
        s, _ = _store()
        h = _health(s, '', name='Northwind Team')
        self.assertEqual(h['type'], 'whatsapp')
        self.assertIn('not switched on', h['why'])

    def test_a_connector_card_name_is_still_the_connection(self):
        s, _ = _store(TEAM)
        h = _health(s, '')
        self.assertNotIn('chat', h)


if __name__ == '__main__':
    unittest.main()
