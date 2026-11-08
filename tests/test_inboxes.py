"""The helpdesks and newer trackers (inboxes.py): Zendesk, Freshdesk, Intercom, ServiceNow, Shortcut, Wrike, Smartsheet,
Airtable, GitHub Projects, Bitbucket, Microsoft Planner. HTTP faked by URL with payloads shaped like each vendor's own API
reference - no network. Each source: Test learns who you are, the poll files only the work pointed at you, and an item's
author is a member only where the vendor's own data says so (senders._item_known, H2)."""
import json, unittest
from datetime import datetime
from unittest import mock
import requests as real_requests

from taskuary import inboxes, senders
from taskuary.store import MemoryStore

SINCE = datetime(2026, 8, 1)


class R:
    def __init__(self, j, status=200): self._j, self.status_code, self.text = j, status, ''
    def json(self): return self._j
    def raise_for_status(self):
        if self.status_code >= 400: raise real_requests.HTTPError(str(self.status_code))


class FakeHTTP:
    """Route by URL substring, longest first - an unexpected call fails the test instead of reaching the network."""
    RequestException, HTTPError = real_requests.RequestException, real_requests.HTTPError
    def __init__(self, routes): self.routes, self.calls = routes, []
    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        for k in sorted(self.routes, key=len, reverse=True):
            if k in url: v = self.routes[k]; return v if isinstance(v, R) else R(v)
        raise AssertionError(f'unexpected url: {url}')
    get = lambda self, url, **kw: self.request('get', url, **kw)


def wired(routes):
    inboxes._MEMO.clear()
    return mock.patch.object(inboxes, 'requests', FakeHTTP(routes))


def conn(s, typ, cfg=None):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1, **({'ConfigJson': json.dumps(cfg)} if cfg else {})}, 't')
    return s.get_connector(cid, with_secret=True)


def again(s, c): return s.get_connector(c['ConnectorId'], with_secret=True)
def rows(s, ch): return [dict(r) for r in s.cx.execute('SELECT * FROM message WHERE Channel=? ORDER BY MessageId', (ch,)).fetchall()]
def meta(r): return json.loads(r.get('MailMetaJson') or '{}')
def trusted(s, r): return senders.known(s, {'channel': r['Channel'], 'from_name': r['FromName'], 'source_name': r['SourceName'],
                                             'mail_meta': meta(r)})[0]


class ZendeskTests(unittest.TestCase):
    def test_assigned_and_new_in_group_with_the_requesters_role(self):
        s = MemoryStore(); c = conn(s, 'zendesk', {'subdomain': 'northwind', 'email': 'alex@northwind.example'})
        t = lambda i, req, **kw: {'id': i, 'subject': f'Ticket {i}', 'description': 'printer jam', 'status': 'open', 'priority': 'high',
                                   'requester_id': req, 'updated_at': '2026-08-20T10:00:00Z', **kw}
        with wired({'/users/me.json': {'user': {'id': 7, 'name': 'Alex Doyle', 'role': 'agent'}},
                    '/users/7/group_memberships.json': {'group_memberships': [{'group_id': 30}]},
                    '/users/7/tickets/assigned.json': {'tickets': [t(1, 100), t(2, 101, status='solved')],
                                                       'users': [{'id': 100, 'name': 'Erin Blake', 'role': 'agent'}]},
                    '/search.json': {'results': [t(3, 102, status='new')], 'users': [{'id': 102, 'name': 'Pat Customer', 'role': 'end-user'}]}}) as h:
            self.assertIn('1 group', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        self.assertIn('group:30', json.dumps(h.calls[-1][2]))
        got = {r['Subject']: r for r in rows(s, 'zendesk')}
        self.assertEqual(set(got), {'#1 Ticket 1', '#3 Ticket 3'})                    # a solved ticket is not work
        self.assertEqual(got['#1 Ticket 1']['SourceLink'], 'https://northwind.zendesk.com/agent/tickets/1')
        self.assertTrue(trusted(s, got['#1 Ticket 1']))                              # a colleague agent
        self.assertFalse(trusted(s, got['#3 Ticket 3']))                             # a customer is a stranger

    def test_an_anonymous_answer_is_a_failed_sign_in(self):
        s = MemoryStore(); c = conn(s, 'zendesk', {'subdomain': 'northwind', 'email': 'x'})
        with wired({'/users/me.json': {'user': {'id': None, 'name': 'Anonymous user', 'role': 'end-user'}}}):
            with self.assertRaisesRegex(RuntimeError, 'not sign you in as an agent'): inboxes.test(s, c)


class FreshdeskTests(unittest.TestCase):
    def test_mine_and_group_new_and_agents_are_members(self):
        s = MemoryStore(); c = conn(s, 'freshdesk', {'domain': 'northwind'})
        tk = lambda i, **kw: {'id': i, 'subject': f'T{i}', 'description_text': 'vpn down', 'status': 2, 'priority': 3,
                              'updated_at': '2026-08-20T10:00:00Z', 'requester': {'id': 50 + i, 'name': f'P{i}', 'email': f'p{i}@vendor.example'},
                              'requester_id': 50 + i, **kw}
        with wired({'/api/v2/agents/me': {'id': 9, 'group_ids': [4], 'contact': {'name': 'Alex Doyle'}},
                    '/api/v2/tickets': [tk(1, responder_id=9), tk(2, responder_id=None, group_id=4), tk(3, responder_id=12), tk(4, responder_id=9, status=5)],
                    '/api/v2/agents': [{'id': 51}, {'id': 9}]}):
            self.assertIn('Alex Doyle', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        got = {r['Subject']: r for r in rows(s, 'freshdesk')}
        self.assertEqual(set(got), {'#1 T1', '#2 T2'})
        self.assertTrue(trusted(s, got['#1 T1'])); self.assertFalse(trusted(s, got['#2 T2']))


class IntercomTests(unittest.TestCase):
    def test_assigned_open_conversations_and_teammates(self):
        s = MemoryStore(); c = conn(s, 'intercom')
        cv = lambda i, kind: {'id': str(i), 'title': None, 'state': 'open', 'updated_at': 1787300000, 'priority': 'not_priority',
                              'source': {'subject': '', 'body': '<p>Can you <b>reset</b> my access?</p>',
                                         'author': {'type': kind, 'id': f'a{i}', 'name': f'N{i}', 'email': f'n{i}@vendor.example'}}}
        with wired({'api.intercom.io/me': {'type': 'admin', 'id': '814', 'name': 'Alex Doyle', 'app': {'id_code': 'abc1', 'name': 'Northwind'}},
                    '/conversations/search': {'conversations': [cv(1, 'user'), cv(2, 'admin')]}}) as h:
            inboxes.test(s, c)
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        q = h.calls[-1][2]['json']['query']['value']
        self.assertIn({'field': 'admin_assignee_id', 'operator': '=', 'value': '814'}, q)
        got = {r['FromName']: r for r in rows(s, 'intercom')}
        self.assertIn('reset', got['N1']['BodyText']); self.assertNotIn('<b>', got['N1']['BodyText'])
        self.assertEqual(got['N1']['SourceLink'], 'https://app.intercom.com/a/inbox/abc1/inbox/conversation/1')
        self.assertFalse(trusted(s, got['N1'])); self.assertTrue(trusted(s, got['N2']))


class ServiceNowTests(unittest.TestCase):
    def test_incidents_and_an_outside_caller(self):
        s = MemoryStore(); c = conn(s, 'servicenow', {'instance': 'northwind', 'username': 'alex.doyle'})
        ref = lambda v, d: {'value': v, 'display_value': d, 'link': f'https://northwind.service-now.com/api/now/table/sys_user/{v}'}
        inc = lambda i, caller: {'sys_id': {'value': f's{i}', 'display_value': f's{i}'}, 'number': {'value': f'INC00{i}', 'display_value': f'INC00{i}'},
                                 'short_description': {'value': 'Laptop will not boot', 'display_value': 'Laptop will not boot'},
                                 'description': {'value': 'black screen', 'display_value': 'black screen'},
                                 'priority': {'value': '2', 'display_value': '2 - High'}, 'state': {'value': '2', 'display_value': 'In Progress'},
                                 'sys_updated_on': {'value': '2026-08-20 10:00:00', 'display_value': '2026-08-20 06:00:00'},
                                 'caller_id': caller, 'opened_by': ref('u9', 'Help Desk')}
        with wired({'/table/sys_user': {'result': [{'sys_id': 'me1', 'name': 'Alex Doyle'}]},
                    '/table/incident': {'result': [inc(1, ref('u1', 'Erin Blake')), inc(2, ref('u2', 'Pat Customer'))]},
                    '/table/sys_user/u1': {'result': {'sys_class_name': 'sys_user'}},
                    '/table/sys_user/u2': {'result': {'sys_class_name': 'customer_contact'}}}) as h:
            self.assertIn('incident', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        self.assertIn('assigned_to=me1', h.calls[1][2]['params']['sysparm_query'])
        got = {r['FromName']: r for r in rows(s, 'servicenow')}
        self.assertTrue(got['Erin Blake']['Subject'].startswith('INC001'))
        self.assertIn('nav_to.do?uri=incident.do%3Fsys_id%3Ds1', got['Erin Blake']['SourceLink'])
        self.assertTrue(trusted(s, got['Erin Blake'])); self.assertFalse(trusted(s, got['Pat Customer']))

    def test_a_table_name_cannot_walk_elsewhere(self):
        s = MemoryStore(); c = conn(s, 'servicenow', {'instance': 'northwind', 'username': 'a', 'tables': 'incident,../x', 'me_id': 'm'})
        with wired({}), self.assertRaisesRegex(RuntimeError, 'not a ServiceNow table'): inboxes.poll(s, c, SINCE)


class ShortcutTests(unittest.TestCase):
    def test_stories_i_own_and_requesters_are_members(self):
        s = MemoryStore(); c = conn(s, 'shortcut')
        st = lambda i, req: {'id': i, 'name': f'Story {i}', 'description': 'd', 'story_type': 'bug', 'app_url': f'https://app.shortcut.com/nw/story/{i}',
                             'updated_at': '2026-08-20T10:00:00Z', 'requested_by_id': req}
        with wired({'/api/v3/member': {'id': 'm-me', 'profile': {'name': 'Alex Doyle', 'mention_name': 'alex'}, 'workspace2': {'url_slug': 'northwind'}},
                    '/search/stories': {'data': [st(1, 'm-erin'), st(2, 'm-gone')]},
                    '/api/v3/members': [{'id': 'm-erin', 'profile': {'name': 'Erin Blake'}}, {'id': 'm-gone', 'disabled': True, 'profile': {}}]}) as h:
            inboxes.test(s, c)
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        self.assertIn('owner:alex', h.calls[1][2]['params']['query'])
        got = {r['Subject']: r for r in rows(s, 'shortcut')}
        self.assertTrue(trusted(s, got['sc-1 Story 1'])); self.assertFalse(trusted(s, got['sc-2 Story 2']))


class WrikeTests(unittest.TestCase):
    def test_active_tasks_and_external_authors(self):
        s = MemoryStore(); c = conn(s, 'wrike')
        tk = lambda i, a: {'id': f'T{i}', 'title': f'Task {i}', 'description': '<p>draft the memo</p>', 'status': 'Active', 'importance': 'High',
                           'permalink': f'https://www.wrike.com/open.htm?id={i}', 'updatedDate': '2026-08-20T10:00:00Z', 'authorIds': [a]}
        with wired({'/api/v4/contacts': {'data': [{'id': 'ME', 'firstName': 'Alex', 'lastName': 'Doyle'}]},
                    '/api/v4/tasks': {'data': [tk(1, 'IN'), tk(2, 'OUT')]},
                    '/api/v4/contacts/IN,OUT': {'data': [{'id': 'IN', 'type': 'Person', 'firstName': 'Gail', 'lastName': 'Moreno', 'profiles': [{'external': False}]},
                                                         {'id': 'OUT', 'type': 'Person', 'firstName': 'Vic', 'profiles': [{'external': True}]}]}}):
            self.assertIn('Alex Doyle', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        got = {r['FromName']: r for r in rows(s, 'wrike')}
        self.assertTrue(trusted(s, got['Gail Moreno'])); self.assertFalse(trusted(s, got['Vic']))


class SmartsheetTests(unittest.TestCase):
    def test_rows_naming_me_and_sheet_shares(self):
        s = MemoryStore(); c = conn(s, 'smartsheet', {'sheet_ids': '42'})
        cell = lambda col, v, **kw: {'columnId': col, 'value': v, 'displayValue': v, **kw}
        row = lambda i, who, by: {'id': i, 'rowNumber': i, 'modifiedAt': '2026-08-20T10:00:00Z', 'permalink': f'https://app.smartsheet.com/r/{i}',
                                  'createdBy': {'name': by, 'email': f'{by.lower()}@northwind.example'},
                                  'cells': [cell(1, f'Item {i}'), cell(2, who, objectValue={'objectType': 'CONTACT', 'email': who})]}
        with wired({'/users/me': {'id': 1, 'email': 'Alex@northwind.example'},
                    '/sheets/42/shares': {'data': [{'email': 'erin@northwind.example'}]},
                    '/sheets/42': {'name': 'Launch plan', 'permalink': 'https://app.smartsheet.com/sheets/42',
                                   'columns': [{'id': 1, 'title': 'Task', 'primary': True, 'type': 'TEXT_NUMBER'}, {'id': 2, 'title': 'Assigned To', 'type': 'CONTACT_LIST'}],
                                   'rows': [row(1, 'alex@northwind.example', 'Erin'), row(2, 'ray@northwind.example', 'Erin'), row(3, 'alex@northwind.example', 'Omar')]}}):
            inboxes.test(s, c)
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        got = {r['Subject']: r for r in rows(s, 'smartsheet')}
        self.assertEqual(set(got), {'Item 1', 'Item 3'})
        self.assertIn('Assigned To: alex@northwind.example', got['Item 1']['BodyText'])
        self.assertTrue(trusted(s, got['Item 1'])); self.assertFalse(trusted(s, got['Item 3']))


class AirtableTests(unittest.TestCase):
    def test_rows_of_a_view_carry_no_author_until_the_table_is_trusted(self):
        s = MemoryStore(); c = conn(s, 'airtable', {'base_id': 'appNW1', 'table': 'tblTasks', 'view': 'Mine'})
        with wired({'/meta/whoami': {'id': 'usr1', 'email': 'alex@northwind.example'},
                    '/appNW1/tblTasks': {'records': [{'id': 'rec1', 'createdTime': '2026-08-20T10:00:00.000Z',
                                                      'fields': {'Name': 'Order labels', 'Status': 'Todo', 'Points': 3}}]}}) as h:
            self.assertIn("'Mine'", inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 1)
        self.assertIn('IS_AFTER(LAST_MODIFIED_TIME()', h.calls[-1][2]['params']['filterByFormula'])
        r = rows(s, 'airtable')[0]
        self.assertEqual((r['Subject'], r['SourceLink']), ('Order labels', 'https://airtable.com/appNW1/tblTasks/rec1'))
        self.assertNotIn('author', meta(r)); self.assertFalse(trusted(s, r))
        s.remember_trust('airtable', senders._place({'SourceName': r['SourceName']}), 'you trust this source')
        self.assertTrue(trusted(s, r))


class GithubProjectsTests(unittest.TestCase):
    def test_assigned_items_skip_watched_repos_and_read_association(self):
        s = MemoryStore(); c = conn(s, 'github_projects')
        s.save_source({'Channel': 'github', 'Address': 'northwind/ledger', 'Active': 1}, 't')
        a = lambda *who: {'nodes': [{'login': w} for w in who]}
        node = lambda i, content: {'id': f'PVTI_{i}', 'updatedAt': '2026-08-20T10:00:00Z', 'content': content}
        iss = lambda n, repo, assoc, who='alex': {'__typename': 'Issue', 'number': n, 'title': f'I{n}', 'url': f'https://github.com/{repo}/issues/{n}', 'body': 'b',
                                                   'state': 'OPEN', 'authorAssociation': assoc, 'author': {'login': 'ray'}, 'assignees': a(who),
                                                   'repository': {'nameWithOwner': repo}}
        board = {'title': 'Roadmap', 'url': 'https://github.com/users/alex/projects/1', 'items': {'nodes': [
            node(1, iss(1, 'northwind/portal', 'MEMBER')), node(2, iss(2, 'northwind/portal', 'NONE')),
            node(3, iss(3, 'northwind/ledger', 'MEMBER')), node(4, iss(4, 'northwind/portal', 'MEMBER', who='ray')),
            node(5, {'__typename': 'DraftIssue', 'title': 'Draft idea', 'body': 'x', 'creator': {'login': 'erin'}, 'assignees': a('alex')})]}}
        with wired({'api.github.com/graphql': R({'data': {'viewer': {'login': 'alex', 'projectsV2': {'totalCount': 1, 'nodes': [board]}}}})}):
            inboxes.test(s, c)
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 3)
        got = {r['Subject']: r for r in rows(s, 'github_projects')}
        self.assertEqual(set(got), {'northwind/portal#1 I1', 'northwind/portal#2 I2', 'Draft idea'})
        self.assertTrue(trusted(s, got['northwind/portal#1 I1'])); self.assertFalse(trusted(s, got['northwind/portal#2 I2']))
        self.assertTrue(trusted(s, got['Draft idea']))


class BitbucketTests(unittest.TestCase):
    def test_review_requests_issues_and_workspace_members(self):
        s = MemoryStore(); c = conn(s, 'bitbucket', {'workspace': 'northwind', 'username': 'alex', 'repos': 'ledger'})
        pr = {'id': 7, 'title': 'Fix rounding', 'description': 'cents', 'updated_on': '2026-08-20T10:00:00+00:00', 'state': 'OPEN',
              'author': {'uuid': '{in}', 'display_name': 'Marcus Reed'}, 'links': {'html': {'href': 'https://bitbucket.org/northwind/ledger/pull-requests/7'}}}
        issue = {'id': 3, 'title': 'Export fails', 'content': {'raw': 'csv'}, 'updated_on': '2026-08-20T11:00:00+00:00', 'state': 'open',
                 'reporter': {'uuid': '{out}', 'display_name': 'Vic Outside'}, 'links': {'html': {'href': 'https://bitbucket.org/northwind/ledger/issues/3'}}}
        with wired({'/2.0/user': {'uuid': '{me}', 'display_name': 'Alex Doyle'}, '/2.0/workspaces/northwind': {'name': 'Northwind'},
                    '/ledger/pullrequests': {'values': [pr]}, '/ledger/issues': {'values': [issue]},
                    '/workspaces/northwind/members/%7Bin%7D': {'user': {}}, '/workspaces/northwind/members/%7Bout%7D': R({}, 404)}) as h:
            self.assertIn('Northwind', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)
        self.assertIn('reviewers.uuid="{me}"', next(k['params']['q'] for _, u, k in h.calls if 'pullrequests' in u))
        got = {r['FromName']: r for r in rows(s, 'bitbucket')}
        self.assertEqual(got['Marcus Reed']['Subject'], 'ledger!7 Fix rounding')
        self.assertTrue(trusted(s, got['Marcus Reed'])); self.assertFalse(trusted(s, got['Vic Outside']))

    def test_a_repo_without_issues_is_not_an_error(self):
        s = MemoryStore(); c = conn(s, 'bitbucket', {'workspace': 'northwind', 'username': 'a', 'repos': 'portal', 'me_id': '{me}'})
        with wired({'/portal/pullrequests': {'values': []}, '/portal/issues': R({}, 404)}):
            self.assertEqual(inboxes.poll(s, c, SINCE), 0)


class PlannerTests(unittest.TestCase):
    def test_open_tasks_through_a_company_app_and_guests(self):
        s = MemoryStore(); c = conn(s, 'ms_planner', {'user': 'alex@northwind.example'})
        tk = lambda i, by, pct=0: {'id': f'pt{i}', 'planId': 'P1', 'title': f'Plan task {i}', 'percentComplete': pct, 'hasDescription': i == 1,
                                   'createdDateTime': f'2026-08-2{i}T10:00:00Z', 'dueDateTime': '2026-09-01T00:00:00Z',
                                   'createdBy': {'user': {'id': by, 'displayName': by.title()}}}
        app = ({'tenant_id': 't1', 'client_id': 'c1'}, 'sec', True)
        with mock.patch('taskuary.channels.graph_creds', return_value=app), mock.patch('taskuary.channels.graph_token', return_value='T'), \
                wired({'/users/alex@northwind.example/planner/tasks': {'value': [tk(1, 'gail'), tk(2, 'guest'), tk(3, 'gail', 100)]},
                       '/planner/plans/P1': {'title': 'Q3 Launch'}, '/planner/tasks/pt1/details': {'description': 'book the venue'},
                       '/users/gail': {'userType': 'Member'}, '/users/guest': {'userType': 'Guest'}}):
            self.assertIn('Planner read OK', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, c, SINCE), 2)
        got = {r['FromName']: r for r in rows(s, 'ms_planner')}
        self.assertIn('book the venue', got['Gail']['BodyText']); self.assertIn('Q3 Launch', got['Gail']['BodyText'])
        self.assertTrue(trusted(s, got['Gail'])); self.assertFalse(trusted(s, got['Guest']))

    def test_a_company_app_must_name_whose_plans(self):
        s = MemoryStore(); c = conn(s, 'ms_planner')
        with mock.patch('taskuary.channels.graph_creds', return_value=({'client_id': 'c'}, 's', True)):
            with self.assertRaisesRegex(RuntimeError, 'enter whose'): inboxes.test(s, c)

    def test_the_outlook_sign_in_is_asked_for_tasks_not_chats(self):
        from taskuary import channels, msauth
        s = MemoryStore()
        o = s.get_connector_by_type('outlook')
        s.save_connector({'ConnectorId': o['ConnectorId'], 'Secret': 'rt', 'Active': 1, 'ConfigJson': json.dumps({'auth': 'user', 'client_id': 'c'})}, 't')
        cfg, sec, borrowed = channels.graph_creds(s, conn(s, 'ms_planner') | {'Secret': None})
        self.assertEqual((cfg['_scope'], cfg['_for'], sec, borrowed), (msauth.PLANNER, 'ms_planner', 'rt', True))


class ZulipTests(unittest.TestCase):
    def test_mentions_and_dms_with_the_organizations_roles(self):
        s = MemoryStore(); c = conn(s, 'zulip', {'site': 'northwind.zulipchat.com', 'email': 'alex@northwind.example'})
        msg = lambda i, who, kind='stream': {'id': i, 'sender_id': who, 'sender_full_name': f'U{who}', 'sender_email': f'u{who}@northwind.example',
                                             'content': f'@**Alex Doyle** can you look {i}', 'timestamp': 1787300000, 'type': kind,
                                             'display_recipient': 'ops', 'subject': 'deploy', 'stream_id': 5}
        with wired({'/users/me': {'user_id': 1, 'full_name': 'Alex Doyle'},
                    '/messages': {'messages': [msg(10, 2), msg(11, 3, 'private'), msg(12, 1)]},
                    '/users/2': {'user': {'role': 400}}, '/users/3': {'user': {'role': 600}}}):
            inboxes.test(s, c)
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 2)          # its own line is not work; the second narrow repeats them
        got = {r['FromName']: r for r in rows(s, 'zulip')}
        self.assertEqual(got['U2']['ConversationId'], 'zulip:5:deploy'); self.assertIn('/channel/5/topic/deploy/near/10', got['U2']['SourceLink'])
        self.assertTrue(trusted(s, got['U2'])); self.assertFalse(trusted(s, got['U3']))     # a guest


class SignalTests(unittest.TestCase):
    def test_a_drained_queue_files_every_message_however_old(self):
        s = MemoryStore(); c = conn(s, 'signal', {'number': '+1 555 0100'})
        env = lambda ts, text, g=None: {'envelope': {'source': '+15550111', 'sourceNumber': '+15550111', 'sourceUuid': 'uuid-1', 'sourceName': 'Ray Colton',
                                                     'timestamp': ts, 'dataMessage': {'timestamp': ts, 'message': text, **({'groupInfo': {'groupId': g}} if g else {})}}}
        with wired({'/v1/about': {'version': '0.92'}, '/v1/accounts': ['+15550100'],
                    '/v1/receive/%2B15550100': [env(1000000000000, 'old but never seen'), env(1787300000000, None), env(1787300001000, 'in the group', 'G1')]}):
            self.assertIn('+15550100', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, c, SINCE), 2)
        got = [r for r in rows(s, 'signal')]
        self.assertEqual({r['ConversationId'] for r in got}, {'signal:dm:uuid-1', 'signal:g:G1'})
        self.assertFalse(trusted(s, got[0]))

    def test_an_unlinked_number_is_said(self):
        s = MemoryStore(); c = conn(s, 'signal', {'number': '+15550100'})
        with wired({'/v1/about': {}, '/v1/accounts': []}), self.assertRaisesRegex(RuntimeError, 'not registered or linked'): inboxes.test(s, c)


class TwilioTests(unittest.TestCase):
    def test_inbound_texts_thread_by_sender(self):
        sid = 'AC' + 'a' * 32
        s = MemoryStore(); c = conn(s, 'twilio', {'account_sid': sid, 'number': '+15550100'})
        m = lambda i, d='inbound': {'sid': f'SM{i}', 'from': '+15550199', 'to': '+15550100', 'body': f'text {i}', 'direction': d,
                                    'date_sent': 'Thu, 20 Aug 2026 10:00:00 +0000'}
        with wired({f'/Accounts/{sid}.json': {'friendly_name': 'Northwind'}, '/Messages.json': {'messages': [m(1), m(2), m(3, 'outbound-api')]}}) as h:
            inboxes.test(s, c)
            self.assertEqual(inboxes.poll(s, c, SINCE), 2)
        self.assertEqual(h.calls[-1][2]['params']['To'], '+15550100')
        self.assertEqual({r['ConversationId'] for r in rows(s, 'twilio')}, {'twilio:from:+15550199'})


class DiscourseTests(unittest.TestCase):
    def test_notifications_to_me_and_only_staff_are_colleagues(self):
        s = MemoryStore(); c = conn(s, 'discourse', {'base_url': 'https://forum.northwind.example', 'username': 'alex'})
        n = lambda i, kind, who: {'id': i, 'notification_type': kind, 'created_at': '2026-08-20T10:00:00.000Z', 'topic_id': 70 + i, 'post_number': 2,
                                  'slug': 'pump-noise', 'fancy_title': 'Pump noise', 'data': {'original_username': who, 'topic_title': 'Pump noise'}}
        with wired({'/u/alex.json': {'user': {'username': 'alex'}}, '/notifications.json': {'notifications': [n(1, 1, 'erin'), n(2, 2, 'visitor'), n(3, 5, 'x')]},
                    '/posts/by_number/71/2.json': {'raw': 'what do you think @alex', 'name': 'Erin Blake'},
                    '/posts/by_number/72/2.json': {'raw': 'reply', 'name': 'A Visitor'},
                    '/u/erin.json': {'user': {'moderator': True}}, '/u/visitor.json': {'user': {'groups': [{'name': 'trust_level_1'}]}}}):
            inboxes.test(s, c)
            self.assertEqual(inboxes.poll(s, c, SINCE), 2)                     # a like (type 5) is not work
        got = {r['FromName']: r for r in rows(s, 'discourse')}
        self.assertEqual(got['Erin Blake']['SourceLink'], 'https://forum.northwind.example/t/pump-noise/71/2')
        self.assertTrue(trusted(s, got['Erin Blake'])); self.assertFalse(trusted(s, got['A Visitor']))


class RedditTests(unittest.TestCase):
    def test_the_inbox_through_a_script_app_is_always_strangers(self):
        s = MemoryStore(); c = conn(s, 'reddit', {'client_id': 'cid', 'client_secret': 'cs', 'username': 'alexd'})
        kid = lambda i: {'kind': 't1', 'data': {'id': f'c{i}', 'name': f't1_c{i}', 'author': 'someone', 'body': 'is this still for sale?', 'was_comment': True,
                                                'subreddit': 'woodworking', 'link_title': 'My bench', 'created_utc': 1787300000.0, 'context': f'/r/woodworking/comments/x/y/c{i}/?context=3'}}
        with mock.patch('taskuary.net.token', side_effect=lambda key, mint: mint()[0]), \
                wired({'reddit.com/api/v1/access_token': {'access_token': 'T', 'expires_in': 3600},
                       '/api/v1/me': {'name': 'alexd'}, '/message/inbox': {'data': {'children': [kid(1)]}}}):
            self.assertIn('u/alexd', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, c, SINCE), 1)
        r = rows(s, 'reddit')[0]
        self.assertEqual(r['SourceLink'], 'https://www.reddit.com/r/woodworking/comments/x/y/c1/?context=3'); self.assertFalse(trusted(s, r))
        from taskuary import guard
        self.assertIn('client_secret', guard.WRITE_ONLY_CONFIG['reddit'])


class YouTubeTests(unittest.TestCase):
    def test_comments_on_my_videos_without_my_own(self):
        me = 'UC' + 'x' * 22
        s = MemoryStore(); c = conn(s, 'youtube', {'channel_id': me})
        th = lambda i, who: {'id': f'Ug{i}', 'snippet': {'videoId': 'vid1', 'topLevelComment': {'snippet': {
            'authorDisplayName': f'@viewer{i}', 'authorChannelId': {'value': who}, 'textOriginal': 'great video, what lens?',
            'publishedAt': '2026-08-20T10:00:00Z', 'updatedAt': '2026-08-20T10:00:00Z'}}}}
        with wired({'/channels': {'items': [{'snippet': {'title': 'Northwind Builds'}}]}, '/commentThreads': {'items': [th(1, 'UCother'), th(2, me)]}}) as h:
            self.assertIn('Northwind Builds', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, c, SINCE), 1)
        self.assertEqual(h.calls[-1][2]['params']['allThreadsRelatedToChannelId'], me)
        r = rows(s, 'youtube')[0]
        self.assertEqual(r['SourceLink'], 'https://www.youtube.com/watch?v=vid1&lc=Ug1'); self.assertFalse(trusted(s, r))


class CommerceTests(unittest.TestCase):
    """Bookings, orders and disputes: nobody inside wrote them, so they wait until the source is trusted."""
    def test_calendly_new_bookings(self):
        s = MemoryStore(); c = conn(s, 'calendly')
        ev = lambda i, made: {'uri': f'https://api.calendly.com/scheduled_events/E{i}', 'name': 'Intro call', 'created_at': made,
                              'start_time': '2026-09-02T15:00:00Z', 'end_time': '2026-09-02T15:30:00Z', 'location': {'join_url': 'https://zoom.example/j/1'}}
        with wired({'/users/me': {'resource': {'uri': 'https://api.calendly.com/users/ME', 'name': 'Alex Doyle'}},
                    '/scheduled_events/E1/invitees': {'collection': [{'name': 'Paula Vance', 'email': 'paula@vendor.example',
                                                                     'questions_and_answers': [{'question': 'Topic?', 'answer': 'pricing'}]}]},
                    '/scheduled_events': {'collection': [ev(1, '2026-08-20T10:00:00Z'), ev(2, '2026-07-01T10:00:00Z')]}}):
            inboxes.test(s, c)
            self.assertEqual(inboxes.poll(s, again(s, c), SINCE), 1)
        r = rows(s, 'calendly')[0]
        self.assertEqual(r['Subject'], 'Intro call with Paula Vance'); self.assertIn('Topic?: pricing', r['BodyText']); self.assertFalse(trusted(s, r))

    def test_shipstation_orders_awaiting_shipment(self):
        s = MemoryStore(); c = conn(s, 'shipstation', {'api_key': 'k'})
        o = {'orderId': 99, 'orderNumber': 'NW-1001', 'shipByDate': '2026-08-22T00:00:00.0000000', 'customerEmail': 'buyer@vendor.example',
             'billTo': {'name': 'Pat Buyer'}, 'items': [{'name': 'Oak shelf', 'quantity': 2}], 'customerNotes': 'gift wrap', 'orderTotal': 120.0}
        with wired({'/stores': [{'storeId': 1}], '/orders': {'orders': [o]}}):
            self.assertIn('1 store', inboxes.test(s, c))
            self.assertEqual(inboxes.poll(s, c, SINCE), 1)
        r = rows(s, 'shipstation')[0]
        self.assertIn('2 × Oak shelf', r['BodyText']); self.assertIn('ship by 2026-08-22', r['BodyText'])

    def test_shopify_unfulfilled_orders(self):
        s = MemoryStore(); c = conn(s, 'shopify', {'shop': 'northwind'})
        o = {'id': 450, 'name': '#1001', 'email': 'buyer@vendor.example', 'updated_at': '2026-08-20T10:00:00-04:00', 'financial_status': 'paid',
             'total_price': '40.00', 'currency': 'USD', 'customer': {'first_name': 'Pat', 'last_name': 'Buyer'},
             'line_items': [{'title': 'Mug', 'quantity': 1}], 'note': 'ship Monday'}
        with wired({'/admin/api/2024-10/shop.json': {'shop': {'name': 'Northwind Goods'}}, '/admin/api/2024-10/orders.json': {'orders': [o]}}) as h:
            inboxes.test(s, c)
            self.assertEqual(inboxes.poll(s, c, SINCE), 1)
        self.assertEqual(h.calls[-1][2]['params']['fulfillment_status'], 'unfulfilled')
        r = rows(s, 'shopify')[0]
        self.assertEqual((r['FromName'], r['SourceLink']), ('Pat Buyer', 'https://northwind.myshopify.com/admin/orders/450'))

    def test_square_and_paypal_disputes(self):
        s = MemoryStore(); sq, pp = conn(s, 'square'), conn(s, 'paypal', {'client_id': 'cid'})
        with wired({'/merchants/me': {'merchant': {'business_name': 'Northwind'}},
                    '/v2/disputes': {'disputes': [{'id': 'D1', 'amount_money': {'amount': 2500, 'currency': 'USD'}, 'reason': 'NOT_AS_DESCRIBED',
                                                   'state': 'EVIDENCE_REQUIRED', 'due_at': '2026-08-30T00:00:00Z', 'card_brand': 'VISA',
                                                   'updated_at': '2026-08-20T10:00:00Z'}]}}):
            inboxes.test(s, sq); self.assertEqual(inboxes.poll(s, sq, SINCE), 1)
        self.assertEqual(rows(s, 'square')[0]['Subject'], 'Dispute: 25.0 USD - not as described')
        with mock.patch('taskuary.net.token', side_effect=lambda key, mint: mint()[0]), \
                wired({'/v1/oauth2/token': {'access_token': 'T', 'expires_in': 3600},
                       '/v1/customer/disputes': {'items': [{'dispute_id': 'PP-D-1', 'reason': 'MERCHANDISE_OR_SERVICE_NOT_RECEIVED', 'status': 'WAITING_FOR_SELLER_RESPONSE',
                                                            'dispute_amount': {'value': '19.99', 'currency_code': 'USD'}, 'dispute_life_cycle_stage': 'INQUIRY',
                                                            'update_time': '2026-08-20T10:00:00.000Z'}]}}) as h:
            inboxes.test(s, pp); self.assertEqual(inboxes.poll(s, pp, SINCE), 1)
        self.assertIn('api-m.paypal.com', h.calls[0][1])
        r = rows(s, 'paypal')[0]
        self.assertEqual(r['SourceLink'], 'https://www.paypal.com/resolutioncenter/PP-D-1'); self.assertFalse(trusted(s, r))


class MailPresetTests(unittest.TestCase):
    """Fastmail, Yahoo, Proton Mail Bridge and Exchange are IMAP cards with their servers filled in - no protocol of their own."""
    def presets(self):
        import pathlib
        cat = json.loads((pathlib.Path(__file__).resolve().parents[1] / 'taskuary' / 'connectorcatalog.json').read_text(encoding='utf-8'))
        return {c['type']: c for c in cat['cards'] if c.get('preset')}

    def test_each_is_a_working_imap_card(self):
        p = self.presets()
        self.assertEqual(set(p), {'fastmail', 'yahoo_mail', 'proton_mail', 'exchange'})
        for t, c in p.items():
            self.assertFalse(c['planned'], t); self.assertEqual(c['preset']['type'], 'imap', t); self.assertTrue(c['preset']['howto'], t)
        self.assertEqual(p['fastmail']['preset']['config']['imap_host'], 'imap.fastmail.com')
        self.assertEqual(p['yahoo_mail']['preset']['config']['smtp_host'], 'smtp.mail.yahoo.com')

    def test_the_bridge_is_reached_with_starttls_and_the_card_password(self):
        from taskuary import imapmail
        cfg = {**self.presets()['proton_mail']['preset']['config'], 'address': 'alex@northwind.example'}
        M = mock.MagicMock()
        with mock.patch.object(imapmail.imaplib, 'IMAP4', return_value=M) as plain, mock.patch.object(imapmail.imaplib, 'IMAP4_SSL') as ssl_:
            got, user = imapmail._login({'Type': 'imap', 'ConfigJson': json.dumps(cfg), 'Secret': 'bridge-pw'})
        plain.assert_called_once_with('127.0.0.1', 1143, timeout=30); M.starttls.assert_called_once(); ssl_.assert_not_called()
        M.login.assert_called_once_with('alex@northwind.example', 'bridge-pw')
        self.assertEqual(imapmail._hosts({'Type': 'imap', 'ConfigJson': json.dumps(cfg)})[1], '127.0.0.1')

    def test_a_993_mailbox_still_speaks_ssl(self):
        from taskuary import imapmail
        with mock.patch.object(imapmail.imaplib, 'IMAP4') as plain, mock.patch.object(imapmail.imaplib, 'IMAP4_SSL') as ssl_:
            imapmail._login({'Type': 'imap', 'Secret': 'pw', 'ConfigJson': json.dumps({'imap_host': 'imap.fastmail.com', 'address': 'a@northwind.example'})})
        ssl_.assert_called_once(); plain.assert_not_called()


class OneRoadTests(unittest.TestCase):
    def test_every_source_is_wired_everywhere_a_tracker_is(self):
        from taskuary import channels, outbound, search, store
        for t in inboxes.TYPES:
            self.assertIn(t, channels.PER_CONNECTOR); self.assertEqual(channels.CH2SRC[t], t)
            self.assertIn(t, senders.TRACKERS); self.assertIn(t, outbound.NEVER); self.assertIn(t, search.TICKET)
            self.assertEqual(store.DEFAULT_ROLES[t], 'trigger')
        self.assertEqual({c['Type'] for c in MemoryStore().list_connectors()} & set(inboxes.TYPES), set(inboxes.TYPES))

    def test_a_poll_goes_through_the_card_test_and_poll_dispatch(self):
        from taskuary import channels
        s = MemoryStore(); c = conn(s, 'shortcut', {'me_id': 'm', 'mention': 'alex'})
        with wired({'/search/stories': {'data': []}, '/api/v3/members': []}):
            self.assertEqual(channels._poll_one(s, c, False, 0, None, False), 0)

    def test_a_revision_is_the_same_conversation(self):
        s = MemoryStore(); c = conn(s, 'shortcut', {'me_id': 'm', 'mention': 'alex'})
        st = lambda d: {'data': [{'id': 1, 'name': 'S', 'description': d, 'updated_at': '2026-08-20T10:00:00Z', 'requested_by_id': 'x'}]}
        with wired({'/search/stories': st('one'), '/api/v3/members': [{'id': 'x', 'profile': {'name': 'Erin Blake'}}]}):
            self.assertEqual(inboxes.poll(s, c, SINCE), 1); self.assertEqual(inboxes.poll(s, c, SINCE), 0)
        with wired({'/search/stories': st('two'), '/api/v3/members': []}):
            self.assertEqual(inboxes.poll(s, c, SINCE), 1)
        self.assertEqual({r['ConversationId'] for r in rows(s, 'shortcut')}, {'shortcut:1'})


if __name__ == '__main__':
    unittest.main()
