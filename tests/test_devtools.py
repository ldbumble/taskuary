"""The developer-tool connectors (GitLab, Azure DevOps, Linear, Trello, Notion, Discord,
Sentry, PagerDuty) plus the Prometheus/Datadog report executors - HTTP faked by URL, no
network, so these run anywhere. Mirrors test_pm.py.
"""
import json, unittest
from datetime import datetime
from unittest import mock
import requests as real_requests

from taskuary import devtools
from taskuary.reports import REGISTRY, resolve_cfg
from taskuary.store import MemoryStore

SINCE = datetime(2026, 8, 1)


def conn(s, typ, cfg=None):
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1,
                      **({'ConfigJson': json.dumps(cfg)} if cfg else {})}, 't')
    return s.get_connector(cid, with_secret=True)


class R:
    def __init__(self, j, status=200): self._j, self.status_code, self.text = j, status, ''
    def json(self): return self._j
    def raise_for_status(self):
        if self.status_code >= 400: raise real_requests.HTTPError(str(self.status_code))


class FakeHTTP:
    """Route by URL substring - an unexpected call fails the test instead of the network."""
    RequestException = real_requests.RequestException
    HTTPError = real_requests.HTTPError
    def __init__(self, routes): self.routes, self.calls = routes, []
    def _find(self, url):
        self.calls.append(url)
        for k, v in self.routes.items():
            if k in url: return R(v)
        raise AssertionError(f'unexpected url: {url}')
    def get(self, url, **kw): return self._find(url)
    def post(self, url, **kw): return self._find(url)
    def request(self, method, url, **kw): return self._find(url)


def wired(routes):
    return mock.patch.object(devtools, 'requests', FakeHTTP(routes))


def feed_channels(s): return [r['Channel'] for r in s.feed()]


class GitLabTests(unittest.TestCase):
    ISSUE = {'id': 9, 'iid': 4, 'title': 'Importer chokes on BOM', 'state': 'opened',
             'description': 'crash log attached', 'updated_at': '2026-08-20T10:00:00Z',
             'web_url': 'https://gitlab.com/acme/importer/-/issues/4', 'author': {'name': 'Rina'}}
    def test_test_and_poll(self):
        s = MemoryStore(); c = conn(s, 'gitlab')
        with wired({'/api/v4/user': {'name': 'Uri', 'username': 'uri'},
                    '/api/v4/issues': [self.ISSUE], '/api/v4/merge_requests': []}):
            self.assertIn('Uri', devtools.test(s, c))
            self.assertEqual(devtools.poll(s, c, SINCE), 1)
        self.assertIn('gitlab', feed_channels(s))
        row = next(r for r in s.feed() if r['Channel'] == 'gitlab')
        self.assertIn('#4', row['Subject']); self.assertEqual(row['SourceName'], 'acme/importer')


class AzdoTests(unittest.TestCase):
    def test_test_and_poll(self):
        s = MemoryStore(); c = conn(s, 'azdo', {'org_url': 'https://dev.azure.com/northwind'})
        wi = {'id': 88, 'fields': {'System.Title': 'Fix PTO rounding', 'System.State': 'Active',
                                   'System.WorkItemType': 'Bug', 'System.TeamProject': 'Census',
                                   'System.Description': 'cents off', 'System.ChangedDate': '2026-08-21T09:00:00Z',
                                   'System.CreatedBy': {'displayName': 'Chana'}}}
        with wired({'/_apis/projects': {'count': 3}, '/_apis/wit/wiql': {'workItems': [{'id': 88}]},
                    '/_apis/wit/workitems?ids=88': {'value': [wi]}}):
            self.assertIn('3 project', devtools.test(s, c))
            self.assertEqual(devtools.poll(s, c, SINCE), 1)
        row = next(r for r in s.feed() if r['Channel'] == 'azdo')
        self.assertIn('#88', row['Subject']); self.assertIn('Census', row['SourceName'])

    def test_no_org_is_loud(self):
        s = MemoryStore(); c = conn(s, 'azdo')
        with self.assertRaises(RuntimeError): devtools.test(s, c)


class LinearTests(unittest.TestCase):
    def test_test_and_poll(self):
        s = MemoryStore(); c = conn(s, 'linear')
        node = {'identifier': 'ENG-42', 'title': 'Rotate the API keys', 'description': None,
                'url': 'https://linear.app/acme/issue/ENG-42', 'updatedAt': '2026-08-19T08:00:00Z',
                'state': {'name': 'Todo'}, 'creator': {'name': 'Dana'}, 'project': {'name': 'Security'}}
        with wired({'graphql': {'data': {'viewer': {'name': 'Uri', 'email': 'u@x'},
                                         'issues': {'nodes': [node]}}}}):
            self.assertIn('Uri', devtools.test(s, c))
            self.assertEqual(devtools.poll(s, c, SINCE), 1)
        row = next(r for r in s.feed() if r['Channel'] == 'linear')
        self.assertIn('ENG-42', row['Subject']); self.assertEqual(row['SourceName'], 'Security')


class TrelloTests(unittest.TestCase):
    def test_needs_both_halves(self):
        s = MemoryStore(); c = conn(s, 'trello')     # token saved, no api_key
        with self.assertRaises(RuntimeError): devtools.test(s, c)

    def test_poll(self):
        s = MemoryStore(); c = conn(s, 'trello', {'api_key': 'k'})
        card = {'id': 'abc', 'name': 'Renew SSL cert', 'desc': 'expires 9/1',
                'dateLastActivity': '2026-08-18T12:00:00Z', 'url': 'https://trello.com/c/abc',
                'idBoard': 'b1', 'board': {'name': 'Ops'}}
        with wired({'/members/me/cards': [card], '/members/me': {'fullName': 'Uri'}}):
            self.assertEqual(devtools.poll(s, c, SINCE), 1)
        row = next(r for r in s.feed() if r['Channel'] == 'trello')
        self.assertEqual((row['Subject'], row['SourceName']), ('Renew SSL cert', 'Ops'))


class NotionTests(unittest.TestCase):
    def test_test_and_poll(self):
        s = MemoryStore(); c = conn(s, 'notion')
        page = {'id': 'p1', 'url': 'https://notion.so/p1', 'last_edited_time': '2026-08-22T07:00:00Z',
                'properties': {'Name': {'type': 'title', 'title': [{'plain_text': 'Onboarding runbook'}]}}}
        with wired({'/users/me': {'name': 'Taskuary bot'}, '/search': {'results': [page]}}):
            self.assertIn('Taskuary bot', devtools.test(s, c))
            self.assertEqual(devtools.poll(s, c, SINCE), 1)
        row = next(r for r in s.feed() if r['Channel'] == 'notion')
        self.assertEqual(row['Subject'], 'Onboarding runbook')


class DiscordTests(unittest.TestCase):
    def test_poll_is_per_source_and_skips_bots(self):
        s = MemoryStore(); c = conn(s, 'discord')
        src = {'Address': '555'}
        msgs = [{'id': '2', 'content': 'deploy is red', 'timestamp': '2026-08-21T10:00:00Z',
                 'author': {'username': 'lea', 'global_name': 'Lea'}},
                {'id': '1', 'content': 'nightly ok', 'timestamp': '2026-08-21T09:00:00Z',
                 'author': {'username': 'ci-bot', 'bot': True}}]
        with wired({'/channels/555/messages': msgs, '/users/@me': {'username': 'taskuary'}}):
            self.assertIn('taskuary', devtools.test(s, c))
            self.assertEqual(devtools.poll_discord(s, c, src, SINCE), 1)
        row = next(r for r in s.feed() if r['Channel'] == 'discord')
        self.assertEqual((row['FromName'], row['SourceName']), ('Lea', '555'))

    def test_send(self):
        s = MemoryStore(); conn(s, 'discord')
        with wired({'/channels/555/messages': {'id': 'm9'}}):
            out = devtools.discord_send(s, '555', 'on it')
        self.assertEqual(out, {'channel': 'discord', 'chat': '555'})


class SentryTests(unittest.TestCase):
    def test_test_and_poll(self):
        s = MemoryStore(); c = conn(s, 'sentry', {'org': 'northwind'})
        issue = {'id': '77', 'shortId': 'WEBAPP-3F', 'title': 'KeyError: employee_id',
                 'culprit': 'imports/pto.py', 'count': '41', 'userCount': 3, 'level': 'error',
                 'permalink': 'https://sentry.io/x/77', 'lastSeen': '2026-08-22T05:00:00Z',
                 'project': {'slug': 'census'}}
        with wired({'/api/0/organizations/northwind/issues': [issue],
                    '/api/0/organizations/northwind/': {'slug': 'northwind', 'name': 'Northwind'}}):
            self.assertIn('Northwind', devtools.test(s, c))
            self.assertEqual(devtools.poll(s, c, SINCE), 1)
        row = next(r for r in s.feed() if r['Channel'] == 'sentry')
        self.assertIn('WEBAPP-3F', row['Subject']); self.assertIn('41x', row.get('Preview') or '')


class PagerDutyTests(unittest.TestCase):
    def test_test_and_poll(self):
        s = MemoryStore(); c = conn(s, 'pagerduty')
        inc = {'id': 'P1', 'incident_number': 12, 'title': 'AZWEB01 down', 'status': 'triggered',
               'urgency': 'high', 'created_at': '2026-08-23T03:00:00Z',
               'html_url': 'https://northwind.pagerduty.com/incidents/P1',
               'service': {'summary': 'Web tier'}, 'summary': 'host unreachable'}
        with wired({'/incidents': {'incidents': [inc]}}):
            self.assertIn('authenticated', devtools.test(s, c))
            self.assertEqual(devtools.poll(s, c, SINCE), 1)
        row = next(r for r in s.feed() if r['Channel'] == 'pagerduty')
        self.assertIn('#12', row['Subject']); self.assertEqual(row['SourceName'], 'Web tier')


class ReportExecutorTests(unittest.TestCase):
    def test_prometheus_rows(self):
        j = {'status': 'success', 'data': {'result': [
            {'metric': {'job': 'web', 'instance': 'azweb01'}, 'value': [1755900000, '0']}]}}
        with mock.patch('requests.get', return_value=R(j)):
            head, body = REGISTRY['prometheus']({'base_url': 'http://prom:9090', 'query': 'up == 0'})
        self.assertEqual(head, '1 series'); self.assertIn('azweb01', body)

    def test_prometheus_needs_base_url(self):
        with self.assertRaises(RuntimeError): REGISTRY['prometheus']({'query': 'up'})

    def test_datadog_trouble_first(self):
        mons = [{'name': 'disk ok', 'overall_state': 'OK', 'type': 'metric alert', 'options': {}},
                {'name': 'api errors', 'overall_state': 'Alert', 'type': 'metric alert', 'options': {}}]
        with mock.patch('requests.get', return_value=R(mons)):
            head, body = REGISTRY['datadog']({'api_key': 'k', 'app_key': 'a'})
        self.assertEqual(head, '2 monitors')
        self.assertLess(body.index('api errors'), body.index('disk ok'))

    def test_cards_resolve_creds(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('datadog')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'APIKEY', 'Active': 1,
                          'ConfigJson': json.dumps({'site': 'datadoghq.eu', 'app_key': 'APP'})}, 't')
        got = resolve_cfg(s, {'type': 'datadog'})
        self.assertEqual((got['api_key'], got['app_key'], got['site']), ('APIKEY', 'APP', 'datadoghq.eu'))
        for t in ('gitlab', 'azdo', 'linear', 'trello', 'notion', 'discord', 'sentry', 'pagerduty',
                  'prometheus', 'datadog'):
            self.assertTrue(s.get_connector_by_type(t)['Roles'])   # seeded with a default role


if __name__ == '__main__':
    unittest.main()
