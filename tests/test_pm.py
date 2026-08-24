"""Telegram chat approval, per-source agent prompts, and the PM connectors
(Jira/Asana/Monday/ClickUp/Todoist)."""
import json, unittest
from datetime import datetime, timedelta

from taskuary import messengers, pm
from taskuary.ingest import source_rules, PR_RULES, ISSUE_RULES
from taskuary.store import MemoryStore


def conn(s, typ, cfg=None):
    """The seeded connector row of this type, armed with a token (Type is UNIQUE - update it)."""
    cid = s.get_connector_by_type(typ)['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'tok', 'Active': 1,
                      **({'ConfigJson': json.dumps(cfg)} if cfg else {})}, 't')
    return s.get_connector(cid, with_secret=True)


class TelegramApprovalTests(unittest.TestCase):
    def fake_tg(self, updates):
        def _tg(tok, method, **kw):
            if method == 'getUpdates': return updates
            return {}
        return _tg

    def test_unknown_chat_registers_off_and_never_ingests(self):
        s = MemoryStore()
        c = conn(s, "telegram")
        real, messengers.tg = messengers.tg, self.fake_tg([{'update_id': 7, 'message': {
            'message_id': 1, 'date': 1755900000, 'text': 'buy my crypto course',
            'chat': {'id': 555, 'title': None}, 'from': {'first_name': 'Spam', 'last_name': 'Mer'}}}])
        try: n = messengers.poll_telegram(s, c, [])
        finally: messengers.tg = real
        self.assertEqual(n, 0)
        src = next(x for x in s.list_sources(active_only=False) if x['Channel'] == 'telegram')
        self.assertEqual((src['Address'], src['Active']), ('555', 0))
        self.assertIn('Spam Mer', src['Owner'])
        self.assertEqual(s.feed(), [])                       # not a message anywhere, not even filed

    def test_approved_chat_flows_in(self):
        s = MemoryStore()
        c = conn(s, "telegram")
        s.save_source({'Channel': 'telegram', 'Address': '555', 'ConnectorId': c['ConnectorId'], 'Active': 1}, 't')
        real, messengers.tg = messengers.tg, self.fake_tg([{'update_id': 8, 'message': {
            'message_id': 2, 'date': 1755900000, 'text': 'please fix the export',
            'chat': {'id': 555}, 'from': {'first_name': 'Uri'}}}])
        try: n = messengers.poll_telegram(s, c, [])
        finally: messengers.tg = real
        self.assertEqual(n, 1)
        self.assertEqual(len(s.feed()), 1)


class SourceRulesTests(unittest.TestCase):
    def msg(self, ch, body='', source=''):
        return {'Channel': ch, 'BodyText': body, 'SourceName': source}

    def test_github_pr_and_issue_defaults(self):
        s = MemoryStore()
        pr = self.msg('github', '[pull request by drive-by - association: NONE]\nAdds CSV import')
        self.assertEqual(source_rules(s, pr), PR_RULES)
        self.assertEqual(source_rules(s, self.msg('github', '[issue by someone - association: OWNER]\nIt broke')), ISSUE_RULES)

    def test_github_card_prompt_overrides(self):
        s = MemoryStore()
        c = s.get_connector_by_type('github')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'ConfigJson': json.dumps({'prompt_pr': 'house PR rules'})}, 't')
        self.assertEqual(source_rules(s, self.msg('github', '[pull request by x - association: NONE]')), 'house PR rules')

    def test_connector_task_prompt_and_email_silence(self):
        s = MemoryStore()
        c = s.get_connector_by_type('telegram')
        s.save_connector({'ConnectorId': c['ConnectorId'], 'ConfigJson': json.dumps({'task_prompt': 'chat asks are urgent'})}, 't')
        self.assertEqual(source_rules(s, self.msg('telegram')), 'chat asks are urgent')
        self.assertEqual(source_rules(s, self.msg('email')), '')          # the mail IS the prompt
        self.assertEqual(source_rules(s, self.msg('report')), '')




class PmPollTests(unittest.TestCase):
    def test_jira_assigned_issue_lands_once(self):
        s = MemoryStore()
        c = conn(s, 'jira', {'base_url': 'https://team.atlassian.net', 'email': 'me@x.com'})
        real, pm._jira_get = pm._jira_get, lambda c_, p, **kw: {'issues': [{'key': 'OPS-12', 'fields': {
            'summary': 'Fix the sync', 'description': 'it double-books', 'updated': '2026-08-23T09:00:00.000+0000',
            'status': {'name': 'To Do'}, 'priority': {'name': 'High'}, 'reporter': {'displayName': 'Rina'}}}]}
        try:
            n1 = pm.poll_jira(s, c, datetime.now() - timedelta(hours=1))
            n2 = pm.poll_jira(s, c, datetime.now() - timedelta(hours=1))
        finally: pm._jira_get = real
        self.assertEqual((n1, n2), (1, 0))                    # dedupe by issue key
        row = s.feed()[0]
        self.assertEqual(row['Channel'], 'jira')
        self.assertIn('OPS-12', row['Subject'])

    def test_asana_since_filter(self):
        s = MemoryStore()
        c = conn(s, 'asana', {'workspace_gid': '99'})
        rows = [{'gid': '1', 'name': 'Old one', 'notes': '', 'modified_at': '2026-08-20T08:00:00.000Z'},
                {'gid': '2', 'name': 'Fresh one', 'notes': 'do it', 'modified_at': '2099-01-01T08:00:00.000Z'}]
        real, pm._asana_get = pm._asana_get, lambda c_, p, **kw: rows
        try: n = pm.poll_asana(s, c, datetime.now())
        finally: pm._asana_get = real
        self.assertEqual(n, 1)
        self.assertIn('Fresh one', s.feed()[0]['Subject'])

    def test_monday_keeps_only_items_naming_me(self):
        s = MemoryStore()
        c = conn(s, 'monday', {'me_id': '42'})
        data = {'boards': [{'name': 'Ops', 'items_page': {'items': [
            {'id': '10', 'name': 'Mine', 'updated_at': '2099-01-01T00:00:00Z', 'url': 'u', 'creator': {'name': 'Boss'},
             'column_values': [{'type': 'people', 'text': 'Uri', 'persons_and_teams': [{'id': 42, 'kind': 'person'}]}]},
            {'id': '11', 'name': 'Not mine', 'updated_at': '2099-01-01T00:00:00Z', 'url': 'u', 'creator': None,
             'column_values': [{'type': 'people', 'text': 'Someone', 'persons_and_teams': [{'id': 7, 'kind': 'person'}]}]},
        ]}}]}
        real, pm._monday = pm._monday, lambda c_, q: data
        try: n = pm.poll_monday(s, c, datetime.now())
        finally: pm._monday = real
        self.assertEqual(n, 1)
        self.assertEqual(s.feed()[0]['Subject'], 'Mine')


class ClickUpTests(unittest.TestCase):
    TASK = {'id': '9hz', 'custom_id': 'ABC-1', 'name': 'Fix login', 'description': 'it 500s',
            'status': {'status': 'in progress'}, 'priority': {'priority': 'urgent'},
            'date_updated': '1756000000000', 'due_date': '1756100000000',
            'creator': {'username': 'Rina', 'email': 'rina@x.com'},
            'url': 'https://app.clickup.com/t/9hz', 'list': {'name': 'Sprint 4'}}

    def test_assigned_task_lands_once_and_carries_the_list(self):
        s = MemoryStore()
        c = conn(s, 'clickup', {'user_id': '183', 'team_id': '512'})
        real, pm._clickup = pm._clickup, lambda c_, p, **kw: {'tasks': [self.TASK]}
        try:
            n1 = pm.poll_clickup(s, c, datetime.now() - timedelta(hours=1))
            n2 = pm.poll_clickup(s, c, datetime.now() - timedelta(hours=1))
        finally: pm._clickup = real
        self.assertEqual((n1, n2), (1, 0))                    # dedupe by task id
        row = s.feed()[0]
        self.assertEqual((row['Channel'], row['SourceName']), ('clickup', 'Sprint 4'))
        self.assertEqual(row['Subject'], 'ABC-1 Fix login')
        self.assertIn('in progress', row['Preview'])
        self.assertIn('urgent', row['Preview'])

    def test_poll_refuses_before_test_has_learned_the_workspace(self):
        s = MemoryStore()
        with self.assertRaises(RuntimeError) as e:
            pm.poll_clickup(s, conn(s, 'clickup'), datetime.now())
        self.assertIn('run Test', str(e.exception))

    def test_test_remembers_who_me_is_and_which_workspace(self):
        s = MemoryStore()
        c = conn(s, 'clickup')
        routes = {'/user': {'user': {'id': 183, 'username': 'Uri', 'email': 'u@x.com'}},
                  '/team': {'teams': [{'id': '512', 'name': 'Acme'}]}}
        real, pm._clickup = pm._clickup, lambda c_, p, **kw: routes[p]
        try: detail = pm.test_clickup(s, c)
        finally: pm._clickup = real
        cfg = json.loads(s.get_connector_by_type('clickup')['ConfigJson'])
        self.assertEqual((cfg['user_id'], cfg['team_id']), ('183', '512'))
        self.assertIn('Uri', detail)
        self.assertTrue(any(x['Channel'] == 'clickup' for x in s.list_sources(active_only=False)))

    def test_token_goes_in_raw_without_bearer(self):
        """ClickUp is the one API here that rejects an Authorization: Bearer prefix."""
        seen = {}
        class R:
            status_code = 200
            def json(self): return {'user': {'id': 1}}
            def raise_for_status(self): pass
        class FakeReq:
            @staticmethod
            def get(url, params=None, timeout=None, headers=None):
                seen.update(headers or {}); return R()
        s = MemoryStore()
        real, pm.requests = pm.requests, FakeReq
        try: pm._clickup(conn(s, 'clickup'), '/user')
        finally: pm.requests = real
        self.assertEqual(seen['Authorization'], 'tok')

    def test_priority_survives_both_shapes(self):
        self.assertEqual(pm._cu_priority({'priority': 'high'}), 'high')
        self.assertEqual(pm._cu_priority(1), 'urgent')
        self.assertIsNone(pm._cu_priority(None))


class TodoistTests(unittest.TestCase):
    TASK = {'id': '6XG', 'content': 'Buy milk', 'description': 'organic', 'priority': 4,
            'due': {'date': '2026-08-24'}, 'updated_at': '2026-08-23T09:00:00Z'}

    def test_filtered_task_lands_once_with_a_built_url(self):
        s = MemoryStore()
        c = conn(s, 'todoist')
        real, pm._todoist = pm._todoist, lambda c_, p, **kw: {'results': [self.TASK]}
        try:
            n1 = pm.poll_todoist(s, c, datetime.now() - timedelta(hours=1))
            n2 = pm.poll_todoist(s, c, datetime.now() - timedelta(hours=1))
        finally: pm._todoist = real
        self.assertEqual((n1, n2), (1, 0))
        row = s.feed()[0]
        self.assertEqual((row['Channel'], row['Subject']), ('todoist', 'Buy milk'))
        # v1 dropped the task's url field - we build the deep link ourselves
        self.assertEqual(row['SourceLink'], 'https://app.todoist.com/app/task/6XG')
        self.assertIn('urgent', row['Preview'])
        self.assertIn('2026-08-24', row['Preview'])

    def test_owner_filter_overrides_the_default_query(self):
        s = MemoryStore()
        c = conn(s, 'todoist', {'filter': 'assigned to: me'})
        asked = {}
        def fake(c_, p, **kw): asked.update(kw); return {'results': []}
        real, pm._todoist = pm._todoist, fake
        try: pm.poll_todoist(s, c, datetime.now())
        finally: pm._todoist = real
        self.assertEqual(asked['query'], 'assigned to: me')

    def test_default_query_is_what_todoist_says_is_live(self):
        s = MemoryStore()
        asked = {}
        def fake(c_, p, **kw): asked.update(kw); return {'results': []}
        real, pm._todoist = pm._todoist, fake
        try: pm.poll_todoist(s, conn(s, 'todoist'), datetime.now())
        finally: pm._todoist = real
        self.assertEqual(asked['query'], pm.TODOIST_FILTER)


if __name__ == '__main__':
    unittest.main()
