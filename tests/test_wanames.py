"""A WhatsApp chat is found by its name, its phone number in any form, or its group's name - never by its JID (wanames.py;
the owner, 2026-10-23). Every number here is a 555-01xx fiction and every group id invented."""
import unittest
from unittest import mock
from taskuary import messengers, outbound, remote_assistant, search, wanames
from taskuary.store import MemoryStore

ERIN, RAY, OPS = '15550100123@s.whatsapp.net', '15550100188@s.whatsapp.net', '120363000000000001@g.us'
ROSTER = {'chats': [
    {'jid': OPS, 'group': True, 'name': 'Northwind ops', 'n': 3, 'last': 1755700300, 'people': 6},
    {'jid': ERIN, 'group': False, 'name': 'Erin Blake', 'n': 2, 'last': 1755700200},
    {'jid': RAY, 'group': False, 'name': '', 'n': 1, 'last': 1755700100}]}


def find(rows, q): return [r['jid'] for r in rows if wanames.matches(q, r['jid'], r['name'])]


class MatchTests(unittest.TestCase):
    rows = [{'jid': j, 'name': n} for j, n in ((ERIN, 'Erin Blake'), (RAY, ''), (OPS, 'Northwind ops'))]

    def test_by_name_and_group_name(self):
        self.assertEqual(find(self.rows, 'erin'), [ERIN])
        self.assertEqual(find(self.rows, 'BLAKE erin'), [ERIN])
        self.assertEqual(find(self.rows, 'northwind'), [OPS])
        self.assertEqual(find(self.rows, 'ops'), [OPS])

    def test_by_phone_digits_in_any_common_form(self):
        for q in ('+1 555 010 0123', '+1 (555) 010-0123', '1-555-010-0123', '15550100123', '555.010.0123', '0015550100123',
                  '010-0123', '+1 555-010-0123'):
            self.assertEqual(find(self.rows, q), [ERIN], q)
        self.assertEqual(find(self.rows, '555 0100'), [ERIN, RAY])          # the shared start finds both people, no group

    def test_never_by_the_id(self):
        for q in ('120363', '120363000000000001@g.us', 's.whatsapp.net', 'whatsapp.net', '@g.us', ERIN):
            self.assertEqual(find(self.rows, q), [], q)

    def test_a_number_standing_in_for_a_name_is_not_a_name(self):
        self.assertTrue(wanames.bare('15550100188', RAY))
        self.assertTrue(wanames.bare('+1 555-010-0188', RAY))
        self.assertFalse(wanames.bare('Ray Colton', RAY))
        self.assertEqual(wanames.label(RAY, '15550100188'), '+1 555-010-0188')
        self.assertEqual(wanames.label(OPS), 'WhatsApp group')
        self.assertEqual(wanames.label(ERIN, 'Erin Blake'), 'Erin Blake')
        self.assertEqual(wanames.phone('442079460000@s.whatsapp.net'), '+442079460000')
        self.assertEqual(wanames.phone(OPS), '')


class RosterTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.c = {'ConnectorId': 1, 'Type': 'whatsapp', 'Active': 1, 'Name': 'WhatsApp', 'ConfigJson': '{}'}

    def chats(self, roster=ROSTER):
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: roster): return messengers.wa_chats(self.c, self.s)

    def test_rows_carry_the_phone_and_the_names_are_kept_for_when_the_bridge_forgets_them(self):
        rows = {r['jid']: r for r in self.chats()}
        self.assertEqual((rows[ERIN]['phone'], rows[OPS]['phone']), ('+1 555-010-0123', ''))
        self.assertEqual(wanames.names(self.s), {OPS: 'Northwind ops', ERIN: 'Erin Blake'})
        # the bridge restarted: its roster lives in memory and the saved names arrive a moment later
        cold = {'chats': [{**r, 'name': ''} for r in ROSTER['chats']]}
        self.assertEqual({r['jid']: r['name'] for r in self.chats(cold)}, {OPS: 'Northwind ops', ERIN: 'Erin Blake', RAY: ''})

    def test_a_person_the_bridge_has_no_name_for_is_named_by_their_last_line(self):
        self.s.add_message({'Channel': 'whatsapp', 'BodyText': 'hi', 'ConversationId': f'whatsapp:{RAY}', 'FromName': 'Ray Colton',
                            'FromEmail': 'whatsapp:15550100188', 'SentAt': '2026-10-13 09:00:00', 'Status': 'filed',
                            'Direction': 'in', 'ExternalId': 'wa:1'})
        self.assertEqual({r['jid']: r['name'] for r in self.chats()}[RAY], 'Ray Colton')

    # The owner, 2026-10-26: "the whatsapp contacts people tab are still not searchable by name as well" - the People rows
    # were bare numbers, because the address book never arrived and a person who wrote only in a group was never named
    def test_a_person_known_only_by_a_group_line_is_named_and_found_by_it_on_the_people_tab(self):
        grp = lambda who, num, alias, n: self.s.add_message({
            'Channel': 'whatsapp', 'BodyText': 'standup moved', 'ConversationId': f'whatsapp:{OPS}', 'FromName': who,
            'FromEmail': f'whatsapp:{num}', 'SentAt': f'2026-10-2{n} 09:00:00', 'Status': 'filed', 'Direction': 'in',
            'ExternalId': f'wa:g{n}', 'MailMetaJson': '{"alias": "whatsapp:%s"}' % alias if alias else None})
        grp('Ray Colton', '15550100188', '', 1)
        grp('Gail Moreno', '88001', '15550100155', 2)              # written by LID; the poller kept her number as the alias
        grp('15550100166', '15550100166', '', 3)                   # a number for a name is not one
        GAIL, OMAR, LIDP = '15550100155@s.whatsapp.net', '15550100166@s.whatsapp.net', '88001@lid'
        roster = {'chats': [{'jid': j, 'group': False, 'name': '', 'n': 0, 'last': 1} for j in (RAY, GAIL, OMAR)]
                  + [{'jid': LIDP, 'group': False, 'name': '', 'n': 0, 'last': 1}, ROSTER['chats'][0]]}
        rows = self.chats(roster)
        self.assertEqual({r['jid']: r['name'] for r in rows}, {RAY: 'Ray Colton', GAIL: 'Gail Moreno', OMAR: '', LIDP: 'Gail Moreno',
                                                               OPS: 'Northwind ops'})
        for q in ('ray', 'RAY colton', 'colton'): self.assertEqual(find(rows, q), [RAY], q)
        self.assertEqual(find(rows, 'gail'), [GAIL, LIDP])
        self.assertEqual(find(rows, '+1 555 010 0188'), [RAY])

    def test_a_lid_row_the_roster_named_is_kept_like_any_other(self):
        self.chats({'chats': [{'jid': '88002@lid', 'group': False, 'name': 'Marcus Reed', 'n': 0, 'last': 1}]})
        self.assertEqual(wanames.names(self.s), {'88002@lid': 'Marcus Reed'})
        self.assertEqual([r['name'] for r in self.chats({'chats': [{'jid': '88002@lid', 'group': False, 'name': '', 'n': 0, 'last': 1}]})],
                         ['Marcus Reed'])

    # "We lost the names" (2026-11-02): a bridge restarted by an update holds only what happened since, and a group roster ask that
    # timed out left it no group at all. The switched-on chats fell off the card's list onto raw ids, and a search by name found nobody.
    def test_a_restarted_bridge_still_lists_the_switched_on_chats_by_name_and_the_people_kept(self):
        self.chats()                                                       # the names are kept while the bridge knew them
        self.s.add_message({'Channel': 'whatsapp', 'BodyText': 'rota attached', 'ConversationId': f'whatsapp:{ERIN}', 'FromName': 'EB',
                            'FromEmail': 'whatsapp:15550100123', 'SentAt': '2026-10-30 09:15:00', 'Status': 'filed',
                            'Direction': 'in', 'ExternalId': 'wa:k1'})
        for a in (OPS, ERIN): self.s.save_source({'Channel': 'whatsapp', 'Address': a, 'Active': 1, 'ConnectorId': 1}, 't')
        stranger = '15550100199@s.whatsapp.net'
        cold = {'chats': [{'jid': stranger, 'group': False, 'name': '', 'n': 0, 'last': 0}]}
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: cold):
            rows = {r['jid']: r for r in messengers.wa_chats(self.c, self.s, kept=True)}
            live = [r['jid'] for r in messengers.wa_chats(self.c, self.s)]
        self.assertEqual(live, [stranger], 'the send picker and the doorway still see the live roster alone')
        self.assertEqual({j: r['name'] for j, r in rows.items()}, {OPS: 'Northwind ops', ERIN: 'Erin Blake', stranger: ''})
        self.assertEqual((rows[ERIN]['n'], rows[ERIN]['last'], rows[ERIN]['kept']), (1, '2026-10-30 09:15', True))
        self.assertEqual(find(list(rows.values()), 'erin'), [ERIN])
        self.assertEqual(find(list(rows.values()), 'northwind'), [OPS])

    def test_a_kept_group_stands_in_only_while_the_bridge_lists_none_and_a_lid_is_never_a_second_row(self):
        self.s.set_setting(wanames.KEY, '{"%s": "Northwind ops", "88003@lid": "Erin Blake", "%s": "Erin Blake"}' % (OPS, ERIN), 't')
        other = {'jid': '120363000000000002@g.us', 'group': True, 'name': 'Payworth rollout', 'n': 0, 'last': 1755700000}
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: {'chats': [other]}):
            rows = [r['jid'] for r in messengers.wa_chats(self.c, self.s, kept=True)]
        self.assertEqual(rows, [other['jid'], ERIN], 'a group the owner left is not brought back while the bridge lists its groups')
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: {'chats': []}):
            cold = {r['jid']: r['name'] for r in messengers.wa_chats(self.c, self.s, kept=True)}
        self.assertEqual(cold, {OPS: 'Northwind ops', other['jid']: 'Payworth rollout', ERIN: 'Erin Blake'})

    # The owner, 2026-11-02: the switched-on chats show their last message on the card's list - from the saved messages, one read
    def test_a_switched_on_chat_shows_its_last_saved_line_and_an_off_chat_none(self):
        def msg(conv, who, body, at, n, out=False):
            return self.s.add_message({'Channel': 'whatsapp', 'BodyText': body, 'ConversationId': f'whatsapp:{conv}', 'FromName': who,
                                       'FromEmail': 'whatsapp:15550100155', 'SentAt': at, 'Status': 'filed',
                                       'Direction': 'out' if out else 'in', 'ExternalId': f'wa:s{n}'})
        msg(OPS, 'Gail Moreno', 'old line', '2026-11-01 08:00:00', 1)
        msg(OPS, 'Gail Moreno', 'standup   moved\nto ten ' + 'x' * 200, '2026-11-02 09:00:00', 2)
        msg(ERIN, 'Erin Blake', 'see you there', '2026-11-02 08:00:00', 3, out=True)
        msg(RAY, 'Ray Colton', 'not taken in', '2026-11-02 07:00:00', 4)
        for a, on in ((OPS, 1), (ERIN, 1), (RAY, 0)): self.s.save_source({'Channel': 'whatsapp', 'Address': a, 'Active': on, 'ConnectorId': 1}, 't')
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: ROSTER):
            rows = {r['jid']: r for r in messengers.wa_chats(self.c, self.s, kept=True)}
            plain = messengers.wa_chats(self.c, self.s)
        ops = rows[OPS]['said']
        self.assertEqual((ops['from'], ops['at']), ('Gail Moreno', '2026-11-02 09:00:00'))
        self.assertTrue(ops['text'].startswith('standup moved to ten x') and ops['text'].endswith('…') and len(ops['text']) == wanames.PREVIEW)
        self.assertEqual(rows[ERIN]['said'], {'from': 'You', 'text': 'see you there', 'at': '2026-11-02 08:00:00'})
        self.assertNotIn('said', rows[RAY], 'an off chat shows no text')
        self.assertFalse(any('said' in r for r in plain), 'the pickers read the roster alone')

    def test_a_preview_says_what_media_was(self):
        from taskuary import voice
        self.assertEqual(wanames.preview('(no text - see the attachment)', 'image/jpeg', 'a.jpg'), 'photo')
        self.assertEqual(wanames.preview('look at this', 'image/jpeg'), 'photo: look at this')
        self.assertEqual(wanames.preview(f'call me back after lunch\n\n({voice.MARK.lower()} (5s) from WhatsApp, transcribed by Groq)',
                                         'audio/ogg'), 'voice note: call me back after lunch')
        self.assertEqual(wanames.preview(f'{voice.MARK} (5s) from WhatsApp - not transcribed: no key. Add a connector', 'audio/ogg'), 'voice note')
        self.assertEqual(wanames.preview('(no text - see the attachment)', 'application/pdf', 'rota.pdf'), 'file rota.pdf')
        self.assertEqual(wanames.preview('plain words'), 'plain words')

    def test_send_targets_name_and_number_whatsapp_never_the_jid(self):
        with mock.patch.object(outbound, 'send_channels', return_value=['whatsapp']), \
             mock.patch.object(self.s, 'list_connectors', return_value=[self.c]), \
             mock.patch.object(messengers, '_wa', lambda c_, p, body=None: ROSTER):
            to = {r['to']: r for t in outbound.send_targets(self.s) if t['channel'] == 'whatsapp' for r in t['to']}
        self.assertEqual((to[ERIN]['name'], to[RAY]['name'], to[OPS]['name']), ('Erin Blake', '+1 555-010-0188', 'Northwind ops'))
        self.assertEqual(to[RAY]['phone'], '+1 555-010-0188')

    def test_the_phone_doorway_offers_names_not_ids(self):
        mine = {'chats': [{'jid': '15550100100-1600000000@g.us', 'group': True, 'name': '', 'n': 0, 'last': 1, 'people': 1}]}
        with mock.patch.object(messengers, '_wa', lambda c_, p, body=None: mine), \
             mock.patch.object(remote_assistant, 'own_thread', return_value=True):
            opts = remote_assistant.candidates(self.s, self.c)
        self.assertEqual([o['name'] for o in opts], ['WhatsApp group'])


class SearchEverythingTests(unittest.TestCase):
    def setUp(self):
        self.s = s = MemoryStore()
        s.set_setting(wanames.KEY, '{"%s": "Erin Blake", "%s": "Northwind ops"}' % (ERIN, OPS), 't')
        def wa(conv, who, num, body, n):
            return s.add_message({'Channel': 'whatsapp', 'BodyText': body, 'ConversationId': f'whatsapp:{conv}', 'FromName': who,
                                  'FromEmail': f'whatsapp:{num}', 'SentAt': f'2026-10-1{n} 09:00:00', 'Status': 'filed',
                                  'Direction': 'in', 'SourceName': 'group chat' if conv == OPS else who, 'ExternalId': f'wa:{n}'})
        self.dm = wa(ERIN, 'EB', '15550100123', 'the rota is attached', 1)       # her own push name is not the saved one
        self.grp = wa(OPS, 'Paula', '15550100177', 'standup moved to ten', 2)
        self.bare = wa(RAY, '15550100188', '15550100188', 'call me back', 3)
        for a in (ERIN, OPS): s.save_source({'Channel': 'whatsapp', 'Address': a, 'Active': 1}, 't')

    def hits(self, q, kind): return [h for h in search.everything(self.s, q)['hits'] if h['type'] == kind]

    def test_a_chat_by_the_saved_name_the_group_name_and_the_number(self):
        self.assertIn(self.dm, [h['mid'] for h in self.hits('erin blake', 'chat')])
        self.assertIn(self.grp, [h['mid'] for h in self.hits('northwind ops', 'chat')])
        for q in ('+1 (555) 010-0123', '555-010-0123', '15550100123'):
            self.assertEqual([h['mid'] for h in self.hits(q, 'chat')][:1], [self.dm], q)

    def test_the_line_names_who_and_where_not_a_number_or_an_id(self):
        h = {x['mid']: x for x in self.hits('call', 'chat') + self.hits('standup', 'chat')}
        self.assertEqual(h[self.bare]['who'], '+1 555-010-0188')
        self.assertEqual(h[self.grp]['where'], 'Northwind ops')

    def test_a_source_is_titled_by_name_found_by_name_and_number_never_by_its_id(self):
        src = self.hits('northwind', 'source')
        self.assertEqual([(h['title'], h['sub']) for h in src], [('Northwind ops', OPS)])
        self.assertEqual([h['title'] for h in self.hits('555 010 0123', 'source')], ['Erin Blake'])
        self.assertEqual(self.hits('120363000000000001', 'source'), [])
