"""The sources that sign in by OAuth (inboxes.py on oauth.py's tokens) and Mailgun's polled mail. HTTP faked by URL with payloads
shaped like each vendor's own API reference - no network. Each: Test learns who you are, the poll files only what is pointed at you,
and an author is a colleague only where the vendor's own data says so (senders._item_known, H2)."""
import json, unittest
from datetime import datetime
from unittest import mock
from urllib.parse import urlencode

from taskuary import inboxes
from tests.test_inboxes import FakeHTTP, R, again, conn, rows, trusted


class Fake(FakeHTTP):
    "FakeHTTP, matched on the url WITH its query: two reads of one path differ by what they ask."
    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        full = f"{url}?{urlencode(kw.get('params') or {}, doseq=True)}"
        for k in sorted(self.routes, key=len, reverse=True):
            if k in full: v = self.routes[k]; return v if isinstance(v, R) else R(v)
        raise AssertionError(f'unexpected url: {full}')


def wired(routes):
    inboxes._MEMO.clear()
    return mock.patch.object(inboxes, 'requests', Fake(routes))

SINCE = datetime(2026, 8, 1)
NEW = '2026-08-20T10:00:00.000Z'


class WebexTests(unittest.TestCase):
    def test_direct_messages_and_mentions_with_the_organization(self):
        s = MemoryStore(); c = conn(s, 'webex')
        with wired({'/people/me': {'id': 'P1', 'orgId': 'O1', 'displayName': 'Alex Doyle', 'emails': ['alex@northwind.example']},
                    '/rooms': {'items': [{'id': 'RD', 'title': 'Erin Blake', 'type': 'direct', 'lastActivity': NEW},
                                         {'id': 'RG', 'title': 'Launch', 'type': 'group', 'lastActivity': NEW},
                                         {'id': 'RO', 'title': 'Old', 'type': 'group', 'lastActivity': '2026-07-01T00:00:00.000Z'}]},
                    'roomId=RD': {'items': [{'id': 'M1', 'roomId': 'RD', 'personId': 'P2', 'personEmail': 'erin@northwind.example', 'text': 'got a minute?', 'created': NEW},
                                            {'id': 'M2', 'roomId': 'RD', 'personId': 'P1', 'personEmail': 'alex@northwind.example', 'text': 'sure', 'created': NEW}]},
                    'roomId=RG': {'items': [{'id': 'M3', 'roomId': 'RG', 'personId': 'P3', 'personEmail': 'pat@vendor.example', 'text': 'Alex, the quote?', 'created': NEW}]},
                    '/people/P2': {'id': 'P2', 'orgId': 'O1', 'displayName': 'Erin Blake'},
                    '/people/P3': {'id': 'P3', 'orgId': 'O9', 'displayName': 'Pat Vendor'}}) as h:
            self.assertIn('Alex Doyle', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        self.assertEqual([k['params'].get('mentionedPeople') for _, u, k in h.calls if u.endswith('/messages')], [None, 'me'])
        got = {r['FromName']: r for r in rows(s, 'webex')}
        self.assertTrue(trusted(s, got['Erin Blake'])); self.assertFalse(trusted(s, got['Pat Vendor']))
        self.assertEqual(got['Erin Blake']['ConversationId'], 'webex:RD')


class ZoomChatTests(unittest.TestCase):
    def test_direct_messages_mentions_and_outside_contacts(self):
        s = MemoryStore(); c = conn(s, 'zoom_chat')
        msg = lambda i, who, at=(): {'id': i, 'message': f'note {i}', 'sender': who, 'sender_display_name': who.split('@')[0], 'date_time': NEW, 'at_items': list(at)}
        with wired({'/users/me': {'id': 'Z1', 'email': 'alex@northwind.example', 'account_id': 'A1', 'display_name': 'Alex Doyle'},
                    '/chat/users/me/sessions': {'sessions': [{'peer_contact_email': 'erin@northwind.example', 'type': '1:1'},
                                                             {'channel_id': 'C1', 'name': 'ops', 'type': 'group'}]},
                    'to_contact': {'messages': [msg('m1', 'erin@northwind.example'), msg('m2', 'alex@northwind.example')]},
                    'to_channel': {'messages': [msg('m3', 'pat@vendor.example', [{'at_contact': 'Z1', 'at_type': 1}]), msg('m4', 'gail@northwind.example')]},
                    '/users/erin%40northwind.example': {'id': 'Z2'}, '/users/pat%40vendor.example': R({}, 404)}):
            inboxes.test(s, c)
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)                  # its own line and an unmentioned channel line are not work
        got = {r['FromEmail']: r for r in rows(s, 'zoom_chat')}
        self.assertTrue(trusted(s, got['erin@northwind.example'])); self.assertFalse(trusted(s, got['pat@vendor.example']))


class ThreadsTests(unittest.TestCase):
    def test_mentions_and_replies_are_strangers_and_its_own_reply_is_not_work(self):
        s = MemoryStore(); c = conn(s, 'threads')
        p = lambda i, u: {'id': i, 'text': f'hi {i}', 'username': u, 'timestamp': '2026-08-20T10:00:00+0000', 'permalink': f'https://www.threads.net/@{u}/post/{i}'}
        with wired({'/me?': {'id': 'T1', 'username': 'alexdoyle'},
                    '/T1/mentions': {'data': [p('x1', 'ray.colton')]}, '/T1/threads': {'data': [{'id': 'POST1', 'timestamp': NEW}]},
                    '/POST1/replies': {'data': [p('x2', 'omar.k'), p('x3', 'alexdoyle')]}}):
            self.assertIn('@alexdoyle', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        got = rows(s, 'threads')
        self.assertTrue(all(not trusted(s, r) for r in got))
        self.assertEqual({r['ConversationId'] for r in got}, {'threads:x1', 'threads:POST1'})


class HubSpotTests(unittest.TestCase):
    def test_tickets_and_open_tasks_assigned_to_me(self):
        s = MemoryStore(); c = conn(s, 'hubspot')
        with wired({'/oauth/v1/access-tokens/': {'user': 'alex@northwind.example', 'hub_id': 4242, 'user_id': 9, 'hub_domain': 'northwind.example'},
                    '/crm/v3/owners': {'results': [{'id': '77', 'email': 'alex@northwind.example'}]},
                    '/tickets/search': {'results': [{'id': '501', 'properties': {'subject': 'Login broken', 'content': 'cannot sign in', 'hs_ticket_priority': 'HIGH', 'hs_lastmodifieddate': NEW}}]},
                    '/tasks/search': {'results': [{'id': '601', 'properties': {'hs_task_subject': 'Call back', 'hs_task_status': 'NOT_STARTED', 'hs_timestamp': NEW,
                                                                               'hs_lastmodifieddate': NEW, 'hs_created_by_user_id': '12'}}]}}) as h:
            self.assertIn('alex@northwind.example', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        body = next(k['json'] for m, u, k in h.calls if u.endswith('/tasks/search'))
        self.assertIn({'propertyName': 'hubspot_owner_id', 'operator': 'EQ', 'value': '77'}, body['filterGroups'][0]['filters'])
        got = {r['Subject']: r for r in rows(s, 'hubspot')}
        self.assertEqual(got['Login broken']['SourceLink'], 'https://app.hubspot.com/contacts/4242/record/0-5/501')
        self.assertFalse(trusted(s, got['Login broken'])); self.assertTrue(trusted(s, got['Call back']))


class SalesforceTests(unittest.TestCase):
    def test_cases_and_tasks_and_who_wrote_them(self):
        s = MemoryStore(); c = conn(s, 'salesforce', {'host': 'https://northwind.my.salesforce.com'})
        case = {'Id': '500000000000001AAA', 'CaseNumber': '00001001', 'Subject': 'Refund', 'Status': 'New', 'Priority': 'High', 'LastModifiedDate': NEW,
                'ContactId': '003000000000001AAA', 'Contact': {'Name': 'Pat Customer', 'Email': 'pat@customer.example'}, 'CreatedById': '005000000000002AAA',
                'CreatedBy': {'Name': 'Site Guest', 'UserType': 'Guest'}}
        task = {'Id': '00T000000000001AAA', 'Subject': 'Send the contract', 'Status': 'Not Started', 'Priority': 'Normal', 'LastModifiedDate': NEW,
                'CreatedById': '005000000000003AAA', 'CreatedBy': {'Name': 'Gail Moreno', 'Email': 'gail@northwind.example', 'UserType': 'Standard'}}
        with wired({'/services/oauth2/userinfo': {'user_id': '005000000000001AAA', 'organization_id': '00D000000000001AAA', 'name': 'Alex Doyle'},
                    'FROM+Case': {'records': [case]}, 'FROM+Task': {'records': [task]}}) as h:
            inboxes.test(s, c)
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        soql = [k['params']['q'] for m, u, k in h.calls if u.endswith('/query')]
        self.assertTrue(all("OwnerId = '005000000000001AAA'" in q and 'IsClosed = false' in q for q in soql))
        got = {r['Subject']: r for r in rows(s, 'salesforce')}
        self.assertFalse(trusted(s, got['Case 00001001: Refund'])); self.assertTrue(trusted(s, got['Send the contract']))
        s.merge_connector_config(c['ConnectorId'], {'me_id': "x' OR Name != '"})
        with self.assertRaisesRegex(RuntimeError, 'run Test'): inboxes.ITEMS['salesforce'](s, again(s, c), SINCE)


class DocuSignTests(unittest.TestCase):
    def test_envelopes_waiting_on_my_signature_and_whose_account_sent_them(self):
        s = MemoryStore(); c = conn(s, 'docusign')
        env = lambda i, acct: {'envelopeId': f'e{i}-0000', 'emailSubject': f'Please sign {i}', 'status': 'sent', 'sentDateTime': NEW, 'statusChangedDateTime': NEW,
                               'sender': {'userName': f'Sender {i}', 'email': f's{i}@northwind.example', 'accountId': acct, 'userId': f'u{i}'}}
        with wired({'account.docusign.com/oauth/userinfo': {'name': 'Alex Doyle', 'email': 'alex@northwind.example', 'accounts': [
                        {'account_id': 'a1b2', 'is_default': True, 'account_name': 'Northwind', 'base_uri': 'https://na3.docusign.net'}]},
                    '/envelopes': {'envelopes': [env(1, 'a1b2'), env(2, 'ffff')]}}) as h:
            self.assertIn('Northwind', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        self.assertTrue(any('na3.docusign.net/restapi/v2.1/accounts/a1b2/envelopes' in u and k['params']['folder_ids'] == 'awaiting_my_signature' for m, u, k in h.calls))
        got = {r['Subject']: r for r in rows(s, 'docusign')}
        self.assertTrue(trusted(s, got['Please sign 1'])); self.assertFalse(trusted(s, got['Please sign 2']))
        self.assertEqual(got['Please sign 1']['SourceLink'], 'https://app.docusign.com/documents/details/e1-0000')


class BasecampTests(unittest.TestCase):
    def test_assigned_todos_pings_and_mentions_and_a_client_is_a_stranger(self):
        s = MemoryStore(); c = conn(s, 'basecamp_todos')
        person = lambda i, client=False: {'id': i, 'name': f'P{i}', 'email_address': f'p{i}@northwind.example', 'personable_type': 'User', 'client': client}
        with wired({'launchpad.37signals.com/authorization.json': {'identity': {'id': 1}, 'accounts': [{'product': 'bc3', 'id': 999, 'name': 'Northwind', 'href': 'https://3.basecampapi.com/999'}]},
                    '/my/profile.json': {'id': 10, 'name': 'Alex Doyle'},
                    '/my/assignments.json': {'priorities': [{'id': 7, 'content': 'Draft the memo', 'due_on': '2026-08-30', 'app_url': 'https://3.basecamp.com/999/x/7', 'bucket': {'id': 3, 'name': 'Ops'}}],
                                             'non_priorities': []},
                    '/buckets/3/todos/7.json': {'id': 7, 'description': '<div>by Friday</div>', 'updated_at': NEW, 'creator': person(11)},
                    '/my/readings.json': {'unreads': [{'id': 1, 'section': 'pings', 'title': 'Ping', 'content_excerpt': 'quick q', 'app_url': 'https://3.basecamp.com/999/c/1',
                                                       'readable_sgid': 'sg1', 'created_at': NEW, 'creator': person(12, client=True)},
                                                      {'id': 2, 'section': 'inbox', 'title': 'Newsletter', 'created_at': NEW, 'creator': person(13)}]}}) as h:
            self.assertIn('Northwind', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        self.assertTrue(all('Taskuary' in k['headers']['User-Agent'] for m, u, k in h.calls))
        got = {r['Subject']: r for r in rows(s, 'basecamp_todos')}
        self.assertTrue(trusted(s, got['Draft the memo'])); self.assertFalse(trusted(s, got['Ping']))


class MailgunTests(unittest.TestCase):
    def test_stored_mail_is_polled_from_its_own_domain(self):
        s = MemoryStore(); c = conn(s, 'mailgun', {'domain': 'mg.northwind.example'})
        with wired({'/v3/mg.northwind.example/events': {'items': [{'event': 'stored', 'timestamp': 1787300000.5, 'storage': {'key': 'KEY1', 'url': 'https://storage.example/x'},
                                                                   'message': {'headers': {'from': 'Erin Blake <erin@vendor.example>', 'subject': 'PO 7', 'message-id': 'po7@vendor.example'}}}]},
                    '/v3/domains/mg.northwind.example/messages/KEY1': {'from': 'Erin Blake <erin@vendor.example>', 'subject': 'PO 7', 'stripped-text': 'Please confirm PO 7.',
                                                                      'recipient': 'orders@mg.northwind.example'}}) as h:
            self.assertIn('mg.northwind.example', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 1)
        self.assertTrue(all(k['auth'][0] == 'api' and 'storage.example' not in u for m, u, k in h.calls))   # never the storage url's own host
        r = rows(s, 'mailgun')[0]
        self.assertEqual((r['Subject'], r['FromEmail']), ('PO 7', 'erin@vendor.example'))
        s.merge_connector_config(c['ConnectorId'], {'host': 'https://evil.example'})
        with self.assertRaisesRegex(RuntimeError, 'api.mailgun.net'): inboxes.test(s, again(s, c))


from taskuary.store import MemoryStore     # noqa: E402 - kept beside the helpers it is used with

if __name__ == '__main__':
    unittest.main()
